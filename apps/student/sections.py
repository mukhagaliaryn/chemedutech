"""The ICPAI programme in the student cabinet (docs/icpai/SPEC.md §4.0, STEP-29): the home page with the guide
and the sections' state, and a page per section. Section 1 leads to the existing course pages."""

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.core.permissions import STUDENT, role_required
from apps.programme import selectors as programme_selectors
from apps.programme import services as programme
from apps.programme.models import Section, SectionProgress
from apps.progress import selectors as progress_selectors
from apps.progress.services import benchmark

from . import cabinet

LOCKED = SectionProgress.Status.LOCKED


def _course_block(enrollment) -> dict | None:
    """Section 1: the course enrolment's stages done and where to continue."""
    course_enrollment = programme_selectors.course_enrollment(enrollment)
    if course_enrollment is None:
        return None
    done, total = progress_selectors.required_stages_done(course_enrollment)
    place = cabinet.place_of(course_enrollment)
    return {
        "enrollment": course_enrollment,
        "course": course_enrollment.course,
        "done": done,
        "total": total,
        "card": cabinet.continue_card(place),
        "course_url": reverse("student:course", args=[course_enrollment.course.slug]),
    }


def home_context(user, enrollment) -> dict:
    """The programme home: the guide (sections with «what it does»), their state and «Continue»."""
    rows = programme_selectors.section_rows(enrollment)
    current = programme_selectors.current_section(rows)
    course = _course_block(enrollment)
    return {
        "programme": enrollment.programme,
        "rows": rows,
        "current": current,
        "continue_url": continue_url(current, course) if current else None,
        "passed_count": sum(1 for r in rows if r["status"] == SectionProgress.Status.PASSED),
        "course_block": course,
        "comments": cabinet.teacher_comments(course["enrollment"]) if course else [],
        "benchmark": benchmark.summary(course["enrollment"]) if course else {},
    }


@role_required(STUDENT)
def section(request, number):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, number=number)
    rows = programme_selectors.section_rows(enrollment)
    row = next(r for r in rows if r["section"].pk == section.pk)
    context = {"programme": enrollment.programme, "section": section, "row": row, "rows": rows}
    if row["status"] == LOCKED:
        blocking = programme.blocking_section(enrollment, section)
        context["blocking"] = next((r for r in rows if blocking and r["section"].pk == blocking.pk), None)
        return render(request, "student/section_locked.html", context)
    if section.kind == Section.Kind.COURSE:
        context["course_block"] = _course_block(enrollment)
    return render(request, "student/section.html", context)


def continue_url(row, course_block) -> str:
    """Where «Continue» leads for a section row: the next course stage for section 1, else the section page."""
    if row["section"].kind == Section.Kind.COURSE and course_block and course_block["card"]:
        return course_block["card"]["url"]
    return row["url"]
