from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _


@staff_member_required
def styleguide(request):
    """Every component from ui/templates/components with sample data (staff only)."""
    stages = [
        {"title": _("Theory"), "kind": "theory", "status": "passed", "meta": "100%", "url": "#"},
        {"title": _("Video lesson"), "kind": "video", "status": "passed", "meta": "75%", "url": "#"},
        {"title": _("Lab work"), "kind": "lab", "status": "in_progress", "meta": "2 / 4", "url": "#", "current": True},
        {"title": _("Practice 1"), "kind": "practice", "status": "awaiting_check", "url": "#"},
        {"title": _("Practice 2"), "kind": "practice", "status": "locked", "url": "#"},
        {"title": _("Practice 3"), "kind": "practice", "status": "locked"},
        {"title": _("Topic test"), "kind": "test", "status": "locked"},
    ]
    context = {
        "stages": stages,
        "statuses": ["passed", "in_progress", "awaiting_check", "failed", "locked"],
        "table_headers": [_("Student"), _("Group"), _("Score")],
        "table_rows": [["Айгерім Сапарова", "Хим-23-1", "84.6"], ["Нұрлан Әбенов", "Хим-23-1", "71.2"]],
        "select_options": [(1, "Хим-23-1"), (2, "Хим-23-2")],
    }
    return render(request, "ui/styleguide.html", context)
