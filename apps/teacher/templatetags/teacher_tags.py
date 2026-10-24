"""Tags for the teacher cabinet shell (layouts/teacher.html)."""

from django import template
from django.db.models import Count

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


# the review pages of a section's works mark that section current in the sidebar
DETAIL_KINDS = {"teacher:practice": "research_practice", "teacher:micro": "microlesson",
                "teacher:portfolio": "portfolio", "teacher:independent": "independent"}  # fmt: skip


@register.simple_tag(takes_context=True)
def teacher_programme(context):
    """{% teacher_programme as nav %} — the ICPAI sections of the teacher's sidebar (STEP-41), or None without a
    programme: {programme, groups, group, rows: [{section, passed, total, share, waiting}], current}. The figures are
    the active group's (apps.teacher.scope); computed once per request."""
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not has_role(user, TEACHER, ADMIN):
        return None
    if not hasattr(request, "_teacher_programme"):
        request._teacher_programme = _programme_nav(request)
    nav = request._teacher_programme
    if nav:
        match = getattr(request, "resolver_match", None)
        name = match.view_name if match else ""
        nav["current"] = (
            match.kwargs.get("number")
            if name == "teacher:section"
            else next((r["section"].number for r in nav["rows"] if r["section"].kind == DETAIL_KINDS.get(name)), None)
        )
    return nav


def _programme_nav(request):
    from apps.programme.models import SectionProgress

    from .. import icpai, practice, scope

    programme = icpai._programme(request.user)
    if programme is None:
        return None
    ids = scope.student_ids(request)
    passed = dict(
        SectionProgress.objects.filter(
            enrollment__programme=programme, enrollment__student__in=ids, status=SectionProgress.Status.PASSED
        )
        .values_list("section")
        .annotate(n=Count("pk"))
    )
    waiting = practice.waiting_counts(request, ids)
    kinds = {v: k for k, v in practice.WHAT_KINDS.items()}
    rows = []
    for section in programme.sections.order_by("number", "pk"):
        n = passed.get(section.pk, 0)
        rows.append({
            "section": section, "passed": n, "total": len(ids), "share": n * 100 / len(ids) if ids else 0,
            "waiting": waiting.get(kinds.get(section.kind), 0),
        })  # fmt: skip
    return {"programme": programme, "groups": scope.groups(request), "group": scope.active_group(request), "rows": rows}
