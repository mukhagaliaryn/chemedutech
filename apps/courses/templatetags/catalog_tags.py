"""Tags for the public landing page (core/home.html): real numbers instead of marketing copy."""

from django import template
from django.utils.safestring import mark_safe

from apps.labs.engine import all_labs

from ..models import Course, Module, Topic

register = template.Library()


@register.simple_tag
def landing_facts():
    """{modules, topics, experiments, lab: {title, experiments: [...]}} for the published courses and code labs."""
    published = Course.objects.filter(status=Course.Status.PUBLISHED)
    labs = list(all_labs().values())
    showcase = labs[0] if labs else None
    return {
        "modules": Module.objects.filter(course__in=published).count(),
        "topics": Topic.objects.filter(module__course__in=published).count(),
        "experiments": sum(len(lab.experiments) for lab in labs),
        "lab": {
            "title": showcase.title,
            "topic_number": showcase.topic_number,
            "experiments": [
                {
                    "number": exp.number,
                    "title": exp.title,
                    "goal": exp.goal,
                    "equation": mark_safe(exp.equation),  # trusted HTML from the code spec (sub/sup)
                    "steps": len(exp.steps),
                    "items": [item.name for item in exp.items if item.required][:4],
                    "journal": len(exp.journal),
                }
                for exp in showcase.experiments
            ],
        }
        if showcase
        else None,
    }
