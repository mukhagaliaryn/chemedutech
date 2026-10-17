from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views import i18n
from django.views.decorators.http import require_GET

from apps.core.permissions import home_url_for
from apps.organizations.selectors import group_by_join_code

from . import services
from .forms import LoginForm, SignUpForm


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember"):
            self.request.session.set_expiry(0)  # until the browser is closed
        return response

    def get_default_redirect_url(self):
        return home_url_for(self.request.user)


def signup(request):
    if request.user.is_authenticated:
        return redirect(home_url_for(request.user))
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = services.register_student(
            email=data["email"],
            password=data["password1"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            group=data["resolved_group"],
            research_consent=data["research_consent"],
            language=get_language(),
        )
        login(request, user, backend="apps.accounts.backends.UsernameOrEmailBackend")
        messages.success(request, _("You are signed up! Enrol in a course and start with the first topic."))
        return redirect(home_url_for(user))
    return render(request, "accounts/signup.html", {"form": form, "step": _first_step_with_errors(form)})


SIGNUP_STEPS = (
    ("first_name", "last_name", "email", "password1", "password2"),
    ("group_mode", *SignUpForm.CASCADE, "join_code"),
    ("research_consent",),
)


def _first_step_with_errors(form) -> int:
    """The wizard opens on the first step that has an error (1 — personal data, 2 — group, 3 — confirm)."""
    if not form.is_bound or not form.errors:
        return 1
    for number, fields in enumerate(SIGNUP_STEPS, start=1):
        if any(name in form.errors for name in fields):
            return number
    return 3


@require_GET
def join_code_check(request):
    """HTMX: which group does this join code open?"""
    code = request.GET.get("join_code", "").strip()
    group = group_by_join_code(code) if code else None
    return render(request, "accounts/partials/join_code_status.html", {"code": code, "group": group})


@require_GET
def signup_cascade(request):
    """HTMX: re-render University → Faculty → Department → Group for the current choices."""
    form = SignUpForm(initial=request.GET.dict())
    return render(request, "accounts/partials/signup_cascade.html", {"form": form})


def set_language(request):
    """Django's set_language (sets the cookie) + remember the choice on the account."""
    response = i18n.set_language(request)
    if request.user.is_authenticated and response.cookies:
        services.set_language(request.user, request.POST.get("language", ""))
    return response
