"""The teacher's active group (STEP-41): chosen in the sidebar, kept in the session; the ICPAI section pages, the
sidebar's rings and counters show that group's students (or every student of the teacher's courses and groups)."""

from django.contrib.auth import get_user_model

from apps.courses import selectors as course_selectors

SESSION_KEY = "teacher_group"


def groups(request) -> list:
    if not hasattr(request, "_teacher_groups"):
        request._teacher_groups = list(
            course_selectors.teacher_groups(request.user).filter(is_active=True).order_by("name")
        )
    return request._teacher_groups


def active_group(request):
    """The group chosen in the sidebar, if it is still one of the teacher's; None — all groups."""
    pk = request.session.get(SESSION_KEY)
    return next((g for g in groups(request) if g.pk == pk), None)


def set_group(request, value) -> None:
    group = next((g for g in groups(request) if str(g.pk) == str(value)), None)
    if group:
        request.session[SESSION_KEY] = group.pk
    else:
        request.session.pop(SESSION_KEY, None)


def students(request):
    """The teacher's students, of the active group when one is chosen."""
    qs = course_selectors.teacher_students(request.user)
    group = active_group(request)
    if group:
        qs = qs.filter(student_profile__group=group)
    return qs


def student_ids(request) -> list[int]:
    if not hasattr(request, "_teacher_student_ids"):
        request._teacher_student_ids = list(students(request).values_list("pk", flat=True))
    return request._teacher_student_ids


def student_list(request):
    return list(
        get_user_model()
        .objects.filter(pk__in=student_ids(request))
        .select_related("student_profile__group")
        .order_by("last_name", "first_name", "username")
    )
