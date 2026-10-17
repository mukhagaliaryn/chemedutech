"""Tags for the teacher cabinet shell (layouts/teacher.html)."""

from django import template

from apps.core.permissions import ADMIN, TEACHER, has_role
from apps.courses import selectors as course_selectors
from apps.practice import selectors as practice_selectors

register = template.Library()


@register.simple_tag(takes_context=True)
def grading_pending(context):
    """{% grading_pending as n %} — practice works waiting for the teacher (needs_review) in their courses."""
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not has_role(user, TEACHER, ADMIN):
        return 0
    if not hasattr(request, "_grading_pending"):
        ids = list(course_selectors.teacher_enrollments(user).values_list("pk", flat=True))
        request._grading_pending = practice_selectors.grading_queue(ids).count() if ids else 0
    return request._grading_pending
