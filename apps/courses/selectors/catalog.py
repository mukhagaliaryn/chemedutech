from django.db.models import QuerySet

from apps.core.permissions import ADMIN, TEACHER, has_role

from ..models import Course, Topic


def open_courses() -> QuerySet[Course]:
    return Course.objects.filter(status=Course.Status.PUBLISHED, enrollment_mode=Course.EnrollmentMode.OPEN)


def courses_for(user) -> QuerySet[Course]:
    """Courses a user may open: admins — all; teachers — the ones they teach; students — their enrolments."""
    if has_role(user, ADMIN):
        return Course.objects.all()
    if has_role(user, TEACHER):
        return Course.objects.filter(course_teachers__teacher=user).distinct()
    return Course.objects.filter(
        enrollments__student=user, status__in=(Course.Status.PUBLISHED, Course.Status.ARCHIVED)
    ).distinct()


def topic_by_number(user, course_slug: str, number: int) -> Topic | None:
    topic = (
        Topic.objects.select_related("module__course")
        .filter(module__course__in=courses_for(user), module__course__slug=course_slug, number=number)
        .first()
    )
    if topic and not topic.is_published and not has_role(user, TEACHER, ADMIN):
        return None
    return topic


def topic_for_lab(lab_key: str) -> Topic | None:
    """The (first) topic whose lab stage uses this lab — for the lab page's «back to the topic» link."""
    return (
        Topic.objects.filter(stages__lab_content__lab_key=lab_key)
        .select_related("module__course")
        .order_by("module__course", "number")
        .first()
    )
