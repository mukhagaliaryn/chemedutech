"""Reads for the programme pages (no recalculation here — services.refresh does that)."""

from django.urls import reverse
from django.utils.translation import gettext as _

from apps.assessments.models import Component
from apps.pedagogy.models import Lesson, LessonTemplate, Trial
from apps.progress.models import CourseResult

from .models import DiagnosticResult, Portfolio, Programme, ProgrammeEnrollment, Section, SectionProgress, VideoWatch
from .providers import provider_for
from .providers.course import course_enrollment
from .services import diagnostics
from .services.engine import section_url

__all__ = [
    "COMPONENTS",
    "COMPONENT_LABELS",
    "component_dynamics",
    "course_enrollment",
    "current_enrollment",
    "current_section",
    "diagnostic_results_of_course",
    "diagnostic_rows",
    "diagnostic_summaries",
    "diagnostic_section",
    "matrix",
    "programme_of_course",
    "section_by_number",
    "section_facts",
    "section_rows",
]


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


def section_facts(enrollment) -> dict[int, list[tuple[str, str]]]:
    """Two short figures per section for the student's home cards: {number: [(value, label), …]}."""
    student = enrollment.student_id
    sections = {s.kind: s.number for s in enrollment.programme.sections.all()}
    templates = LessonTemplate.objects.filter(is_active=True).count()
    lessons = Lesson.objects.filter(owner_id=student)
    final = Lesson.Status.FINAL
    facts: dict[int, list[tuple[str, str]]] = {}

    def put(kind, *items):
        if kind in sections:
            facts[sections[kind]] = [item for item in items if item]

    course = course_enrollment(enrollment)
    result = CourseResult.objects.filter(enrollment=course).first() if course else None
    if result:
        score = f"{result.current_percent:.0f}" if result.current_percent is not None else "—"
        put("course", (f"{result.topics_completed}/{result.topics_total}", _("topics")), (score, _("score")))
    diagnostic = diagnostic_section(enrollment.programme)
    if diagnostic:
        tests = len(diagnostics.tests_of(diagnostic))
        put("diagnostic", (f"{len(diagnostics.done_phases(enrollment))}/{tests}", _("tests taken")))
    watch = VideoWatch.objects.filter(enrollment=enrollment).first()
    put("video", (f"{watch.percent if watch else 0}%", _("watched")))
    copies = lessons.filter(kind=Lesson.Kind.TEMPLATE_COPY)
    put("designer", (f"{copies.filter(status=final).count()}/{templates}", _("lessons")),
        (str(Trial.objects.filter(lesson__in=copies).count()), _("trials")))  # fmt: skip
    practices = lessons.filter(kind=Lesson.Kind.RESEARCH_PRACTICE)
    put("research_practice", (f"{practices.filter(status=final).count()}/{templates}", _("practices")),
        (str(Trial.objects.filter(lesson__in=practices).count()), _("trials")))  # fmt: skip
    micro = lessons.filter(kind=Lesson.Kind.MICROLESSON).first()
    put("microlesson", (str(micro.trials.count() if micro else 0), _("trials")),
        (_("assembled") if micro and micro.status == final else "—", _("microlesson")))  # fmt: skip
    folio = Portfolio.objects.filter(enrollment=enrollment).first()
    put("portfolio", (folio.get_status_display() if folio else "—", _("portfolio")))
    own = lessons.filter(kind=Lesson.Kind.INDEPENDENT)
    put("independent", (str(own.filter(status=final).count()), _("lessons confirmed")),
        (str(Trial.objects.filter(lesson__in=own).count()), _("trials")))  # fmt: skip
    return facts


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


# --- diagnostics (section 2, results page) -------------------------------------------------------

COMPONENTS = [c for c, _label in Component.choices]  # the guide's order: motivational, cognitive, activity, reflective
COMPONENT_LABELS = Component.choices


def diagnostic_section(programme) -> Section | None:
    return programme.sections.filter(kind=Section.Kind.DIAGNOSTIC).order_by("number").first()


def diagnostic_rows(enrollment, section) -> list[dict]:
    """Per stage I/II/III: {test, state, results (in component order), summary, url}."""
    tests = diagnostics.tests_of(section)
    done = diagnostics.done_phases(enrollment)
    results: dict[str, dict[str, DiagnosticResult]] = {}
    for r in DiagnosticResult.objects.filter(enrollment=enrollment):
        results.setdefault(r.phase, {})[r.component] = r
    rows = []
    for test in tests:
        by_component = results.get(test.phase, {})
        ordered = [by_component[c] for c in COMPONENTS if c in by_component]
        rows.append(
            {
                "test": test,
                "state": diagnostics.state(enrollment, test, tests, done),
                "results": ordered,
                "summary": diagnostics.summary(ordered) if ordered else None,
                "url": reverse("student:diagnostic", args=[section.number, test.phase]),
            }
        )
    return rows


def component_dynamics(enrollment) -> list[dict]:
    """The results page (guide @S7 II): per component {component, label, phases: {I: %, II: %, III: %}, latest}."""
    table = {c: {} for c in COMPONENTS}
    for r in DiagnosticResult.objects.filter(enrollment=enrollment):
        table[r.component][r.phase] = r.percent
    labels = dict(Component.choices)
    rows = []
    for component in COMPONENTS:
        phases = {p: table[component].get(p) for p in ("I", "II", "III")}  # None — not taken
        latest = next((phases[p] for p in ("III", "II", "I") if phases[p] is not None), None)
        rows.append({"component": component, "label": labels[component], "phases": phases, "latest": latest})
    return rows


def diagnostic_summaries(programme, students) -> dict[int, dict[str, dict]]:
    """{student_id: {phase: {earned, maximum, percent, level}}} — the teacher's group page."""
    rows: dict[tuple[int, str], list[DiagnosticResult]] = {}
    for r in DiagnosticResult.objects.filter(
        enrollment__programme=programme, enrollment__student__in=students
    ).select_related("enrollment"):
        rows.setdefault((r.enrollment.student_id, r.phase), []).append(r)
    out: dict[int, dict[str, dict]] = {}
    for (student_id, phase), results in rows.items():
        out.setdefault(student_id, {})[phase] = diagnostics.summary(results)
    return out


def diagnostic_results_of_course(course, students):
    """Every diagnostic result of the given students in the course's active programmes (analytics, CSV)."""
    return DiagnosticResult.objects.filter(
        enrollment__programme__course=course, enrollment__programme__is_active=True, enrollment__student__in=students
    ).select_related("enrollment__student", "enrollment__group", "attempt")
