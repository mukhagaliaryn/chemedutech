"""Teacher: one student's full results in one ICPAI section (STEP-47) — the page «Open» leads to from a section's
students table. 1 — the course (the student page's «Course» tab), 2 — the diagnostics I/II/III: the total, the level and
its interpretation, the components and every answer with the key; 3 — the video watched; 4, 5, 6, 8 — the section's
lessons with versions, trials, the teacher's grades and comments; 7 — the portfolio with the teacher's feedback.
Every section also lists the student's AI dialogues that belong to it. Reads only."""

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.assessments import selectors as quiz_selectors
from apps.pedagogy.models import Lesson, LessonStage, Review, Trial
from apps.programme import portfolio_selectors
from apps.programme import selectors as programme_selectors
from apps.programme.models import (
    QUESTIONS,
    Portfolio,
    PortfolioFeedback,
    ProgrammeEnrollment,
    Section,
    SectionProgress,
    SectionVideo,
    VideoWatch,
)

from . import icpai, scope
from .views import _student, teacher_only

K = Section.Kind
LESSON_KINDS = {
    K.DESIGNER: Lesson.Kind.TEMPLATE_COPY,
    K.RESEARCH_PRACTICE: Lesson.Kind.RESEARCH_PRACTICE,
    K.MICROLESSON: Lesson.Kind.MICROLESSON,
    K.INDEPENDENT: Lesson.Kind.INDEPENDENT,
}
SECTION_OF_LESSON = {v: k for k, v in LESSON_KINDS.items()}
FEEDBACK_FIELDS = ("chemistry", "design", "digital", "practice", "strengths", "improvements", "recommendations")


@teacher_only
def student(request, number, pk):
    programme = icpai._programme(request.user)
    if programme is None:
        raise Http404
    section = get_object_or_404(programme.sections, number=number)
    person = _student(request, pk)
    if section.kind == K.COURSE:  # the course results live on the student page
        return redirect(f"{reverse('teacher:student', args=[person.pk])}?course={programme.course.slug}#stages")
    enrollment = ProgrammeEnrollment.objects.filter(programme=programme, student=person).first()
    progress = SectionProgress.objects.filter(enrollment=enrollment, section=section).first() if enrollment else None
    context = {
        "programme": programme, "section": section, "student": person, "enrollment": enrollment,
        "progress": progress, "conversations": _conversations(person, section), **_neighbours(request, person),
    }  # fmt: skip
    if enrollment:
        context.update(BLOCKS.get(section.kind, lambda *a: {})(section, person, enrollment))
    return render(request, "teacher/sections/student.html", context)


def _neighbours(request, person) -> dict:
    """The previous / next student of the same group (the section page's tab order)."""
    profile = getattr(person, "student_profile", None)
    group = profile.group if profile else None
    ids = list(
        get_user_model()
        .objects.filter(pk__in=scope.students(request).values("pk"), student_profile__group=group)
        .order_by("last_name", "first_name", "username")
        .values_list("pk", flat=True)
    ) if group else []  # fmt: skip
    at = ids.index(person.pk) if person.pk in ids else -1
    return {
        "group": group,
        "position": at + 1,
        "group_size": len(ids),
        "prev_pk": ids[at - 1] if at > 0 else None,
        "next_pk": ids[at + 1] if 0 <= at < len(ids) - 1 else None,
    }


# --- section blocks --------------------------------------------------------------------------


def _diagnostic(section, person, enrollment) -> dict:
    phases = []
    for row in programme_selectors.diagnostic_rows(enrollment, section):
        attempt = row["results"][0].attempt if row["results"] and row["results"][0].attempt_id else None
        level = row["summary"]["level"] if row["summary"] else ""
        phases.append({
            **row, "attempt": attempt, "level_text": row["test"].levels.get(level, "") if level else "",
            "answers": quiz_selectors.review_rows(attempt) if attempt and attempt.is_finished else [],
        })  # fmt: skip
    return {"phases": phases, "dynamics": programme_selectors.component_dynamics(enrollment)}


def _video(section, person, enrollment) -> dict:
    return {
        "video": SectionVideo.objects.filter(section=section).first(),
        "watch": VideoWatch.objects.filter(enrollment=enrollment, section=section).first(),
    }


def _lessons(section, person, enrollment) -> dict:
    lessons = list(
        Lesson.objects.filter(owner=person, kind=LESSON_KINDS[section.kind])
        .select_related("source_template")
        .annotate(n_versions=Count("versions", distinct=True))
        .order_by("cycle", "source_template__number", "pk")
    )
    trials: dict[int, list] = {}
    for t in Trial.objects.filter(lesson__in=lessons).order_by("started_at", "pk"):
        trials.setdefault(t.lesson_id, []).append(t)
    reviews = {(r.lesson_id, r.trial_id): r for r in Review.objects.filter(lesson__in=lessons)}
    criteria = dict(Review.MICRO_CRITERIA if section.kind == K.MICROLESSON else Review.CRITERIA)
    items = []
    for x in lessons:
        review = reviews.get((x.pk, None))
        items.append({
            "lesson": x, "review": review, "scores": _scores(review, criteria),
            "trials": [{"trial": t, "review": reviews.get((x.pk, t.pk)), "scores": _scores(reviews.get((x.pk, t.pk)), criteria)}
                       for t in trials.get(x.pk, [])],
        })  # fmt: skip
    return {"lessons": items}


def _scores(review, criteria) -> list[dict]:
    """Points by criterion; section 8 keeps only a total (``{"total": n}``), which the page shows already."""
    if review is None or not review.scores:
        return []
    rows = [(int(k), v) for k, v in review.scores.items() if str(k).isdigit()]
    return [{"label": criteria.get(k, k), "points": v} for k, v in sorted(rows)]


def _portfolio(section, person, enrollment) -> dict:
    """The reflection's seven answers, the development map, what «Assemble» still needs and the portfolio itself
    with the teacher's feedback (the full ten parts are on the portfolio review page)."""
    portfolio = Portfolio.objects.filter(enrollment=enrollment).first()
    answers = portfolio_selectors.reflection_answers(enrollment)
    return {
        "portfolio": portfolio,
        "versions": portfolio.versions.count() if portfolio else 0,
        "feedbacks": [
            {
                "feedback": f,
                "fields": [
                    (PortfolioFeedback._meta.get_field(n).verbose_name, getattr(f, n))
                    for n in FEEDBACK_FIELDS
                    if getattr(f, n)
                ],
            }
            for f in PortfolioFeedback.objects.filter(portfolio=portfolio)
            .select_related("teacher")
            .order_by("-created_at")
        ]
        if portfolio
        else [],  # fmt: skip
        "reflection": [{"question": q, "answer": answers.get(k, "")} for k, q in QUESTIONS],
        "plan": portfolio_selectors.plan_rows(enrollment),
        "completeness": portfolio_selectors.completeness(enrollment),
    }


BLOCKS = {
    K.DIAGNOSTIC: _diagnostic,
    K.VIDEO: _video,
    K.DESIGNER: _lessons,
    K.RESEARCH_PRACTICE: _lessons,
    K.MICROLESSON: _lessons,
    K.INDEPENDENT: _lessons,
    K.PORTFOLIO: _portfolio,
}


# --- AI dialogues of the section --------------------------------------------------------------


def _conversations(person, section) -> list:
    """The student's AI dialogues that belong to the section: its «explain» panel, and those about its lessons,
    lesson stages, trials, the microlesson check or the portfolio."""
    rows = list(icpai._conversations(person))
    lesson_ids = {c.context_id for c in rows if c.context_type in ("lesson", "microlesson")}
    stage_lessons = dict(
        LessonStage.objects.filter(pk__in=[c.context_id for c in rows if c.context_type == "lesson_stage"]).values_list(
            "pk", "lesson"
        )
    )
    trial_lessons = dict(
        Trial.objects.filter(pk__in=[c.context_id for c in rows if c.context_type == "trial"]).values_list(
            "pk", "lesson"
        )
    )
    kinds = dict(
        Lesson.objects.filter(
            pk__in=lesson_ids | set(stage_lessons.values()) | set(trial_lessons.values())
        ).values_list("pk", "kind")
    )

    def section_kind(c):
        if c.context_type == "section":
            return section.kind if c.context_id == section.pk else None
        if c.context_type == "portfolio":
            return K.PORTFOLIO
        lesson = {"lesson_stage": stage_lessons, "trial": trial_lessons}.get(c.context_type, {}).get(c.context_id)
        if c.context_type in ("lesson", "microlesson"):
            lesson = c.context_id
        return SECTION_OF_LESSON.get(kinds.get(lesson))

    return [c for c in rows if section_kind(c) == section.kind]
