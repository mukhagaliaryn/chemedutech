"""Notification pages shared by every cabinet (the nav badge polls ``badge`` every 60 s)."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from apps.core.permissions import ADMIN, TEACHER, has_role

from . import selectors, services


def _layout(user):
    return "layouts/teacher.html" if has_role(user, TEACHER, ADMIN) else "layouts/student.html"


@login_required
def notifications(request):
    page = Paginator(selectors.recent(request.user), 30).get_page(request.GET.get("page"))
    return render(
        request,
        "feedback/notifications.html",
        {"layout": _layout(request.user), "page": page, "unread": selectors.unread_count(request.user)},
    )


@login_required
def open_notification(request, pk):
    """Mark as read and follow the link (only links inside the site)."""
    notification = services.mark_read(request.user, pk)
    url = notification.url if notification else ""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return redirect(url)
    return redirect("feedback:notifications")


@require_POST
@login_required
def read_all(request):
    services.mark_all_read(request.user)
    if request.htmx:
        return menu(request)
    return redirect("feedback:notifications")


@login_required
def menu(request):
    """The Topbar dropdown: the last notifications (HTMX, loaded on open)."""
    return render(
        request,
        "feedback/partials/menu.html",
        {"items": selectors.recent(request.user, 6), "unread": selectors.unread_count(request.user)},
    )


@require_GET
@login_required
def badge(request):
    return render(request, "feedback/partials/badge.html", {"unread": selectors.unread_count(request.user)})
