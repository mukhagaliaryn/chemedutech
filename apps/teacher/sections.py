"""Teacher: one page per ICPAI section (STEP-41), opened from the sidebar like the student's sections. Each page shows
the section's purpose (the guide's text), the active group's figures (passed, mean percent, works waiting) and the
students' progress in it, then what belongs to the section: 1 — the course, 2 — the diagnostics I/II/III, 3 — the
video watched, 4 — the template lessons, 5–8 — the review queue (8 — with the group's dates). Reads, except the
section 8 dates and the active group choice."""

from collections import defaultdict

from django.contrib import messages
from django.db.models import Avg, Count, Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.pedagogy.models import Lesson, LessonTemplate, Review
from apps.programme import selectors as programme_selectors
from apps.programme.models import (
    DiagnosticResult,
    Portfolio,
    ProgrammeEnrollment,
    Section,
    SectionProgress,
    SectionSchedule,
    SectionVideo,
    VideoWatch,
)
from apps.programme.services import schedule as schedule_services

from . import icpai, practice, scope
from .views import teacher_only

S = SectionProgress.Status
QUEUES = {v: k for k, v in practice.WHAT_KINDS.items()}  # section kind → the queue's name
PHASES = ("I", "II", "III")


@require_POST
@teacher_only
def set_group(request):
    """The sidebar's group picker: one of the teacher's groups, or all of them."""
    scope.set_group(request, request.POST.get("group", ""))
    back = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = "/teacher/"
    return redirect(back)


def _figures(section, students, progress) -> dict:
    marks = [progress.get(s.pk) for s in students]
    passed = sum(1 for m in marks if m and m.status == S.PASSED)
    return {
        "total": len(students),
        "passed": passed,
        "share": passed * 100 / len(students) if students else 0,
        "mean": sum(float(m.percent) for m in marks if m) / len(students) if students else 0,
        "opened": sum(1 for m in marks if m and m.status != S.LOCKED),
    }


def _course(request, section, students, rows) -> dict:
    from apps.courses.models import Enrollment

    course = section.programme.course
    enrolled = {e.student_id: e for e in Enrollment.objects.filter(course=course, student__in=students)}
    for r in rows:
        r["enrollment"] = enrolled.get(r["student"].pk)
    return {"course": course}


def _diagnostic(request, section, students, rows) -> dict:
    summaries = programme_selectors.diagnostic_summaries(section.programme, students)
    for r in rows:
        mine = summaries.get(r["student"].pk, {})
        r["phases"] = [{"phase": p, "summary": mine.get(p)} for p in PHASES]
    means = defaultdict(dict)
    for row in (
        DiagnosticResult.objects.filter(enrollment__programme=section.programme, enrollment__student__in=students)
        .values("component", "phase")
        .annotate(mean=Avg("percent"), n=Count("pk"))
    ):
        means[row["component"]][row["phase"]] = {"mean": float(row["mean"]), "n": row["n"]}
    return {
        "phases": PHASES,
        "components": [
            {"label": label, "cells": [means[c].get(p) for p in PHASES]}
            for c, label in programme_selectors.COMPONENT_LABELS
        ],
    }


def _video(request, section, students, rows) -> dict:
    watched = dict(
        VideoWatch.objects.filter(section=section, enrollment__student__in=students).values_list(
            "enrollment__student", "percent"
        )
    )
    for r in rows:
        r["watched"] = watched.get(r["student"].pk)
    return {"video": SectionVideo.objects.filter(section=section).first()}


def _designer(request, section, students, rows) -> dict:
    templates = list(LessonTemplate.objects.filter(is_active=True).order_by("number"))
    lessons = defaultdict(dict)
    for x in Lesson.objects.filter(kind=Lesson.Kind.TEMPLATE_COPY, owner__in=students).annotate(
        n_trials=Count("trials", distinct=True)
    ):
        lessons[x.owner_id][x.source_template_id] = x
    for r in rows:
        r["lessons"] = [{"template": t, "lesson": lessons[r["student"].pk].get(t.pk)} for t in templates]
    final = defaultdict(int)
    for per in lessons.values():
        for template_id, x in per.items():
            final[template_id] += x.status == Lesson.Status.FINAL
    return {"templates": [{"template": t, "final": final[t.pk]} for t in templates]}


def _graded_lessons(students, kind) -> dict:
    """{owner: {"lessons": n, "final": n, "best": grade}} of one kind of lesson."""
    out = defaultdict(lambda: {"lessons": 0, "final": 0, "best": None, "latest": None})
    for x in Lesson.objects.filter(kind=kind, owner__in=students).order_by("cycle", "pk"):
        row = out[x.owner_id]
        row["lessons"] += 1
        row["final"] += x.status == Lesson.Status.FINAL
        row["latest"] = x
    for owner, best in (
        Review.objects.filter(lesson__kind=kind, lesson__owner__in=students)
        .values_list("lesson__owner")
        .annotate(best=Max("total"))
    ):
        out[owner]["best"] = best
    return out


def _queue(request, section, students, rows) -> dict:
    what = QUEUES[section.kind]
    show = "graded" if request.GET.get("show") == "graded" else "new"
    ids = [s.pk for s in students]
    queue = practice.queue_rows(request, what, show, ids)
    if "show" not in request.GET and not queue["new"] and queue["graded"]:  # nothing waiting: show the graded ones
        show = "graded"
        queue = practice.queue_rows(request, what, show, ids)
    context = {"what": what, "show": show, "queue_rows": queue["rows"], "new": queue["new"], "graded": queue["graded"]}
    if what == "portfolio":
        portfolios = {p.enrollment.student_id: p for p in Portfolio.objects.filter(
            enrollment__programme=section.programme, enrollment__student__in=students).select_related("enrollment")}  # fmt: skip
        for r in rows:
            r["portfolio"] = portfolios.get(r["student"].pk)
    else:
        kind = {"practice": Lesson.Kind.RESEARCH_PRACTICE, "micro": Lesson.Kind.MICROLESSON,
                "independent": Lesson.Kind.INDEPENDENT}[what]  # fmt: skip
        per = _graded_lessons(students, kind)
        for r in rows:
            r["work"] = per.get(r["student"].pk)
    if what == "independent":
        groups = [scope.active_group(request)] if scope.active_group(request) else scope.groups(request)
        schedules = {s.group_id: s for s in SectionSchedule.objects.filter(section=section)}
        context["schedule_rows"] = [{"group": g, "schedule": schedules.get(g.pk)} for g in groups]
    return context


BUILDERS = {
    Section.Kind.COURSE: _course,
    Section.Kind.DIAGNOSTIC: _diagnostic,
    Section.Kind.VIDEO: _video,
    Section.Kind.DESIGNER: _designer,
}


@teacher_only
def section(request, number):
    programme = icpai._programme(request.user)
    if programme is None:
        raise Http404
    item = get_object_or_404(programme.sections, number=number)
    if request.method == "POST" and item.kind == Section.Kind.INDEPENDENT:
        return _save_schedule(request, item)
    students = scope.student_list(request)
    joined = {e.student_id: e for e in ProgrammeEnrollment.objects.filter(programme=programme, student__in=students)}
    progress = {
        p.enrollment.student_id: p
        for p in SectionProgress.objects.filter(section=item, enrollment__student__in=students).select_related(
            "enrollment"
        )
    }
    rows = [{"student": s, "joined": joined.get(s.pk), "progress": progress.get(s.pk)} for s in students]
    builder = BUILDERS.get(item.kind, _queue)
    extra = builder(request, item, students, rows)
    return render(request, "teacher/sections/section.html", {
        "programme": programme, "section": item, "rows": rows, "figures": _figures(item, students, progress),
        "group": scope.active_group(request), "waiting": extra.get("new") if builder is _queue else None, **extra,
    })  # fmt: skip


def _save_schedule(request, item):
    group = next((g for g in scope.groups(request) if str(g.pk) == request.POST.get("group")), None)
    if group:
        schedule_services.set_schedule(
            item, group, request.user,
            hand_in_on=parse_date(request.POST.get("hand_in_on") or "") or None,
            trial_on=parse_date(request.POST.get("trial_on") or "") or None,
        )  # fmt: skip
        messages.success(request, _("The dates are saved; the students are notified."))
    return redirect("teacher:section", item.number)
