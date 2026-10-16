from apps.labs.models import LabAttempt


def best_attempts_by_experiment(user, lab_key):
    """Latest completed attempt per experiment for the topic page progress."""
    result = {}
    qs = LabAttempt.objects.filter(user=user, lab_key=lab_key).exclude(status=LabAttempt.Status.IN_PROGRESS)
    for a in qs.order_by("started_at"):
        result[a.experiment_key] = a
    return result
