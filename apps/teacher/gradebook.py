"""Teacher: the gradebook — students × topics, CSV / XLSX export (STEP-11)."""

import csv

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import xlsx
from apps.courses import selectors as course_selectors

from . import overview
from .views import teacher_only


def _labels():
    return {
        "student": _("Student"),
        "username": _("Username"),
        "group": _("Group"),
        "cohort": _("Research group"),
        "topic": _("Topic"),
        "module": _("Module"),
        "current": _("Current score"),
        "final": _("Final score"),
        "letter": _("Letter"),
        "topics_completed": _("Topics completed"),
    }


@teacher_only
def gradebook(request, course_slug=None):
    courses = list(course_selectors.teacher_courses(request.user))
    if course_slug is None:
        if not courses:
            return render(request, "teacher/gradebook.html", {"courses": []})
        return redirect("teacher:gradebook_course", courses[0].slug)
    course = get_object_or_404(course_selectors.teacher_courses(request.user), slug=course_slug)
    enrollments = course_selectors.teacher_enrollments(request.user, course).select_related("student", "group")
    groups = (
        course_selectors.teacher_groups(request.user)
        .filter(pk__in=enrollments.exclude(group=None).values("group"))
        .order_by("name")
    )
    group = next((g for g in groups if str(g.pk) == request.GET.get("group")), None)
    if group is not None:
        enrollments = enrollments.filter(group=group)
    book = overview.gradebook(course, enrollments)
    fmt = request.GET.get("format")
    if fmt in ("csv", "xlsx"):
        table = overview.gradebook_table(book, _labels())
        stamp = timezone.localdate().isoformat()
        name = f"gradebook_{course.slug}{'_' + group.name if group else ''}_{stamp}"
        if fmt == "xlsx":
            response = HttpResponse(
                xlsx.build(table, sheet_name=group.name if group else course.slug), content_type=xlsx.CONTENT_TYPE
            )
        else:
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response.write("﻿")
            csv.writer(response).writerows(table)
        response["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
        return response
    return render(
        request,
        "teacher/gradebook.html",
        {"courses": courses, "course": course, "groups": groups, "group": group, **book},
    )
