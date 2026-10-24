"""Teacher: the ICPAI programme in the cabinet (docs/icpai/SPEC.md §4.9; STEP-39) — the block on the home page (the
groups' progress by section, the review queues, the section 8 dates), the student page's «ICPAI» tab (sections,
diagnostics I/II/III, the lessons of sections 4, 5, 6, 8 with versions and trial protocols, the portfolio, the AI
dialogues) and the read-only pages of a lesson, a trial and an AI dialogue. Reads only."""

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.ai.models import AIConversation, AIMessage, Mode
from apps.courses import selectors as course_selectors
from apps.pedagogy import frames
from apps.pedagogy import selectors as pedagogy_selectors
from apps.pedagogy.models import ExpertReview, Lesson, Review, Trial
from apps.programme import selectors as programme_selectors
from apps.programme.models import Portfolio, Programme, SectionProgress, SectionSchedule

from .views import _student, teacher_only

S = SectionProgress.Status
# the section each kind of lesson belongs to, in the programme's order
LESSON_SECTIONS = (
    (Lesson.Kind.TEMPLATE_COPY, 4),
    (Lesson.Kind.RESEARCH_PRACTICE, 5),
    (Lesson.Kind.MICROLESSON, 6),
    (Lesson.Kind.INDEPENDENT, 8),
)


# the lessons' extra details (pedagogy services: micro, independent) → their labels
DETAIL_LABELS = {
    "programme": _("Education programme"), "study_year": _("Study year"), "course_group": _("Study year and group"),
    "source_title": _("Part of the practice"), "idea": _("Authorial pedagogical idea"),
    "lab_task": _("Lab or research task"), "assessment": _("Assessment criteria"), "feedback_way": _("Way of feedback"),
}  # fmt: skip


def _programme(user) -> Programme | None:
    return (
        Programme.objects.filter(course__in=course_selectors.teacher_courses(user), is_active=True)
        .order_by("pk")
        .first()
    )


def dashboard_block(request) -> dict | None:
    """The home page's ICPAI block: each group × the 8 sections (passed of the students, the mean percent), the
    works waiting in the review queues and the section 8 dates ahead."""
    from . import practice  # practice imports views; this module is imported by views lazily

    programme = _programme(request.user)
    if programme is None:
        return None
    groups = list(course_selectors.teacher_groups(request.user).filter(is_active=True).order_by("name"))
    users = get_user_model().objects.filter(student_profile__group__in=groups).select_related("student_profile")
    by_group: dict[int, list] = {}
    for u in users:
        by_group.setdefault(u.student_profile.group_id, []).append(u)
    sections, rows = programme_selectors.matrix(programme, list(users))
    progress = {r["student"].pk: r["cells"] for r in rows}
    group_rows = []
    for group in groups:
        students = by_group.get(group.pk, [])
        if not students:
            continue
        cells = []
        for i, section in enumerate(sections):
            marks = [progress[s.pk][i]["progress"] for s in students]
            passed = sum(1 for m in marks if m and m.status == S.PASSED)
            mean = sum(float(m.percent) for m in marks if m) / len(students)
            cells.append({"section": section, "passed": passed, "mean": mean, "share": passed * 100 / len(students)})
        group_rows.append({"group": group, "students": len(students), "cells": cells})
    today = timezone.localdate()
    deadlines = (
        SectionSchedule.objects.filter(group__in=groups, section__programme=programme)
        .filter(Q(hand_in_on__gte=today) | Q(trial_on__gte=today))
        .select_related("group")
        .order_by("hand_in_on", "trial_on")[:6]
    )
    return {
        "programme": programme,
        "sections": sections,
        "group_rows": group_rows,
        "queues": [
            {"what": "practice", "n": practice._practices(request).filter(reviews__isnull=True).count()},
            {"what": "micro", "n": practice._micro_trials(request).filter(reviews__isnull=True).count()},
            {"what": "portfolio", "n": practice._portfolios(request).filter(status=Portfolio.Status.SUBMITTED).count()},
            {"what": "independent", "n": practice._independent_waiting(request).count()},
        ],
        "deadlines": list(deadlines),
        "today": today,
    }


def _lesson_rows(student) -> list[dict]:
    """The student's lessons by section with their trials and the teacher's grades."""
    lessons = list(
        Lesson.objects.filter(owner=student)
        .select_related("source_template")
        .annotate(n_versions=Count("versions", distinct=True))
        .order_by("cycle", "pk")
    )
    trials: dict[int, list] = {}
    for t in Trial.objects.filter(lesson__in=lessons).order_by("started_at", "pk"):
        trials.setdefault(t.lesson_id, []).append(t)
    grades: dict[tuple, int] = {}
    for lesson_id, trial_id, total in Review.objects.filter(lesson__in=lessons).values_list("lesson", "trial", "total"):
        grades[(lesson_id, trial_id)] = total
    out = []
    for kind, number in LESSON_SECTIONS:
        items = [
            {
                "lesson": x,
                "trials": [{"trial": t, "grade": grades.get((x.pk, t.pk))} for t in trials.get(x.pk, [])],
                "grade": grades.get((x.pk, None)),
            }
            for x in lessons
            if x.kind == kind
        ]
        out.append({"kind": kind, "number": number, "label": Lesson.Kind(kind).label, "items": items})
    return out


def _conversations(student):
    return (
        AIConversation.objects.filter(user=student)
        .annotate(
            answers=Count("messages", filter=Q(messages__role=AIMessage.Role.ASSISTANT)),
            tokens=Sum("messages__input_tokens") + Sum("messages__output_tokens"),
        )
        .order_by("-created_at")
    )


def student_context(student) -> dict:
    """The «ICPAI» tab of the teacher's student page."""
    enrollment = programme_selectors.current_enrollment(student)
    if enrollment is None:
        return {"icpai": None}
    conversations = _conversations(student)
    by_mode = dict(AIConversation.objects.filter(user=student).order_by().values_list("mode").annotate(n=Count("pk")))
    return {
        "icpai": enrollment,
        "section_rows": programme_selectors.section_rows(enrollment),
        "diagnostics": programme_selectors.diagnostic_summaries(enrollment.programme, [student]).get(student.pk, {}),
        "dynamics": programme_selectors.component_dynamics(enrollment),
        "phases": ("I", "II", "III"),
        "lesson_sections": _lesson_rows(student),
        "portfolio": Portfolio.objects.filter(enrollment=enrollment).first(),
        "conversations": list(conversations[:40]),
        "conversations_total": sum(by_mode.values()),
        "modes": [{"mode": m, "label": label, "n": by_mode.get(m, 0)} for m, label in Mode.choices],
    }


@teacher_only
def lesson(request, pk, lesson_pk):
    """A student's lesson, read only: the details, the stages with their content, the versions, the trials, the
    checks and «Айгерім»'s opinions."""
    student = _student(request, pk)
    item = get_object_or_404(Lesson.objects.select_related("source_template"), pk=lesson_pk, owner=student)
    stages = list(item.stages.select_related("lesson").order_by("order"))
    grades = {r.trial_id: r for r in Review.objects.filter(lesson=item)}
    return render(request, "teacher/icpai/lesson.html", {
        "student": student, "lesson": item,
        "stages": [{**row, "fields": pedagogy_selectors.stage_fields(row["stage"])}
                   for row in pedagogy_selectors.timeline(stages)],
        "versions": list(item.versions.order_by("-number")),
        "trials": [{"trial": t, "review": grades.get(t.pk)} for t in item.trials.order_by("started_at", "pk")],
        "review": grades.get(None),
        "checks": list(item.checks.order_by("-created_at")[:5]),
        "expert_reviews": list(item.expert_reviews.filter(kind=ExpertReview.Kind.DRAFT)[:5]),
        "details": [(label, item.details[k]) for k, label in DETAIL_LABELS.items() if item.details.get(k)],
    })  # fmt: skip


@teacher_only
def trial(request, pk, trial_pk):
    """A trial's protocol, read only: the AI student's answers and the student's analysis by stage, the dialogue
    messages, or the real audience's protocol; the teacher's grade and «Айгерім»'s analysis."""
    student = _student(request, pk)
    item = get_object_or_404(
        Trial.objects.select_related("lesson", "version", "recorded_by"), pk=trial_pk, lesson__owner=student
    )
    return render(request, "teacher/icpai/trial.html", {
        "student": student, "trial": item, "lesson": item.lesson,
        "turns": list(item.turns.order_by("stage_order")), "messages_": list(item.messages.order_by("number")),
        "review": Review.objects.filter(trial=item).first() or (
            Review.objects.filter(lesson=item.lesson, trial__isnull=True).first()
            if item.lesson.kind == Lesson.Kind.RESEARCH_PRACTICE else None
        ),
        "expert_reviews": list(item.expert_reviews.all()), "directions": ExpertReview.TRIAL_DIRECTIONS,
        "free": frames.FREE,
    })  # fmt: skip


@teacher_only
def conversation(request, pk, conversation_pk):
    """An AI dialogue of the student, read only (assistant, AI student, checker, «Айгерім»)."""
    student = _student(request, pk)
    item = get_object_or_404(AIConversation, pk=conversation_pk, user=student)
    return render(request, "teacher/icpai/conversation.html", {
        "student": student, "conversation": item, "messages_": list(item.messages.all()),
        "tokens": item.messages.aggregate(i=Sum("input_tokens"), o=Sum("output_tokens")),
    })  # fmt: skip
