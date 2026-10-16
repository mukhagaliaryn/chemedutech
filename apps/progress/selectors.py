from .models import CourseResult, StageProgress, TopicResult


def stage_progress_map(enrollment) -> dict[int, StageProgress]:
    return {sp.stage_id: sp for sp in StageProgress.objects.filter(enrollment=enrollment)}


def topic_results_map(enrollment) -> dict[int, TopicResult]:
    return {r.topic_id: r for r in TopicResult.objects.filter(enrollment=enrollment)}


def course_result(enrollment) -> CourseResult | None:
    return CourseResult.objects.filter(enrollment=enrollment).first()


def needing_attention(course):
    """Stages passed only because the attempts ran out, or waiting for a teacher's check."""
    return (
        StageProgress.objects.filter(enrollment__course=course)
        .filter(needs_attention=True)
        .union(StageProgress.objects.filter(enrollment__course=course, status=StageProgress.Status.AWAITING_CHECK))
    )
