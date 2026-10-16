from apps.labs.models import LabAttempt


def analysed_attempts(enrollment, stage) -> dict:
    """{experiment_key: best analysed attempt} of one student in one lab stage (highest score, then earliest)."""
    result = {}
    qs = LabAttempt.objects.filter(enrollment=enrollment, stage=stage, status=LabAttempt.Status.ANALYSED)
    for a in qs.order_by("experiment_key", "-score_percent", "started_at"):
        result.setdefault(a.experiment_key, a)
    return result
