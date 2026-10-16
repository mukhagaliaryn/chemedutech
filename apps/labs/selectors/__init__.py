from apps.labs.models import LabAttempt


def analysed_attempts(enrollment, stage) -> dict:
    """{experiment_key: best analysed attempt} of one student in one lab stage (highest score, then earliest)."""
    result = {}
    qs = LabAttempt.objects.filter(enrollment=enrollment, stage=stage, status=LabAttempt.Status.ANALYSED)
    for a in qs.order_by("experiment_key", "-score_percent", "started_at"):
        result.setdefault(a.experiment_key, a)
    return result


def recent_analysed(enrollment):
    """Analysed attempts of one enrolment, newest first."""
    return LabAttempt.objects.filter(enrollment=enrollment, status=LabAttempt.Status.ANALYSED).order_by(
        "-finished_at", "-pk"
    )


def analysed_experiment_count(enrollment) -> int:
    """Experiments (stage × experiment) with at least one analysed attempt."""
    return (
        LabAttempt.objects.filter(enrollment=enrollment, status=LabAttempt.Status.ANALYSED)
        .values("stage_id", "experiment_key")
        .distinct()
        .count()
    )


def error_totals(enrollment_ids) -> dict[int, dict]:
    """{enrollment_id: {order, safety, wrong}} summed over every attempt (the research log counts them all)."""
    from django.db.models import F, Sum

    rows = (
        LabAttempt.objects.filter(enrollment_id__in=enrollment_ids)
        .values("enrollment_id")
        .annotate(
            order=Sum("order_errors"), safety=Sum("safety_warnings"), wrong=Sum(F("wrong_items") + F("wrong_choices"))
        )
    )
    return {r["enrollment_id"]: r for r in rows}


def last_attempt_times(enrollment_ids) -> dict[int, object]:
    from django.db.models import Max

    rows = (
        LabAttempt.objects.filter(enrollment_id__in=enrollment_ids)
        .values("enrollment_id")
        .annotate(at=Max("started_at"))
    )
    return {r["enrollment_id"]: r["at"] for r in rows}


def risky_attempts(enrollment_ids, min_safety=3):
    return LabAttempt.objects.filter(enrollment_id__in=enrollment_ids, safety_warnings__gte=min_safety).order_by(
        "-started_at"
    )


def attempts_of(enrollment):
    return LabAttempt.objects.filter(enrollment=enrollment).select_related("stage").order_by("-started_at")


def events_of(attempt):
    return attempt.events.order_by("seq", "pk")
