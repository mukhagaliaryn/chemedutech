"""Teacher's group management (ARCHITECTURE §3.2): groups, members, course streams, research cohort.

Lives in courses because a group change touches enrolments (they follow the group to its courses).
Progress and research data are never removed: a student who leaves a group keeps their enrolments.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext as _

from apps.core.permissions import STUDENT, TEACHER, has_role
from apps.organizations.models import AcademicGroup, StudentProfile
from apps.organizations.services import regenerate_join_code

from ..models import CourseGroup, Enrollment
from ..selectors.teaching import can_manage_group
from .enrollment import assign_group, sync_student_enrollments

GROUP_FIELDS = ("department", "specialty", "name", "admission_year", "study_year", "is_active")


class GroupError(Exception):
    """Shown to the teacher as is (already translated)."""


@transaction.atomic
def save_group(user, data: dict, group: AcademicGroup | None = None) -> AcademicGroup:
    """Create (the teacher becomes the curator) or update a group."""
    if group is None:
        group = AcademicGroup(curator=user if has_role(user, TEACHER) else None)
    # a ModelForm has already copied the new values onto the instance — compare with the database
    previous = AcademicGroup.objects.filter(pk=group.pk).values_list("research_cohort", flat=True).first() or ""
    for name in GROUP_FIELDS:
        if name in data:
            setattr(group, name, data[name])
    group.research_cohort = previous
    group.save()
    if data.get("research_cohort", previous) != previous:
        set_research_cohort(group, data["research_cohort"])
    return group


@transaction.atomic
def set_research_cohort(group: AcademicGroup, cohort: str) -> int:
    """Assign control / experimental to the group.

    New enrolments copy it. Enrolments of this group that have no cohort yet get it now (a group is often
    labelled after its students joined); an enrolment that already has a cohort keeps it — that value is
    the research snapshot (D36). Lab attempts are never touched. Returns how many enrolments were filled.
    """
    group.research_cohort = cohort
    group.save(update_fields=["research_cohort", "updated_at"])
    if not cohort:
        return 0
    return Enrollment.objects.filter(group=group, research_cohort="").update(research_cohort=cohort)


def cohort_conflicts(group: AcademicGroup, cohort: str) -> int:
    """Enrolments of the group that would keep a different cohort."""
    if not cohort:
        return 0
    return Enrollment.objects.filter(group=group).exclude(research_cohort="").exclude(research_cohort=cohort).count()


def find_student(query: str):
    """An existing student account by username or email (exact, case-insensitive)."""
    query = (query or "").strip()
    if not query:
        return None
    users = get_user_model().objects.filter(role=STUDENT, is_active=True)
    return users.filter(username__iexact=query).first() or users.filter(email__iexact=query).first()


@transaction.atomic
def add_student(user, group: AcademicGroup, student) -> int:
    """Put a student into the group and enrol them in the group's courses. Returns new enrolments."""
    if not has_role(student, STUDENT):
        raise GroupError(_("Only students can be added to a group."))
    profile, _created = StudentProfile.objects.select_for_update().get_or_create(user=student)
    if profile.group_id == group.pk:
        raise GroupError(_("%(name)s is already in this group.") % {"name": student.full_name})
    if profile.group is not None and not can_manage_group(user, profile.group):
        raise GroupError(
            _("%(name)s is in the group %(group)s. Ask its teacher to move the student.")
            % {"name": student.full_name, "group": profile.group}
        )
    profile.group = group
    profile.study_year = group.study_year
    profile.save(update_fields=["group", "study_year", "updated_at"])
    return sync_student_enrollments(student)


@transaction.atomic
def remove_student(group: AcademicGroup, student) -> None:
    """Take the student out of the group. Their enrolments, progress and attempts stay."""
    updated = StudentProfile.objects.filter(user=student, group=group).update(group=None)
    if not updated:
        raise GroupError(_("The student is not in this group."))


def attach_course(group: AcademicGroup, course, teacher, starts_on=None, ends_on=None) -> CourseGroup:
    return assign_group(course, group, teacher=teacher, starts_on=starts_on, ends_on=ends_on)


def detach_course(course_group: CourseGroup) -> None:
    """Stop the stream: new members are no longer enrolled; existing enrolments stay."""
    course_group.delete()


def new_join_code(group: AcademicGroup) -> str:
    return regenerate_join_code(group)


@transaction.atomic
def delete_group(group: AcademicGroup) -> None:
    """Only an empty group can go: enrolments remember their group for the research exports."""
    if group.students.exists() or group.course_links.exists() or Enrollment.objects.filter(group=group).exists():
        raise GroupError(_("Only an empty group can be deleted. Make it inactive instead."))
    group.delete()
