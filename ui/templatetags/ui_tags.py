"""Helpers for the component templates in ui/templates/components/ (registered as a builtin)."""

from django import template
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe

from apps.core.html import clean_html

register = template.Library()

# Design-system status mapping, shared by badges, steppers and tables.
STATUS_VARIANTS = {
    "passed": "success",
    "completed": "success",
    "graded": "success",
    "in_progress": "info",
    "available": "info",
    "grading": "info",
    "awaiting_check": "warning",
    "needs_review": "warning",
    "submitted": "warning",
    "failed": "danger",
    "returned": "danger",
    "locked": "neutral",
}


@register.filter
def status_variant(status):
    """{{ stage.status|status_variant }} → success | info | warning | danger | neutral."""
    return STATUS_VARIANTS.get(str(status), "neutral")


@register.filter
def percent_of(value, maximum=100):
    """{{ 3|percent_of:5 }} → 60.0, clamped to 0..100. An empty maximum means 100."""
    if maximum in (None, ""):
        maximum = 100
    try:
        value, maximum = float(value), float(maximum)
    except (TypeError, ValueError):
        return 0
    if maximum <= 0:
        return 0
    return round(max(0.0, min(100.0, value / maximum * 100)), 1)


@register.filter
def initials(person):
    """User or plain name → up to two capital letters for the avatar."""
    if hasattr(person, "get_full_name"):
        name = person.get_full_name() or person.get_username()
    else:
        name = str(person or "")
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


@register.filter
def with_attrs(bound_field, css="input"):
    """Render a form field's widget with design-system classes and aria-invalid on errors."""
    attrs = {"class": css}
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
        attrs["aria-describedby"] = f"{bound_field.auto_id}_error"
    elif bound_field.help_text:
        attrs["aria-describedby"] = f"{bound_field.auto_id}_help"
    return bound_field.as_widget(attrs=attrs)


@register.filter
def widget_type(bound_field):
    """input_type of the widget ("text", "checkbox", "select", …) for component branching."""
    widget = bound_field.field.widget
    return getattr(widget, "input_type", None) or widget.__class__.__name__.lower()


@register.simple_tag(takes_context=True)
def nav_current(context, url_names):
    """aria-current="page" when the current view is one of the space-separated url names (or namespaces "ns:")."""
    match = getattr(context.get("request"), "resolver_match", None)
    if not match:
        return ""
    for name in url_names.split():
        if name == match.view_name or (name.endswith(":") and match.view_name.startswith(name)):
            return mark_safe('aria-current="page"')
    return ""


@register.simple_tag
def url_or_empty(name, *args):
    """{% url_or_empty "student:results" as href %} — "" for pages that are not built yet."""
    try:
        return reverse(name, args=args or None)
    except NoReverseMatch:
        return ""


@register.filter
def get_field(form, name):
    """{{ form|get_field:"email" }} — a BoundField by name (loops over a fixed field list)."""
    return form[name]


@register.filter
def sanitize(html):
    """{{ content.body|sanitize }} — CKEditor HTML made safe for students (nh3 allow-list)."""
    return mark_safe(clean_html(str(html or "")))  # cleaned by nh3 above
