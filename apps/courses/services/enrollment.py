"""Enrolment: the only place that creates Enrollment rows (ARCHITECTURE §3.3)."""

from django.db import transaction
from django.utils.translation import gettext as _

from apps.core.permissions import STUDENT, has_role
from apps.organizations.selectors import group_of, normalize_join_code

from ..models import Course, CourseGroup, Enrollment


class EnrollmentError(Exception):
    """Shown to the student as is (already translated)."""


@transaction.atomic
def enroll(student, course: Course, source: str, group=None) -> Enrollment:
    """Enrol a student once. The research cohort is copied from the group now and never changes."""
    if not has_role(student, STUDENT):
        raise EnrollmentError(_("Only students can be enrolled in a course."))
    enrollment = Enrollment.objects.filter(student=student, course=course).first()
    if enrollment:
        return enrollment
    group = group or group_of(student)
    return Enrollment.objects.create(
        student=student,
        course=course,
        source=source,
        group=group,
        research_cohort=group.research_cohort if group else "",
    )


def self_enroll(student, course: Course) -> Enrollment:
    if not (course.is_published and course.enrollment_mode == Course.EnrollmentMode.OPEN):
        raise EnrollmentError(_("This course is not open for enrolment."))
    return enroll(student, course, Enrollment.Source.SELF)


def enroll_by_code(student, code: str) -> Enrollment:
    code = normalize_join_code(code)
    course = (
        Course.objects.filter(
            enroll_code__iexact=code, status=Course.Status.PUBLISHED, enrollment_mode=Course.EnrollmentMode.CODE
        ).first()
        if code
        else None
    )
    if course is None:
        raise EnrollmentError(_("No course has this code. Check it with your teacher."))
    return enroll(student, course, Enrollment.Source.CODE)


def sync_group_enrollments(course_group: CourseGroup) -> int:
    """Enrol every active student of the group who is not enrolled yet. Returns how many were added."""
    group = course_group.group
    added = 0
    for profile in group.students.select_related("user").filter(user__is_active=True, user__role=STUDENT):
        if not Enrollment.objects.filter(student=profile.user, course=course_group.course).exists():
            enroll(profile.user, course_group.course, Enrollment.Source.GROUP, group=group)
            added += 1
    return added


@transaction.atomic
def assign_group(course: Course, group, teacher=None, starts_on=None, ends_on=None) -> CourseGroup:
    """Attach an academic group to a course and enrol its students."""
    course_group, _created = CourseGroup.objects.update_or_create(
        course=course, group=group, defaults={"teacher": teacher, "starts_on": starts_on, "ends_on": ends_on}
    )
    sync_group_enrollments(course_group)
    return course_group


def sync_student_enrollments(student) -> int:
    """A student who joined a group after it was assigned to courses gets those courses too."""
    if not has_role(student, STUDENT):
        return 0
    group = group_of(student)
    if group is None:
        return 0
    added = 0
    for course_group in CourseGroup.objects.filter(group=group).exclude(course__enrollments__student=student):
        enroll(student, course_group.course, Enrollment.Source.GROUP, group=group)
        added += 1
    return added
