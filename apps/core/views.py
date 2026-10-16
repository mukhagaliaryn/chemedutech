from django.shortcuts import redirect, render

from .permissions import home_url_for


def home(request):
    if request.user.is_authenticated:
        return redirect(home_url_for(request.user))
    return render(request, "core/home.html")
