"""Tags for the student cabinet shell (layouts/student.html)."""

from django import template

from apps.core.permissions import STUDENT, has_role
from apps.programme import selectors as programme_selectors

from .. import cabinet, learning
from ..learning import S

register = template.Library()


@register.simple_tag(takes_context=True)
def sidebar_topic(context):
    """{% sidebar_topic as card %} — the «current topic» card of the sidebar, or None.

    {topic, passed, required, percent, url}: the topic of the next open stage in the most recent course.
    Computed once per request.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not has_role(user, STUDENT):
        return None
    if not hasattr(request, "_sidebar_topic"):
        request._sidebar_topic = _current_topic(user)
    return request._sidebar_topic


def _current_topic(user):
    enrollments = cabinet.enrollments_of(user)
    if not enrollments:
        return None
    place = cabinet.place_of(enrollments[0])
    stage = learning.continue_target(place)
    if stage is None:
        return None
    required = [s for s in learning.ordered_stages(stage.topic) if s.is_required]
    passed = sum(1 for s in required if learning.stage_status(place, s) == S.PASSED)
    return {
        "topic": stage.topic,
        "passed": passed,
        "required": len(required),
        "percent": round(100 * passed / len(required)) if required else 0,
        "url": learning.stage_url(stage),
    }


@register.simple_tag(takes_context=True)
def sidebar_sections(context):
    """{% sidebar_sections as nav %} — the ICPAI sections of the sidebar, or None when the student is in no programme.

    {rows: programme.selectors.section_rows, current: number of the section page open now}. Reads the stored
    state (the programme pages recalculate it); computed once per request.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not has_role(user, STUDENT):
        return None
    if not hasattr(request, "_sidebar_sections"):
        enrollment = programme_selectors.current_enrollment(user)
        request._sidebar_sections = {"rows": programme_selectors.section_rows(enrollment)} if enrollment else None
    nav = request._sidebar_sections
    if nav:
        match = getattr(request, "resolver_match", None)
        nav["current"] = match.kwargs.get("number") if match and match.view_name == "student:section" else None
    return nav
