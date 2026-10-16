"""What a teacher may see (ARCHITECTURE §1): their courses, their groups and the students in them.

Groups: the ones they curate + the ones attached to their courses. Students: enrolled in their courses
or members of their groups. The platform admin sees everything. Every teacher page filters through here.
"""

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from apps.core.permissions import ADMIN, STUDENT, has_role
from apps.organizations.models import AcademicGroup, Department, Specialty

from ..models import Course, CourseGroup, Enrollment
from .catalog import courses_for


def teacher_courses(user) -> QuerySet[Course]:
    return courses_for(user).order_by("title")


def teacher_groups(user) -> QuerySet[AcademicGroup]:
    qs = AcademicGroup.objects.all()
    if not has_role(user, ADMIN):
        qs = qs.filter(Q(curator=user) | Q(course_links__course__in=courses_for(user)))
    return qs.select_related("department", "specialty", "curator").distinct()


def can_manage_group(user, group: AcademicGroup) -> bool:
    return teacher_groups(user).filter(pk=group.pk).exists()


def teacher_students(user):
    """Student accounts the teacher may open."""
    users = get_user_model().objects.filter(role=STUDENT)
    if has_role(user, ADMIN):
        return users
    return users.filter(
        Q(enrollments__course__in=courses_for(user)) | Q(student_profile__group__in=teacher_groups(user))
    ).distinct()


def teacher_enrollments(user, course=None) -> QuerySet[Enrollment]:
    qs = Enrollment.objects.filter(course__in=courses_for(user)).exclude(status=Enrollment.Status.DROPPED)
    if course is not None:
        qs = qs.filter(course=course)
    return qs.select_related("student", "course", "group")


def group_courses(group: AcademicGroup) -> QuerySet[CourseGroup]:
    return CourseGroup.objects.filter(group=group).select_related("course", "teacher").order_by("course__title")


def group_members(group: AcademicGroup):
    return (
        get_user_model()
        .objects.filter(role=STUDENT, student_profile__group=group)
        .select_related("student_profile")
        .order_by("last_name", "first_name", "username")
    )


def departments_for(user) -> QuerySet[Department]:
    """Where a teacher may create groups: their university's departments (all for the admin / no profile)."""
    qs = Department.objects.filter(faculty__university__is_active=True).select_related("faculty__university")
    profile = getattr(user, "teacher_profile", None)
    if profile is not None and not has_role(user, ADMIN):
        qs = qs.filter(faculty__university=profile.department.faculty.university)
    return qs.order_by("faculty__university__name", "faculty__name", "name")


def specialties_for(user) -> QuerySet[Specialty]:
    return Specialty.objects.filter(department__in=departments_for(user)).order_by("code")


def can_edit_course(user, course) -> bool:
    """Authors of the course and the admin edit its content; assistants only teach (groups, grading)."""
    from ..models import CourseTeacher

    if has_role(user, ADMIN):
        return True
    return CourseTeacher.objects.filter(course=course, teacher=user, role=CourseTeacher.Role.AUTHOR).exists()
