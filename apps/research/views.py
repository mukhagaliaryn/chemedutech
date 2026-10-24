"""Researcher / teacher views (/teacher/research/, /teacher/analytics/): lab attempts by research group,
course analytics and CSV exports (UTF-8 BOM). A teacher sees the data of their own courses, the admin — all.
"""

import csv

from django.contrib import messages
from django.db.models import Avg, Count
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from apps.assessments.models import AttemptAnswer
from apps.core.permissions import ADMIN, TEACHER, has_role, role_required
from apps.courses import selectors as course_selectors
from apps.courses.models import Topic
from apps.labs.engine import all_labs
from apps.labs.models import LabAttempt, LabEvent
from apps.organizations.models import ResearchCohort
from apps.practice.models import TeacherReview
from apps.practice.services import sampling
from apps.programme.models import DiagnosticResult

from . import analytics


def _group_name(user):
    profile = getattr(user, "student_profile", None)
    return profile.group.name if profile and profile.group else ""


def _scope(request, qs, field="enrollment"):
    """A teacher sees the work done in their courses; the admin — everything (previews included)."""
    if has_role(request.user, ADMIN):
        return qs
    return qs.filter(**{f"{field}__in": course_selectors.teacher_enrollments(request.user)})


def _filtered(request):
    qs = _scope(request, LabAttempt.objects.select_related("user__student_profile__group"))
    # ?cohort= keeps its old name in links; the field is LabAttempt.research_cohort
    for param, field in (("lab_key", "lab_key"), ("experiment_key", "experiment_key"), ("cohort", "research_cohort")):
        value = request.GET.get(param)
        if value:
            qs = qs.filter(**{field: value})
    if request.GET.get("group"):
        qs = qs.filter(user__student_profile__group__name=request.GET["group"])
    return qs


@role_required(TEACHER, ADMIN)
def dashboard(request):
    qs = _filtered(request)
    finished = qs.exclude(status=LabAttempt.Status.IN_PROGRESS)
    summary = (
        finished.values("experiment_key", "research_cohort")
        .annotate(
            n=Count("id"),
            students=Count("user", distinct=True),
            avg_time=Avg("duration_s"),
            avg_order=Avg("order_errors"),
            avg_safety=Avg("safety_warnings"),
            avg_wrong=Avg("wrong_items"),
            avg_score=Avg("analysis_correct"),
        )
        .order_by("experiment_key", "research_cohort")
    )
    experiments = [(e.key, e.title) for lab in all_labs().values() for e in lab.experiments]
    return render(
        request,
        "research/dashboard.html",
        {
            "summary": summary,
            "attempts": qs[:100],
            "total": qs.count(),
            "unfinished": qs.filter(status=LabAttempt.Status.IN_PROGRESS).count(),
            "experiments": experiments,
            "titles": dict(experiments),
            "cohort_names": dict(ResearchCohort.choices),
            "query": request.GET.urlencode(),
        },
    )


class _Echo:
    def write(self, value):
        return value


def _csv_response(filename, header, rows):
    writer = csv.writer(_Echo())

    def stream():
        yield "﻿"  # BOM so Excel opens UTF-8 (Kazakh letters) correctly
        yield writer.writerow(header)
        for row in rows:
            yield writer.writerow(row)

    response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@role_required(TEACHER, ADMIN)
def export_attempts(request):
    qs = _filtered(request)
    header = [
        "attempt_id",
        "username",
        "full_name",
        "study_group",
        "cohort",
        "lab",
        "experiment",
        "status",
        "started_at",
        "duration_s",
        "order_errors",
        "safety_warnings",
        "wrong_items",
        "wrong_choices",
        "hints_used",
        "journal_correct",
        "journal_total",
        "analysis_correct",
        "analysis_total",
        # added in STEP-08 — appended so that existing analysis scripts keep their column positions
        "enrollment_id",
        "course",
        "stage_id",
        "score_percent",
    ]
    rows = (
        [
            a.pk,
            a.user.username,
            a.user.get_full_name(),
            _group_name(a.user),
            a.research_cohort,
            a.lab_key,
            a.experiment_key,
            a.status,
            a.started_at.isoformat(),
            a.duration_s,
            a.order_errors,
            a.safety_warnings,
            a.wrong_items,
            a.wrong_choices,
            a.hints_used,
            a.journal_correct,
            a.journal_total,
            a.analysis_correct,
            a.analysis_total,
            a.enrollment_id or "",
            a.enrollment.course.slug if a.enrollment_id else "",
            a.stage_id or "",
            a.score_percent if a.score_percent is not None else "",
        ]
        for a in qs.select_related("enrollment__course").iterator()
    )
    return _csv_response("attempts.csv", header, rows)


@role_required(TEACHER, ADMIN)
def export_events(request):
    attempts = _filtered(request)
    qs = LabEvent.objects.filter(attempt__in=attempts).select_related("attempt__user").order_by("attempt_id", "seq")
    header = ["attempt_id", "username", "cohort", "experiment", "seq", "t_ms", "type", "step", "payload"]
    rows = (
        [
            e.attempt_id,
            e.attempt.user.username,
            e.attempt.research_cohort,
            e.attempt.experiment_key,
            e.seq,
            e.t_ms,
            e.type,
            e.step,
            e.payload,
        ]
        for e in qs.iterator()
    )
    return _csv_response("events.csv", header, rows)


@role_required(TEACHER, ADMIN)
def export_quiz_answers(request):
    qs = (
        _scope(request, AttemptAnswer.objects.all(), "attempt__enrollment")
        .select_related(
            "attempt__user__student_profile__group", "attempt__enrollment__course", "attempt__quiz", "question"
        )
        .prefetch_related("choices")
        .order_by("attempt_id", "question_id")
    )
    header = [
        "answer_id", "attempt_id", "username", "study_group", "cohort", "course", "quiz_id", "quiz_kind",
        "attempt_no", "started_at", "finished_at", "attempt_percent", "question_id", "question_kind",
        "chosen_ids", "text_value", "numeric_value", "is_correct", "points",
        "phase",  # STEP-22: pre / post for the course's pre/post test, empty otherwise (appended)
    ]  # fmt: skip
    rows = (
        [
            a.pk,
            a.attempt_id,
            a.attempt.user.username,
            _group_name(a.attempt.user),
            a.attempt.enrollment.research_cohort if a.attempt.enrollment_id else "",
            a.attempt.enrollment.course.slug if a.attempt.enrollment_id else "",
            a.attempt.quiz_id,
            a.attempt.quiz.kind,
            a.attempt.attempt_no,
            a.attempt.started_at.isoformat(),
            a.attempt.finished_at.isoformat() if a.attempt.finished_at else "",
            a.attempt.percent if a.attempt.percent is not None else "",
            a.question_id,
            a.question.kind,
            ";".join(str(c.pk) for c in a.choices.all()),
            a.text_value,
            a.numeric_value if a.numeric_value is not None else "",
            int(a.is_correct),
            a.points,
            a.attempt.phase,
        ]  # fmt: skip
        for a in qs.iterator(chunk_size=500)
    )
    return _csv_response("quiz_answers.csv", header, rows)


@role_required(TEACHER, ADMIN)
def export_diagnostics(request):
    """ICPAI diagnostics (D71): one row per student × stage × component — earned, maximum, percent, the level."""
    qs = DiagnosticResult.objects.select_related(
        "enrollment__student__student_profile__group", "enrollment__programme__course", "attempt"
    ).order_by("enrollment__student__username", "phase", "component")
    if not has_role(request.user, ADMIN):
        courses = course_selectors.teacher_courses(request.user)
        students = course_selectors.teacher_enrollments(request.user).values("student")
        qs = qs.filter(enrollment__programme__course__in=courses, enrollment__student__in=students)
    header = [
        "result_id", "username", "full_name", "study_group", "cohort", "programme", "course", "stage", "component",
        "earned", "maximum", "percent", "level", "attempt_id", "finished_at",
    ]  # fmt: skip
    rows = (
        [
            r.pk,
            r.enrollment.student.username,
            r.enrollment.student.full_name,
            _group_name(r.enrollment.student),
            r.enrollment.research_cohort,
            r.enrollment.programme.slug,
            r.enrollment.programme.course.slug,
            r.phase,
            r.component,
            r.earned,
            r.maximum,
            r.percent,
            r.level,
            r.attempt_id,
            r.attempt.finished_at.isoformat() if r.attempt.finished_at else "",
        ]  # fmt: skip
        for r in qs.iterator(chunk_size=500)
    )
    return _csv_response("diagnostics.csv", header, rows)


@role_required(TEACHER, ADMIN)
def export_ai_reviews(request):
    """Every teacher review of an AI grade — the raw data of the AI ↔ teacher agreement (§5.6)."""
    qs = (
        _scope(request, TeacherReview.objects.all(), "answer__submission__enrollment")
        .select_related("answer__item", "answer__ai_grade", "answer__submission__enrollment__course", "teacher")
        .order_by("answer_id", "created_at")
    )
    header = [
        "review_id", "answer_id", "submission_id", "course", "cohort", "item_id", "item_points", "ai_model",
        "ai_confidence", "ai_points", "teacher_points", "teacher", "reason", "sampled", "ai_criteria",
        "teacher_criteria", "created_at",
    ]  # fmt: skip

    def row(r):
        grade = getattr(r.answer, "ai_grade", None)
        sub = r.answer.submission
        return [
            r.pk, r.answer_id, sub.pk, sub.enrollment.course.slug, sub.enrollment.research_cohort, r.answer.item_id,
            r.answer.item.points, grade.model if grade else "", grade.confidence if grade else "",
            r.ai_points if r.ai_points is not None else "", r.teacher_points, r.teacher.username, r.reason,
            int(sub.sampled_at is not None), grade.criteria_scores if grade else "", r.criteria_scores,
            r.created_at.isoformat(),
        ]  # fmt: skip

    return _csv_response("ai_reviews.csv", header, (row(r) for r in qs.iterator(chunk_size=500)))


# --- course analytics ----------------------------------------------------------------------------


def _analytics_scope(request, slug):
    course = get_object_or_404(course_selectors.teacher_courses(request.user), slug=slug)
    groups = (
        course_selectors.teacher_groups(request.user)
        .filter(pk__in=course_selectors.teacher_enrollments(request.user, course).exclude(group=None).values("group"))
        .order_by("name")
    )
    group = next((g for g in groups if str(g.pk) == request.GET.get("group")), None)
    topics = list(Topic.objects.filter(module__course=course, is_published=True).order_by("number"))
    topic = next((t for t in topics if str(t.number) == request.GET.get("topic")), None)
    return course, groups, group, topics, topic


@role_required(TEACHER, ADMIN)
def analytics_page(request, slug=None):
    if slug is None:
        first = course_selectors.teacher_courses(request.user).first()
        if first is None:
            return render(request, "research/analytics.html", {"course": None})
        return redirect("research:analytics_course", first.slug)
    course, groups, group, topics, topic = _analytics_scope(request, slug)
    data = analytics.page(request.user, course, group, topic)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        stamp = timezone.localdate().isoformat()
        response["Content-Disposition"] = f'attachment; filename="analytics_{course.slug}_{stamp}.csv"'
        response.write("\ufeff")
        csv.writer(response).writerows(analytics.csv_rows(data))
        return response
    return render(
        request,
        "research/analytics.html",
        {
            "course": course,
            "courses": course_selectors.teacher_courses(request.user),
            "groups": groups,
            "group": group,
            "all_topics": topics,
            "topic": topic,
            "query": request.GET.urlencode(),
            **data,
        },
    )


@require_POST
@role_required(TEACHER, ADMIN)
def draw_sample(request, slug):
    course = get_object_or_404(course_selectors.teacher_courses(request.user), slug=slug)
    ids = list(course_selectors.teacher_enrollments(request.user, course).values_list("pk", flat=True))
    added = sampling.draw_review_sample(ids, course.review_sample_percent)
    if added:
        messages.success(
            request,
            ngettext("%(n)s work is drawn for your check.", "%(n)s works are drawn for your check.", added)
            % {"n": added},
        )
    else:
        messages.info(request, _("The sample is already complete; nothing new was drawn."))
    return redirect("research:analytics_course", course.slug)
