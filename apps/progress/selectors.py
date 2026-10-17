from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from .models import CourseResult, ModuleResult, ProgressEvent, StageProgress, StudyDay, TopicResult


def stage_progress_map(enrollment) -> dict[int, StageProgress]:
    return {sp.stage_id: sp for sp in StageProgress.objects.filter(enrollment=enrollment)}


def topic_results_map(enrollment) -> dict[int, TopicResult]:
    return {r.topic_id: r for r in TopicResult.objects.filter(enrollment=enrollment)}


def module_results_map(enrollment) -> dict[int, ModuleResult]:
    return {r.module_id: r for r in ModuleResult.objects.filter(enrollment=enrollment)}


def time_spent_s(enrollment) -> int:
    return StageProgress.objects.filter(enrollment=enrollment).aggregate(t=Sum("time_spent_s"))["t"] or 0


def study_days(enrollment, days: int) -> dict:
    """{date: seconds} for the last ``days`` local days (today included); missing days are 0."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    found = dict(
        StudyDay.objects.filter(enrollment=enrollment, date__gte=start, date__lte=today).values_list("date", "seconds")
    )
    return {start + timedelta(days=i): found.get(start + timedelta(days=i), 0) for i in range(days)}


def active_students_by_day(enrollment_ids, days: int = 7) -> list[int]:
    """Students with study time on each of the last ``days`` local days (oldest first)."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    counts = dict(
        StudyDay.objects.filter(enrollment_id__in=enrollment_ids, date__gte=start, seconds__gt=0)
        .values("date")
        .annotate(n=Count("enrollment__student", distinct=True))
        .values_list("date", "n")
    )
    return [counts.get(start + timedelta(days=i), 0) for i in range(days)]


def study_streak(enrollment) -> int:
    """Days in a row with study time, ending today (or yesterday, if today has nothing yet)."""
    dates = set(StudyDay.objects.filter(enrollment=enrollment, seconds__gt=0).values_list("date", flat=True))
    day = timezone.localdate()
    if day not in dates:
        day -= timedelta(days=1)
    streak = 0
    while day in dates:
        streak += 1
        day -= timedelta(days=1)
    return streak


def stages_passed_since(enrollment, since) -> int:
    return StageProgress.objects.filter(
        enrollment=enrollment, status=StageProgress.Status.PASSED, completed_at__gte=since
    ).count()


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


def topic_results_by_enrollment(enrollment_ids) -> dict[int, dict[int, TopicResult]]:
    result = {pk: {} for pk in enrollment_ids}
    for r in TopicResult.objects.filter(enrollment_id__in=enrollment_ids):
        result[r.enrollment_id][r.topic_id] = r
    return result


def module_results_by_enrollment(enrollment_ids) -> dict[int, dict[int, ModuleResult]]:
    result = {pk: {} for pk in enrollment_ids}
    for r in ModuleResult.objects.filter(enrollment_id__in=enrollment_ids):
        result[r.enrollment_id][r.module_id] = r
    return result
