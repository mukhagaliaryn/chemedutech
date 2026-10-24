"""The ICPAI section engine (docs/icpai/SPEC.md §3.1): sections open one after another, each when the previous
one reaches its pass mark (80 % by default); a teacher may open a section by hand. No signals: the product layer
calls ``refresh`` after the student's work and on the programme pages (like progress.services, D20/D29).
"""

from decimal import Decimal

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.permissions import STUDENT, has_role
from apps.courses.models import Enrollment
from apps.feedback import services as feedback

from ..models import Programme, ProgrammeEnrollment, Section, SectionEvent, SectionProgress, VideoWatch
from ..providers import provider_for

S = SectionProgress.Status
A = SectionEvent.Action


class SectionLocked(Exception):
    """The section is not open for this student yet."""


def _sections(programme) -> list[Section]:
    return list(programme.sections.order_by("number", "pk"))


def _clamp(value) -> Decimal:
    return min(max(Decimal(value or 0), Decimal(0)), Decimal(100))


def section_url(section) -> str:
    return reverse("student:section", args=[section.number])


# --- enrolments -----------------------------------------------------------------------


def join(course_enrollment) -> list[ProgrammeEnrollment]:
    """Programme enrolments for a course enrolment: one per active programme built on that course."""
    joined = []
    for programme in Programme.objects.filter(course_id=course_enrollment.course_id, is_active=True):
        enrollment, _created = ProgrammeEnrollment.objects.get_or_create(
            student_id=course_enrollment.student_id,
            programme=programme,
            defaults={"group_id": course_enrollment.group_id, "research_cohort": course_enrollment.research_cohort},
        )
        joined.append(enrollment)
    return joined


def sync_student(student) -> list[ProgrammeEnrollment]:
    """Join every active programme whose course the student is enrolled in; the student's programme enrolments."""
    if not has_role(student, STUDENT):
        return []
    course_enrollments = Enrollment.objects.filter(student=student, course__programmes__is_active=True).exclude(
        status=Enrollment.Status.DROPPED
    )
    for course_enrollment in course_enrollments.distinct():
        join(course_enrollment)
    return list(
        ProgrammeEnrollment.objects.filter(student=student, programme__is_active=True).select_related("programme")
    )


# --- the recalculation ----------------------------------------------------------------


def _ensure_rows(enrollment, sections) -> dict[int, SectionProgress]:
    rows = {r.section_id: r for r in SectionProgress.objects.filter(enrollment=enrollment)}
    missing = [SectionProgress(enrollment=enrollment, section=s) for s in sections if s.pk not in rows]
    if missing:
        SectionProgress.objects.bulk_create(missing, ignore_conflicts=True)
        rows = {r.section_id: r for r in SectionProgress.objects.filter(enrollment=enrollment)}
    return rows


def _notify_opened(student, sections) -> None:
    for section in sections:
        feedback.notify(student, feedback.Kind.SECTION, str(section), section_url(section))


@transaction.atomic
def recalculate(enrollment) -> list[SectionProgress]:
    """Ask every section's provider for its percent and re-derive the statuses in section order.

    A section is open when it is the first one, the previous one is passed, or a teacher opened it; an open
    section is passed at ``pass_percent``. Passed stays passed (a lower percent later is only logged).
    Returns the rows in section order.
    """
    enrollment = (
        ProgrammeEnrollment.objects.select_for_update().select_related("programme", "student").get(pk=enrollment.pk)
    )
    sections = _sections(enrollment.programme)
    rows = _ensure_rows(enrollment, sections)
    now = timezone.now()
    events, opened = [], []
    previous_passed = True
    for index, section in enumerate(sections):
        row = rows[section.pk]
        before = (row.status, row.percent)
        percent = _clamp(provider_for(section).percent(enrollment, section))
        if percent != row.percent:
            row.percent = percent
            events.append(SectionEvent(enrollment=enrollment, section=section, action=A.PERCENT, percent=percent))
        if row.status != S.PASSED:
            open_now = previous_passed or row.unlocked_by_id is not None
            if not open_now:
                row.status = S.LOCKED
            elif percent >= section.pass_percent:
                row.status = S.PASSED
            else:
                row.status = S.IN_PROGRESS if percent > 0 else S.AVAILABLE
            if row.status != S.LOCKED and row.opened_at is None:
                row.opened_at = now
                events.append(SectionEvent(enrollment=enrollment, section=section, action=A.OPENED))
                if index:  # the first section opens with the enrolment — nothing to announce
                    opened.append(section)
            if row.status == S.PASSED:
                row.passed_at = now
                events.append(SectionEvent(enrollment=enrollment, section=section, action=A.PASSED, percent=percent))
        if (row.status, row.percent) != before or row.opened_at == now:
            row.save(update_fields=["status", "percent", "opened_at", "passed_at", "updated_at"])
        previous_passed = row.status == S.PASSED

    SectionEvent.objects.bulk_create(events)
    done = bool(sections) and all(rows[s.pk].status == S.PASSED for s in sections)
    if done != (enrollment.completed_at is not None):
        enrollment.completed_at = now if done else None
        enrollment.save(update_fields=["completed_at", "updated_at"])
    if opened:
        student = enrollment.student
        transaction.on_commit(lambda: _notify_opened(student, opened))
    return [rows[s.pk] for s in sections]


def refresh(student) -> ProgrammeEnrollment | None:
    """Sync and recalculate the student's programme enrolments; the current one (the most recent) or None."""
    enrollments = sync_student(student)
    for enrollment in enrollments:
        recalculate(enrollment)
    return enrollments[0] if enrollments else None


# --- access ---------------------------------------------------------------------------


def _row(enrollment, section) -> SectionProgress | None:
    row = SectionProgress.objects.filter(enrollment=enrollment, section=section).first()
    if row is None and section.programme_id == enrollment.programme_id:
        recalculate(enrollment)
        row = SectionProgress.objects.filter(enrollment=enrollment, section=section).first()
    return row


def can_access(enrollment, section) -> bool:
    if enrollment is None or section.programme_id != enrollment.programme_id:
        return False
    row = _row(enrollment, section)
    return row is not None and row.is_open


def blocking_section(enrollment, section) -> Section | None:
    """The section to finish first to open ``section`` (for the lock page): the first earlier one not passed."""
    if can_access(enrollment, section):
        return None
    passed = set(
        SectionProgress.objects.filter(enrollment=enrollment, status=S.PASSED).values_list("section_id", flat=True)
    )
    return next((s for s in _sections(enrollment.programme) if s.number < section.number and s.pk not in passed), None)


@transaction.atomic
def record_watch(enrollment, section, percent: int) -> int:
    """The video player's report: keep the largest share watched, then recalculate. Returns the stored percent."""
    percent = max(0, min(int(percent), 100))
    watch, _created = VideoWatch.objects.select_for_update().get_or_create(enrollment=enrollment, section=section)
    if percent > watch.percent:
        watch.percent = percent
        watch.save(update_fields=["percent", "updated_at"])
        recalculate(enrollment)
    return watch.percent


@transaction.atomic
def unlock_section(enrollment, section, by_teacher) -> SectionProgress:
    """Open a section for one student by hand. Logged; it stays open whatever the order says."""
    if section.programme_id != enrollment.programme_id:
        raise SectionLocked(section)
    row = _row(enrollment, section)
    row = SectionProgress.objects.select_for_update().get(pk=row.pk)
    if row.unlocked_by_id is None and row.status == S.LOCKED:
        now = timezone.now()
        row.unlocked_by, row.unlocked_at = by_teacher, now
        row.status, row.opened_at = S.AVAILABLE, row.opened_at or now
        row.save(update_fields=["unlocked_by", "unlocked_at", "status", "opened_at", "updated_at"])
        SectionEvent.objects.create(enrollment=enrollment, section=section, action=A.UNLOCKED, actor=by_teacher)
        student = enrollment.student
        transaction.on_commit(lambda: _notify_opened(student, [section]))
    recalculate(enrollment)
    row.refresh_from_db()
    return row
