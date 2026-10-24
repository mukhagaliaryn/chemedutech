"""Reads for the programme pages (no recalculation here — services.refresh does that)."""

__all__ = [
    "course_enrollment",
    "current_enrollment",
    "current_section",
    "matrix",
    "programme_of_course",
    "section_by_number",
    "section_rows",
]

from .models import Programme, ProgrammeEnrollment, Section, SectionProgress
from .providers import provider_for
from .providers.course import course_enrollment
from .services.engine import section_url


def current_enrollment(student) -> ProgrammeEnrollment | None:
    """The student's most recent enrolment in an active programme."""
    return (
        ProgrammeEnrollment.objects.filter(student=student, programme__is_active=True)
        .select_related("programme__course")
        .first()
    )


def programme_of_course(course) -> Programme | None:
    return Programme.objects.filter(course=course, is_active=True).first() if course else None


def section_by_number(programme, number) -> Section | None:
    return programme.sections.filter(number=number).first()


def section_rows(enrollment) -> list[dict]:
    """{section, progress, status, percent, ready, url} per section in order."""
    progress = {r.section_id: r for r in SectionProgress.objects.filter(enrollment=enrollment)}
    rows = []
    for section in enrollment.programme.sections.order_by("number", "pk"):
        row = progress.get(section.pk)
        rows.append(
            {
                "section": section,
                "progress": row,
                "status": row.status if row else SectionProgress.Status.LOCKED,
                "percent": row.percent if row else 0,
                "ready": provider_for(section).ready,
                "url": section_url(section),
            }
        )
    return rows


def current_section(rows) -> dict | None:
    """The row to continue with: the first open section that is not passed (else the last open one)."""
    open_rows = [r for r in rows if r["status"] != SectionProgress.Status.LOCKED]
    return next((r for r in open_rows if r["status"] != SectionProgress.Status.PASSED), None) or (
        open_rows[-1] if open_rows else None
    )


def matrix(programme, students) -> tuple[list[Section], list[dict]]:
    """Students × sections for the teacher's group page: (sections, [{student, enrollment, cells}])."""
    sections = list(programme.sections.order_by("number", "pk"))
    enrollments = {
        e.student_id: e for e in ProgrammeEnrollment.objects.filter(programme=programme, student__in=students)
    }
    progress: dict[int, dict[int, SectionProgress]] = {}
    for row in SectionProgress.objects.filter(enrollment__in=enrollments.values()):
        progress.setdefault(row.enrollment_id, {})[row.section_id] = row
    rows = []
    for student in students:
        enrollment = enrollments.get(student.pk)
        by_section = progress.get(enrollment.pk, {}) if enrollment else {}
        rows.append(
            {
                "student": student,
                "enrollment": enrollment,
                "cells": [{"section": s, "progress": by_section.get(s.pk)} for s in sections],
            }
        )
    return sections, rows
