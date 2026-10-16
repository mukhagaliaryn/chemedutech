"""University → faculty → department → group lookups (sign-up cascade, admin)."""

from ..models import AcademicGroup, Department, Faculty, University


def active_universities():
    return University.objects.filter(is_active=True)


def faculties_of(university):
    return Faculty.objects.filter(university=university)


def departments_of(faculty):
    return Department.objects.filter(faculty=faculty)


def open_groups_of(department):
    """Groups a student may pick when signing up."""
    return AcademicGroup.objects.filter(
        department=department, is_active=True, department__faculty__university__is_active=True
    )


def normalize_join_code(code):
    return "".join(str(code or "").split()).upper()


def group_by_join_code(code):
    code = normalize_join_code(code)
    if not code:
        return None
    return (
        AcademicGroup.objects.filter(join_code=code, is_active=True, department__faculty__university__is_active=True)
        .select_related("department__faculty__university")
        .first()
    )
