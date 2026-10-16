"""Test helpers: a minimal university → faculty → department → group chain."""

from itertools import count

from .models import AcademicGroup, Department, Faculty, StudentProfile, University

_seq = count(1)


def make_group(name=None, research_cohort="", department=None, **extra):
    n = next(_seq)
    if department is None:
        university = University.objects.create(name=f"University {n}", short_name=f"U{n}")
        faculty = Faculty.objects.create(university=university, name=f"Faculty {n}")
        department = Department.objects.create(faculty=faculty, name=f"Department {n}")
    return AcademicGroup.objects.create(
        department=department,
        name=name or f"Chem-{n}",
        admission_year=extra.pop("admission_year", 2023),
        study_year=extra.pop("study_year", 2),
        research_cohort=research_cohort,
        **extra,
    )


def make_student(username, group=None, **user_fields):
    from django.contrib.auth import get_user_model

    user_fields.setdefault("email", f"{username}@example.kz")
    user_fields.setdefault("password", "pw-12345")
    user = get_user_model().objects.create_user(username=username, **user_fields)
    StudentProfile.objects.create(user=user, group=group, study_year=group.study_year if group else None)
    return user
