from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .permissions import home_url_for


def home(request):
    if request.user.is_authenticated:
        return redirect(home_url_for(request.user))
    return render(request, "core/home.html")


ABOUT_PAGES = 3  # the guide's introduction pages 2–4 (@S0-INTRO); page 1 is the landing itself


def about(request, page):
    """The platform introduction (ICPAI guide @S0-INTRO): the platform, its aim and tasks · expected results ·
    the ICPAI model — the navbar of the site links to them. «Sign up» leads through these pages to the sign-up
    form (@S0-RULES); «Log in» does not."""
    if not 1 <= page <= ABOUT_PAGES:
        raise Http404
    return render(
        request,
        "core/about.html",
        {
            "page": page,
            "nav_current": page,  # the navbar link of this page (layouts/site.html)
            "pages": range(1, ABOUT_PAGES + 1),
            "previous_url": reverse("core:about_page", args=[page - 1]) if page > 1 else None,
            "next_url": reverse("core:about_page", args=[page + 1]) if page < ABOUT_PAGES else None,
        },
    )
