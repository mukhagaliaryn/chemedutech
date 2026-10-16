from django.conf import settings
from django.shortcuts import redirect, render
from django.views import i18n


def home(request):
    if request.user.is_authenticated:
        return redirect("courses:dashboard")
    return render(request, "core/home.html")


def set_language(request):
    """Django's set_language (sets the cookie) + remember the choice on the account."""
    response = i18n.set_language(request)
    lang = request.POST.get("language")
    user = request.user
    if (
        settings.LANGUAGE_COOKIE_NAME in response.cookies
        and user.is_authenticated
        and hasattr(user, "language")  # User.language is added in STEP-03
        and user.language != lang
    ):
        user.language = lang
        user.save(update_fields=["language"])
    return response
