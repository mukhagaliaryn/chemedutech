"""Researcher / teacher views: attempt overview by research group and CSV export."""

import csv

from django.db.models import Avg, Count
from django.http import StreamingHttpResponse
from django.shortcuts import render

from apps.core.permissions import ADMIN, TEACHER, role_required
from apps.labs.engine import all_labs
from apps.labs.models import LabAttempt, LabEvent
from apps.organizations.models import ResearchCohort


def _group_name(user):
    profile = getattr(user, "student_profile", None)
    return profile.group.name if profile and profile.group else ""


def _filtered(request):
    qs = LabAttempt.objects.select_related("user__student_profile__group")
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
