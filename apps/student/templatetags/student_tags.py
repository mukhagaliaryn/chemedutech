"""Tags for the student cabinet shell (layouts/student.html)."""

from django import template

from apps.core.permissions import STUDENT, has_role

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
