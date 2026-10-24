"""Reads for section 7 — the professional portfolio (guide @S7): the student's works of the earlier sections as the
eight cards of «My professional works» (I.1, gathered automatically, nothing copied) and the ten parts of the assembled
portfolio (VI). Everything is read from the apps where it lives."""

from django.db.models import Max
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.html import html_to_text
from apps.pedagogy.models import Lesson, LessonEvent, Review, Trial
from apps.practice import selectors as practice_selectors
from apps.progress.models import CourseResult, TopicResult

from .models import (
    DIRECTIONS,
    QUESTIONS,
    DevelopmentPlanItem,
    DiagnosticResult,
    PortfolioFeedback,
    Reflection,
    Section,
)
from .providers.course import course_enrollment


def _section_url(enrollment, kind) -> str:
    section = Section.objects.filter(programme=enrollment.programme, kind=kind).first()
    return reverse("student:section", args=[section.number]) if section else ""


def _date(value):
    return value.date() if hasattr(value, "date") else value


def _status(done, label_done, label_progress, label_none=None):
    if done is None:
        return {"label": label_none or _("Not started"), "tone": "none"}
    return {"label": label_done, "tone": "ok"} if done else {"label": label_progress, "tone": "progress"}


def works(enrollment) -> list[dict]:
    """The eight components of the portfolio (@S7 I.1) as cards: title, date, kind, status, grade, the teacher's
    comment and the link to the work."""
    from .services import diagnostics  # here: services → engine → providers → this module

    student = enrollment.student
    lessons = list(Lesson.objects.filter(owner=student).prefetch_related("reviews", "stages"))
    by_kind = {k: [x for x in lessons if x.kind == k] for k in Lesson.Kind.values}
    cards = []

    # 1. the course: lectures, practical and lab works
    course_enr = course_enrollment(enrollment)
    result = CourseResult.objects.filter(enrollment=course_enr).first() if course_enr else None
    topics = TopicResult.objects.filter(enrollment=course_enr) if course_enr else TopicResult.objects.none()
    comment = practice_selectors.teacher_comments(course_enr, 1).first() if course_enr else None
    score = (
        result.score_percent
        if result and result.score_percent is not None
        else (result.current_percent if result else None)
    )
    cards.append({
        "key": "course", "icon": "lab",
        "title": _("Lectures learnt and practical and lab works done in general chemistry"),
        "kind": _("Theoretical, practical and lab works"),
        "date": _date(result.completed_at or result.updated_at) if result else None,
        "status": _status(None if course_enr is None else bool(result and result.passed), _("Passed"), _("In progress")),
        "grade": f"{score:.0f}%" if score is not None else "",
        "detail": _("%(a)s of %(b)s topics completed") % {"a": topics.filter(status="completed").count(), "b": topics.count()},
        "comment": comment.teacher_comment if comment else "",
        "url": reverse("student:course", args=[course_enr.course.slug]) if course_enr else "",
    })  # fmt: skip

    # 2. the diagnostics I, II, III
    results = list(DiagnosticResult.objects.filter(enrollment=enrollment))
    phases = sorted({r.phase for r in results})
    latest = results and max(results, key=lambda r: r.created_at)
    summary = diagnostics.summary([r for r in results if r.phase == phases[-1]]) if phases else None
    cards.append({
        "key": "diagnostics", "icon": "chart",
        "title": _("Results of the initial, formative and final diagnostics of professional readiness"),
        "kind": _("Diagnostics"),
        "date": _date(latest.created_at) if latest else None,
        "status": _status(None if not phases else len(phases) == 3, _("Taken"), _("In progress")),
        "grade": f"{summary['earned']:.0f}/{summary['maximum']:.0f}" if summary else "",
        "detail": " · ".join(phases),
        "comment": "", "url": reverse("student:icpai"),
    })  # fmt: skip

    # 3. the authorial lesson templates (section 4)
    copies = by_kind["template_copy"]
    finals = [x for x in copies if x.status == "final"]
    cards.append({
        "key": "designer", "icon": "book",
        "title": _("Authorial pedagogical design samples"), "kind": _("Authorial lessons"),
        "date": _date(max((x.updated_at for x in copies), default=None)),
        "status": _status(None if not copies else len(finals) == len(copies) and len(copies) >= 3,
                          _("Final versions"), _("In progress")),
        "grade": "", "detail": _("%(n)s final versions") % {"n": len(finals)}, "comment": "",
        "url": _section_url(enrollment, Section.Kind.DESIGNER),
    })  # fmt: skip

    # 4. the tasks developed with the AI assistant and corrected by the student
    redesigned = sum(1 for x in lessons for s in x.stages.all() if s.edited)
    inserted = LessonEvent.objects.filter(lesson__owner=student, action=LessonEvent.Action.AI_INSERTED).count()
    cards.append({
        "key": "ai_tasks", "icon": "sparkle",
        "title": _("Tasks developed with the AI assistant and corrected by the student"), "kind": _("Tasks"),
        "date": _date(LessonEvent.objects.filter(lesson__owner=student).aggregate(t=Max("created_at"))["t"]),
        "status": _status(None if not redesigned else True, _("Done"), _("In progress")),
        "grade": "", "detail": _("%(a)s stages redesigned, %(b)s AI suggestions reworked") % {"a": redesigned, "b": inserted},
        "comment": "", "url": _section_url(enrollment, Section.Kind.DESIGNER),
    })  # fmt: skip

    # 5. the lessons of the digital research practice (section 5)
    practices = by_kind["research_practice"]
    reviews = [x.review for x in practices if x.review]
    cards.append({
        "key": "practice", "icon": "activity",
        "title": _("Lessons developed in the digital research practice"), "kind": _("Digital research practice"),
        "date": _date(max((x.updated_at for x in practices), default=None)),
        "status": _status(None if not practices else all(x.status == "final" for x in practices) and len(practices) >= 3,
                          _("Results gathered"), _("In progress")),
        "grade": " · ".join(f"{r.total}/10" for r in reviews),
        "detail": _("%(n)s practices") % {"n": len(practices)},
        "comment": next((r.comment for r in sorted(reviews, key=lambda r: r.updated_at, reverse=True) if r.comment), ""),
        "url": _section_url(enrollment, Section.Kind.RESEARCH_PRACTICE),
    })  # fmt: skip

    # 6. the protocols of the trials with the AI student
    trials = Trial.objects.filter(lesson__owner=student, finished_at__isnull=False)
    cards.append({
        "key": "trials", "icon": "user",
        "title": _("Protocols of the pedagogical trials with the AI student"), "kind": _("Trial protocols"),
        "date": _date(trials.aggregate(t=Max("finished_at"))["t"]),
        "status": _status(None if not trials.exists() else True, _("Done"), _("In progress")),
        "grade": "", "detail": _("%(n)s trials") % {"n": trials.count()}, "comment": "",
        "url": _section_url(enrollment, Section.Kind.RESEARCH_PRACTICE),
    })  # fmt: skip

    # 7. the initial and improved versions of the microlesson (section 6)
    micro = next(iter(by_kind["microlesson"]), None)
    micro_reviews = (
        list(Review.objects.filter(lesson=micro, trial__isnull=False).order_by("trial__started_at")) if micro else []
    )
    cards.append({
        "key": "micro", "icon": "play",
        "title": _("The initial and improved versions of the microlesson"), "kind": _("Microlesson"),
        "date": _date(micro.updated_at) if micro else None,
        "status": _status(None if micro is None else micro.status == "final", _("Assembled"), _("In progress")),
        "grade": " → ".join(f"{r.total}/10" for r in micro_reviews),
        "detail": _("%(n)s trials") % {"n": micro.trials.count() if micro else 0},
        "comment": next((r.comment for r in reversed(micro_reviews) if r.comment), ""),
        "url": _section_url(enrollment, Section.Kind.MICROLESSON),
    })  # fmt: skip

    # 8. the teacher's expert feedback and the student's reflection
    feedback = PortfolioFeedback.objects.filter(portfolio__enrollment=enrollment).first()
    reflection = Reflection.objects.filter(enrollment=enrollment).first()
    cards.append({
        "key": "feedback", "icon": "message",
        "title": _("The teacher's expert feedback and the student's professional reflection"),
        "kind": _("Feedback and reflection"),
        "date": _date(feedback.created_at if feedback else reflection.saved_at if reflection else None),
        "status": {"label": feedback.get_status_display(), "tone": "ok" if feedback.status == "accepted" else "progress"}
        if feedback else _status(None if reflection is None else False, "", _("Reflection saved")),
        "grade": "", "detail": "", "comment": feedback.strengths if feedback else "",
        "url": reverse("student:portfolio_reflection"),
    })  # fmt: skip
    return cards


def reflection_answers(enrollment) -> dict:
    reflection = Reflection.objects.filter(enrollment=enrollment).first()
    return dict(reflection.answers) if reflection else {}


def plan_rows(enrollment) -> list[dict]:
    items = {i.direction: i for i in DevelopmentPlanItem.objects.filter(enrollment=enrollment)}
    return [{"direction": key, "label": label, "item": items.get(key)} for key, label in DIRECTIONS]


def completeness(enrollment) -> dict:
    """What «Assemble the portfolio» needs: the reflection (all seven answers), the development map (action and
    expected result in all five directions) and the final (III) diagnostics."""
    answers = reflection_answers(enrollment)
    reflection = all(len(html_to_text(answers.get(k, "")).strip()) >= 10 for k, _q in QUESTIONS)
    rows = plan_rows(enrollment)
    plan = all(r["item"] and r["item"].action.strip() and r["item"].expected.strip() for r in rows)
    final_diagnostics = DiagnosticResult.objects.filter(enrollment=enrollment, phase="III").exists()
    return {"reflection": reflection, "plan": plan, "diagnostics": final_diagnostics,
            "ready": reflection and plan and final_diagnostics}  # fmt: skip
