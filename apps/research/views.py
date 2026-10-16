"""Researcher / teacher views: attempt overview by research group and CSV export."""
import csv

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count
from django.http import StreamingHttpResponse
from django.shortcuts import render

from apps.accounts.models import User
from apps.labs.engine import all_labs
from apps.labs.models import LabAttempt, LabEvent


def _require_teacher(request):
    if not request.user.is_teacher:
        raise PermissionDenied


def _filtered(request):
    qs = LabAttempt.objects.select_related("user")
    for param in ("lab_key", "experiment_key", "cohort"):
        value = request.GET.get(param)
        if value:
            qs = qs.filter(**{param: value})
    if request.GET.get("group"):
        qs = qs.filter(user__study_group=request.GET["group"])
    return qs


@login_required
def dashboard(request):
    _require_teacher(request)
    qs = _filtered(request)
    finished = qs.exclude(status=LabAttempt.Status.IN_PROGRESS)
    summary = (
        finished.values("experiment_key", "cohort")
        .annotate(
            n=Count("id"),
            students=Count("user", distinct=True),
            avg_time=Avg("duration_s"),
            avg_order=Avg("order_errors"),
            avg_safety=Avg("safety_warnings"),
            avg_wrong=Avg("wrong_items"),
            avg_score=Avg("analysis_correct"),
        )
        .order_by("experiment_key", "cohort")
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
            "cohort_names": dict(User.Cohort.choices),
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


@login_required
def export_attempts(request):
    _require_teacher(request)
    qs = _filtered(request)
    header = [
        "attempt_id", "username", "full_name", "study_group", "cohort", "lab", "experiment", "status",
        "started_at", "duration_s", "order_errors", "safety_warnings", "wrong_items", "wrong_choices",
        "hints_used", "journal_correct", "journal_total", "analysis_correct", "analysis_total",
    ]
    rows = (
        [
            a.pk, a.user.username, a.user.get_full_name(), a.user.study_group, a.cohort, a.lab_key,
            a.experiment_key, a.status, a.started_at.isoformat(), a.duration_s, a.order_errors,
            a.safety_warnings, a.wrong_items, a.wrong_choices, a.hints_used, a.journal_correct,
            a.journal_total, a.analysis_correct, a.analysis_total,
        ]
        for a in qs.iterator()
    )
    return _csv_response("attempts.csv", header, rows)


@login_required
def export_events(request):
    _require_teacher(request)
    attempts = _filtered(request)
    qs = LabEvent.objects.filter(attempt__in=attempts).select_related("attempt__user").order_by("attempt_id", "seq")
    header = ["attempt_id", "username", "cohort", "experiment", "seq", "t_ms", "type", "step", "payload"]
    rows = (
        [e.attempt_id, e.attempt.user.username, e.attempt.cohort, e.attempt.experiment_key, e.seq, e.t_ms,
         e.type, e.step, e.payload]
        for e in qs.iterator()
    )
    return _csv_response("events.csv", header, rows)
