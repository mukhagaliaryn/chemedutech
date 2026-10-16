"""Role checks shared by every app (ARCHITECTURE §1).

core is the lowest layer, so roles are compared by value ("admin", "teacher", "student") and
read from ``user.role`` — nothing is imported from accounts.
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import NoReverseMatch, reverse

ADMIN, TEACHER, STUDENT = "admin", "teacher", "student"


def has_role(user, *roles):
    return bool(user and user.is_authenticated and getattr(user, "role", None) in roles)


def role_required(*roles):
    """View decorator: anonymous → login page, signed in with another role → 403."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not has_role(request.user, *roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_role(request.user, *self.allowed_roles):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(RoleRequiredMixin):
    allowed_roles = (STUDENT,)


class TeacherRequiredMixin(RoleRequiredMixin):
    """Teacher cabinet. The platform admin may open it too (support, research exports)."""

    allowed_roles = (TEACHER, ADMIN)


def _first_url(*names):
    for name in names:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return reverse("core:home")


def home_url_for(user):
    """Where a signed-in user lands: admin → /admin/, teacher → /teacher/, student → /me/.

    Cabinet pages that are not built yet fall back to the current ones.
    """
    if has_role(user, ADMIN):
        return _first_url("admin:index")
    if has_role(user, TEACHER):
        return _first_url("teacher:dashboard", "research:dashboard")
    return _first_url("student:dashboard", "courses:dashboard")
