from .models import PracticeSubmission

S = PracticeSubmission.Status


def finished_submissions(enrollment):
    """Graded or waiting-for-review submissions of one enrolment, newest first."""
    return (
        PracticeSubmission.objects.filter(enrollment=enrollment, status__in=(S.GRADED, S.NEEDS_REVIEW))
        .select_related("stage")
        .order_by("-graded_at", "-pk")
    )


def submission_counts(enrollment) -> dict[int, int]:
    """{stage_id: attempts used} — returned works are given back and do not count."""
    counts = {}
    qs = PracticeSubmission.objects.filter(enrollment=enrollment).exclude(status=S.RETURNED)
    for stage_id in qs.values_list("stage_id", flat=True):
        counts[stage_id] = counts.get(stage_id, 0) + 1
    return counts


def teacher_comments(enrollment, limit=3):
    """Latest submissions the teacher wrote a comment on."""
    return (
        PracticeSubmission.objects.filter(enrollment=enrollment)
        .exclude(teacher_comment="")
        .select_related("stage__topic__module__course", "graded_by")
        .order_by("-updated_at", "-pk")[:limit]
    )
