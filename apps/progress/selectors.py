from django.db.models import Sum

from .models import CourseResult, ModuleResult, ProgressEvent, StageProgress, TopicResult


def stage_progress_map(enrollment) -> dict[int, StageProgress]:
    return {sp.stage_id: sp for sp in StageProgress.objects.filter(enrollment=enrollment)}


def topic_results_map(enrollment) -> dict[int, TopicResult]:
    return {r.topic_id: r for r in TopicResult.objects.filter(enrollment=enrollment)}


def module_results_map(enrollment) -> dict[int, ModuleResult]:
    return {r.module_id: r for r in ModuleResult.objects.filter(enrollment=enrollment)}


def time_spent_s(enrollment) -> int:
    return StageProgress.objects.filter(enrollment=enrollment).aggregate(t=Sum("time_spent_s"))["t"] or 0


def course_result(enrollment) -> CourseResult | None:
    return CourseResult.objects.filter(enrollment=enrollment).first()


def needing_attention(course):
    """Stages passed only because the attempts ran out, or waiting for a teacher's check."""
    return (
        StageProgress.objects.filter(enrollment__course=course)
        .filter(needs_attention=True)
        .union(StageProgress.objects.filter(enrollment__course=course, status=StageProgress.Status.AWAITING_CHECK))
    )


# --- many enrolments at once (teacher pages) -------------------------------------------


def stage_progress_by_enrollment(enrollment_ids) -> dict[int, dict[int, StageProgress]]:
    result = {pk: {} for pk in enrollment_ids}
    for sp in StageProgress.objects.filter(enrollment_id__in=enrollment_ids):
        result[sp.enrollment_id][sp.stage_id] = sp
    return result


def course_results_by_enrollment(enrollment_ids) -> dict[int, CourseResult]:
    return {r.enrollment_id: r for r in CourseResult.objects.filter(enrollment_id__in=enrollment_ids)}


def completed_topic_counts(enrollment_ids, topic) -> int:
    return TopicResult.objects.filter(
        enrollment_id__in=enrollment_ids, topic=topic, status=TopicResult.Status.COMPLETED
    ).count()


def events_of(enrollment, limit=50):
    return ProgressEvent.objects.filter(enrollment=enrollment).select_related("stage__topic", "topic", "actor")[:limit]


def last_progress_times(enrollment_ids) -> dict[int, object]:
    from django.db.models import Max

    rows = (
        StageProgress.objects.filter(enrollment_id__in=enrollment_ids)
        .exclude(started_at=None)
        .values("enrollment_id")
        .annotate(at=Max("updated_at"))
    )
    return {r["enrollment_id"]: r["at"] for r in rows}
