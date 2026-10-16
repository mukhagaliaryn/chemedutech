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
