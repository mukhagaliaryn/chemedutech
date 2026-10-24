"""Teacher cabinet: dashboard, groups and students (ARCHITECTURE §8, STEP-10).

Thin views: every object is looked up through courses.selectors.teaching, so a teacher can never open
another teacher's group or student (404). Writes go through courses.services / progress.services.
"""

import csv

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from apps.core.permissions import ADMIN, TEACHER, role_required
from apps.courses import selectors as course_selectors
from apps.courses import services as course_services
from apps.courses.models import CourseGroup, Stage, Topic
from apps.feedback import selectors as feedback_selectors
from apps.feedback import services as feedback
from apps.labs import selectors as lab_selectors
from apps.labs.models import LabAttempt
from apps.programme import selectors as programme_selectors
from apps.programme import services as programme
from apps.programme.models import Section
from apps.progress import services as progress

from . import overview
from .forms import AddStudentForm, AttachCourseForm, CohortForm, GroupForm

teacher_only = role_required(TEACHER, ADMIN)


def _group(request, pk):
    return get_object_or_404(course_selectors.teacher_groups(request.user), pk=pk)


def _student(request, pk):
    return get_object_or_404(course_selectors.teacher_students(request.user).select_related("student_profile"), pk=pk)


# --- dashboard ---------------------------------------------------------------------------


@teacher_only
def dashboard(request):
    context = overview.dashboard(request.user)
    context["group_form"] = GroupForm(request.user)  # «Create a group» dialog
    return render(request, "teacher/dashboard.html", context)


# --- groups --------------------------------------------------------------------------------


GROUP_STATUSES = ("active", "inactive", "all")


@teacher_only
def groups(request):
    """The list archetype: search by name, status chips (with counts), research group filter."""
    q = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status") or ("all" if request.GET.get("all") == "1" else "active")
    status = status if status in GROUP_STATUSES else "active"
    cohort = request.GET.get("cohort", "")
    base = course_selectors.teacher_groups(request.user)
    if q:
        base = base.filter(name__icontains=q)
    if cohort in ("experimental", "control", "none"):
        base = base.filter(research_cohort="" if cohort == "none" else cohort)
    counts = {
        "active": base.filter(is_active=True).count(),
        "inactive": base.filter(is_active=False).count(),
        "all": base.count(),
    }
    qs = base.order_by("-is_active", "name")
    if status != "all":
        qs = qs.filter(is_active=status == "active")
    enrollments = course_selectors.teacher_enrollments(request.user).select_related("student__student_profile")
    rows = overview.student_rows(enrollments)
    no_group = {
        r["student"].pk
        for r in rows
        if not getattr(r["student"], "student_profile", None) or not r["student"].student_profile.group_id
    }
    return render(
        request,
        "teacher/groups.html",
        {
            "groups": overview.group_summaries(qs, rows),
            "q": q,
            "status": status,
            "cohort": cohort,
            "counts": counts,
            "filtered": bool(q or cohort or status != "active"),
            "keep_filters": [("status", status), ("cohort", cohort)],
            "no_group": len(no_group),
        },
    )


@teacher_only
def group_edit(request, pk=None):
    group = _group(request, pk) if pk else None
    form = GroupForm(request.user, request.POST or None, instance=group)
    if request.method == "POST" and form.is_valid():
        group = course_services.save_group(request.user, form.cleaned_data, group=group)
        messages.success(request, _("The group is saved."))
        return redirect("teacher:group", group.pk)
    return render(request, "teacher/group_form.html", {"form": form, "group": group})


@require_POST
@teacher_only
def group_delete(request, pk):
    group = _group(request, pk)
    try:
        course_services.delete_group(group)
    except course_services.GroupError as exc:
        messages.error(request, str(exc))
        return redirect("teacher:group", group.pk)
    messages.success(request, _("The group is deleted."))
    return redirect("teacher:groups")


def _group_rows(request, group, course):
    """Rows for the members' enrolments in ``course`` + members not enrolled in it."""
    enrollments = course_selectors.teacher_enrollments(request.user, course).filter(
        student__student_profile__group=group
    )
    rows = overview.student_rows(enrollments.select_related("student__student_profile"))
    enrolled = {r["student"].pk for r in rows}
    missing = [m for m in course_selectors.group_members(group) if m.pk not in enrolled]
    rows.sort(key=lambda r: (r["student"].last_name, r["student"].first_name, r["student"].username))
    return rows, missing


@teacher_only
def group(request, pk):
    group = _group(request, pk)
    links = list(course_selectors.group_courses(group))
    visible = set(course_selectors.teacher_courses(request.user).values_list("pk", flat=True))
    courses = [link.course for link in links if link.course.pk in visible]
    course = next((c for c in courses if c.slug == request.GET.get("course")), courses[0] if courses else None)
    rows, missing = _group_rows(request, group, course) if course else ([], list(course_selectors.group_members(group)))
    q, show = request.GET.get("q", ""), request.GET.get("show", "")
    shown = overview.filter_rows(rows, q, show)
    counts = {
        "all": len(rows) + len(missing),
        "attention": len(overview.filter_rows(rows, "", "attention")),
        "inactive": len(overview.filter_rows(rows, "", "inactive")),
    }
    if request.GET.get("format") == "csv":
        return _group_csv(group, course, rows)
    sections, matrix = _sections_matrix(course, shown)
    return render(
        request,
        "teacher/group.html",
        {
            "programme": programme_selectors.programme_of_course(course),
            "sections": sections,
            "matrix": matrix,
            "group": group,
            "links": links,
            "courses": courses,
            "course": course,
            "rows": shown,
            "rows_total": len(rows),
            "missing": missing if not q and not show else [],
            "members": len(rows) + len(missing),
            "q": q,
            "show": show,
            "counts": counts,
            "keep_filters": [("course", course.slug if course else ""), ("show", show)],
            "add_form": AddStudentForm(),
            "attach_form": AttachCourseForm(request.user, group),
        },
    )


def _sections_matrix(course, rows):
    """ICPAI students × sections for the shown rows (recalculated so the teacher sees fresh percents)."""
    found = programme_selectors.programme_of_course(course)
    if found is None or not rows:
        return [], []
    for r in rows:
        for enrollment in programme.join(r["enrollment"]):
            programme.recalculate(enrollment)
    return programme_selectors.matrix(found, [r["student"] for r in rows])


def _group_csv(group, course, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = f'attachment; filename="group_{group.pk}_{stamp}.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(
        ["student", "username", "email", "group", "course", "now", "stages_passed", "stages_total", "current_score",
         "order_errors", "safety_warnings", "wrong_choices", "last_activity", "attention"]
    )  # fmt: skip
    for r in rows:
        errors = r["errors"] or {}
        writer.writerow(
            [
                r["student"].full_name, r["student"].username, r["student"].email, group.name,
                course.slug if course else "", r["position"]["text"], r["passed"], r["total"],
                r["score"] if r["score"] is not None else "", errors.get("order", 0), errors.get("safety", 0),
                errors.get("wrong", 0), timezone.localtime(r["last"]).isoformat() if r["last"] else "",
                "; ".join(r["attention"]),
            ]
        )  # fmt: skip
    return response


@require_POST
@teacher_only
def group_cohort(request, pk):
    group = _group(request, pk)
    form = CohortForm(request.POST)
    if form.is_valid():
        cohort = form.cleaned_data["research_cohort"]
        keep = course_services.cohort_conflicts(group, cohort)
        filled = course_services.set_research_cohort(group, cohort)
        messages.success(request, _("The research group is saved."))
        if filled:
            messages.info(
                request,
                ngettext("%(n)s enrolment got it now.", "%(n)s enrolments got it now.", filled) % {"n": filled},
            )
        if keep:
            messages.warning(
                request,
                ngettext(
                    "%(n)s enrolment keeps its earlier research group (the research snapshot).",
                    "%(n)s enrolments keep their earlier research group (the research snapshot).",
                    keep,
                )
                % {"n": keep},
            )
    return redirect("teacher:group", group.pk)


@require_POST
@teacher_only
def group_add_student(request, pk):
    group = _group(request, pk)
    form = AddStudentForm(request.POST)
    if form.is_valid():
        student = course_services.find_student(form.cleaned_data["query"])
        if student is None:
            messages.error(request, _("No student account with this username or email."))
        else:
            try:
                added = course_services.add_student(request.user, group, student)
            except course_services.GroupError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, _("%(name)s is added to the group.") % {"name": student.full_name})
                if added:
                    messages.info(
                        request,
                        ngettext(
                            "Enrolled in %(n)s course of the group.", "Enrolled in %(n)s courses of the group.", added
                        )
                        % {"n": added},
                    )
    return redirect("teacher:group", group.pk)


@require_POST
@teacher_only
def group_remove_student(request, pk, student_pk):
    group = _group(request, pk)
    student = get_object_or_404(course_selectors.group_members(group), pk=student_pk)
    try:
        course_services.remove_student(group, student)
    except course_services.GroupError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, _("%(name)s is removed from the group. Courses and progress stay.") % {"name": student.full_name}
        )
    return redirect("teacher:group", group.pk)


@require_POST
@teacher_only
def group_join_code(request, pk):
    group = _group(request, pk)
    course_services.new_join_code(group)
    messages.success(request, _("A new join code is made; the old one no longer works."))
    return redirect("teacher:group", group.pk)


@require_POST
@teacher_only
def group_attach(request, pk):
    group = _group(request, pk)
    form = AttachCourseForm(request.user, group, request.POST)
    if form.is_valid():
        data = form.cleaned_data
        course_services.attach_course(group, data["course"], request.user, data["starts_on"], data["ends_on"])
        messages.success(request, _("The group is attached to the course; its students are enrolled."))
    else:
        messages.error(request, " ".join(e for errors in form.errors.values() for e in errors))
    return redirect("teacher:group", group.pk)


@require_POST
@teacher_only
def group_detach(request, pk, link_pk):
    group = _group(request, pk)
    link = get_object_or_404(
        CourseGroup, pk=link_pk, group=group, course__in=course_selectors.teacher_courses(request.user)
    )
    course_services.detach_course(link)
    messages.success(request, _("The group is detached. Enrolled students keep the course and progress."))
    return redirect("teacher:group", group.pk)


@require_POST
@teacher_only
def group_posttest(request, pk, link_pk):
    """Open / close the course's post-test for the group before everybody has finished the course."""
    group = _group(request, pk)
    link = get_object_or_404(
        CourseGroup, pk=link_pk, group=group, course__in=course_selectors.teacher_courses(request.user)
    )
    is_open = request.POST.get("open") == "1"
    course_services.set_posttest_open(link, is_open)
    if is_open:
        messages.success(request, _("The final knowledge test is open for the group."))
    else:
        messages.info(request, _("The final knowledge test is closed; it opens for each student after the course."))
    return redirect("teacher:group", group.pk)


# --- students --------------------------------------------------------------------------------


@teacher_only
def students(request):
    q = request.GET.get("q", "").strip()
    qs = course_selectors.teacher_students(request.user).select_related("student_profile__group")
    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(last_name__icontains=q) | Q(first_name__icontains=q)
        )
    no_group = request.GET.get("no_group") == "1"
    counts = {"all": qs.count(), "no_group": qs.filter(student_profile__group=None).count()}
    if no_group:
        qs = qs.filter(student_profile__group=None)
    return render(
        request,
        "teacher/students.html",
        {
            "students": qs.order_by("last_name", "first_name", "username")[:200],
            "q": q,
            "no_group": no_group,
            "counts": counts,
            "keep_filters": [("no_group", "1" if no_group else "")],
        },
    )


@teacher_only
def search(request):
    """Topbar search: students, groups and topics of the teacher's courses."""
    q = request.GET.get("q", "").strip()[:100]
    context = {"search_q": q, "students": [], "groups": [], "topics": []}
    if q:
        context["students"] = (
            course_selectors.teacher_students(request.user)
            .filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(last_name__icontains=q)
                | Q(first_name__icontains=q)
            )
            .select_related("student_profile__group")
            .order_by("last_name", "first_name")[:20]
        )
        context["groups"] = (
            course_selectors.teacher_groups(request.user).filter(name__icontains=q).order_by("name")[:10]
        )
        context["topics"] = (
            Topic.objects.filter(module__course__in=course_selectors.teacher_courses(request.user), title__icontains=q)
            .select_related("module__course")
            .order_by("module__course__title", "number")[:20]
        )
    return render(request, "teacher/search.html", context)


def _enrollment(request, student):
    enrollments = list(
        course_selectors.teacher_enrollments(request.user).filter(student=student).order_by("course__title")
    )
    slug = request.GET.get("course") or request.POST.get("course")
    chosen = next((e for e in enrollments if e.course.slug == slug), enrollments[0] if enrollments else None)
    return enrollments, chosen


@teacher_only
def student(request, pk):
    student = _student(request, pk)
    enrollments, enrollment = _enrollment(request, student)
    context = {"student": student, "enrollments": enrollments, "enrollment": enrollment}
    if enrollment:
        progress.recalculate(enrollment)
        context.update(overview.student_page(enrollment))
    return render(request, "teacher/student.html", context)


@teacher_only
def student_drawer(request, pk):
    """HTMX: the student's short profile for the drawer of the group page (figures and the latest events)."""
    student = _student(request, pk)
    _enrollments, enrollment = _enrollment(request, student)
    context = {"student": student, "enrollment": enrollment}
    group_pk = request.GET.get("group", "")
    profile = getattr(student, "student_profile", None)
    if group_pk.isdigit() and profile and str(profile.group_id) == group_pk:
        context["group"] = course_selectors.teacher_groups(request.user).filter(pk=group_pk).first()
    if enrollment:
        context.update(
            row=overview.student_rows([enrollment])[0],
            time_spent=overview.time_spent(enrollment),
            events=list(overview.recent_events(enrollment, 6)),
        )
    return render(request, "teacher/partials/student_drawer.html", context)


@require_POST
@teacher_only
def unlock_stage(request, pk, stage_pk):
    student = _student(request, pk)
    _enrollments, enrollment = _enrollment(request, student)
    if enrollment is None:
        messages.error(request, _("The student is not enrolled in your course."))
        return redirect("teacher:student", student.pk)
    stage = get_object_or_404(Stage, pk=stage_pk, topic__module__course=enrollment.course)
    try:
        progress.unlock_stage(enrollment, stage, request.user)
    except progress.StageLocked:
        messages.error(request, _("This stage cannot be opened: its topic is not published."))
    else:
        messages.success(request, _("«%(stage)s» is open for the student.") % {"stage": stage.title})
    return redirect(f"{reverse('teacher:student', args=[student.pk])}?course={enrollment.course.slug}#stages")


@require_POST
@teacher_only
def unlock_section(request, pk, number):
    """Open an ICPAI section for one student by hand (logged), from the group page."""
    student = _student(request, pk)
    _enrollments, enrollment = _enrollment(request, student)
    found = programme_selectors.programme_of_course(enrollment.course) if enrollment else None
    back = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = reverse("teacher:student", args=[student.pk])
    if found is None:
        messages.error(request, _("The student's course is not part of a programme."))
        return redirect(back)
    section = get_object_or_404(Section, programme=found, number=number)
    enrollment = next(e for e in programme.join(enrollment) if e.programme_id == found.pk)
    programme.unlock_section(enrollment, section, request.user)
    messages.success(request, _("Section %(n)s is open for the student.") % {"n": section.number})
    return redirect(back)


@teacher_only
def lab_log(request, pk, attempt_pk):
    student = _student(request, pk)
    enrollments = course_selectors.teacher_enrollments(request.user).filter(student=student)
    attempt = get_object_or_404(LabAttempt.objects.select_related("stage"), pk=attempt_pk, enrollment__in=enrollments)
    attempt.title = overview.lab_title(attempt)
    feedback.mark_thread_read(request.user, attempt)
    return render(
        request,
        "teacher/lab_log.html",
        {
            "student": student,
            "attempt": attempt,
            "events": lab_selectors.events_of(attempt),
            "thread": feedback_selectors.thread(attempt),
            "comment_target": {"kind": "lab", "id": attempt.pk},
        },
    )
