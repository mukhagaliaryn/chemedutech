"""Helpers for the component templates in ui/templates/components/ (registered as a builtin)."""

from django import template
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from apps.core.html import clean_html
from apps.feedback import selectors as notification_selectors

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
    """Render a form field's widget with design-system classes and aria-invalid on errors.

    The widget's own classes stay (CKEditor 5 finds its textarea by «django_ckeditor_5»)."""
    own = bound_field.field.widget.attrs.get("class", "")
    attrs = {"class": f"{own} {css}".strip()}
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


@register.filter
def chem(text):
    """{{ "Zn + 2HCl -> ZnCl2 + H2"|chem }} → "Zn + 2HCl → ZnCl₂ + H₂" (unreadable input is shown as typed)."""
    from apps.assessments.chem import ChemError, parse_equation, pretty_formula

    text = str(text or "")
    try:
        return parse_equation(text).pretty()
    except ChemError:
        pass
    try:
        return pretty_formula(text)
    except ChemError:
        return text


@register.simple_tag(takes_context=True)
def unread_notifications(context):
    """{% unread_notifications as n %} — the signed-in user's unread count for the nav badge."""
    request = context.get("request")
    return notification_selectors.unread_count(request.user) if request else 0


@register.filter
def ago(moment):
    """«just now», «5 min ago», «3 h ago», then the date (Django's timesince has no full kk translation)."""
    if not moment:
        return ""
    seconds = (timezone.now() - moment).total_seconds()
    if seconds < 60:
        return _("just now")
    if seconds < 3600:
        return _("%(n)s min ago") % {"n": int(seconds // 60)}
    if seconds < 86400:
        return _("%(n)s h ago") % {"n": int(seconds // 3600)}
    return date_format(timezone.localtime(moment), "j E, H:i")


@register.filter
def seconds(ms):
    """Milliseconds from the start → «1:05.3» (m:ss.s) for the lab log."""
    try:
        total = int(ms) / 1000
    except (TypeError, ValueError):
        return ""
    minutes, secs = divmod(total, 60)
    return f"{int(minutes)}:{secs:04.1f}"


@register.filter
def duration_s(value):
    """Seconds → «4:05» (m:ss) or «1:02:05»."""
    try:
        total = int(value)
    except (TypeError, ValueError):
        return ""
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


@register.filter
def lab_variant(status):
    """Lab attempt status → badge variant."""
    return {"analysed": "success", "finished": "info", "in_progress": "neutral"}.get(str(status), "neutral")


@register.filter
def grade_variant(letter):
    """KZ letter grade → badge variant (A success, B info, C neutral, D warning, F danger)."""
    return {"A": "success", "B": "info", "C": "neutral", "D": "warning", "F": "danger"}.get(str(letter)[:1], "neutral")
