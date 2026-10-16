from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.views import i18n
from django.views.decorators.http import require_GET

from apps.core.permissions import home_url_for

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
            username=data["username"],
            email=data["email"],
            password=data["password1"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            group=data["resolved_group"],
            research_consent=data["research_consent"],
            language=get_language(),
        )
        login(request, user, backend="apps.accounts.backends.UsernameOrEmailBackend")
        return redirect(home_url_for(user))
    return render(request, "accounts/signup.html", {"form": form})


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
