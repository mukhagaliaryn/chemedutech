from django import template

register = template.Library()


@register.filter
def times(n):
    """{% for i in 6|times %} → 0..5 (Alpine's x-for does not work inside SVG)."""
    return range(int(n))


@register.filter
def split(value, sep=None):
    """{% for m in "0 50 100"|split %}"""
    return str(value).split(sep)


@register.filter
def get(mapping, key):
    """{{ titles|get:row.experiment_key }}"""
    return mapping.get(key, key) if hasattr(mapping, "get") else key
