from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_vary_headers


def _supported(code):
    return bool(code) and code in dict(settings.LANGUAGES)


class KazakhFirstLocaleMiddleware:
    """Pick the interface language without looking at the browser.

    Django's LocaleMiddleware falls back to ``Accept-Language``, so a browser set
    to Russian gets a Russian page on the first visit. Here the order is fixed:
    the signed-in user's saved language → the language cookie → LANGUAGE_CODE
    (kk). ``Accept-Language`` is ignored. Must run after AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = self.get_language(request)
        translation.activate(lang)
        request.LANGUAGE_CODE = lang

        response = self.get_response(request)

        patch_vary_headers(response, ("Cookie",))
        response.headers.setdefault("Content-Language", translation.get_language())
        return response

    @staticmethod
    def get_language(request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # User.language is added in STEP-03 (accounts); until then this is a no-op.
            code = getattr(user, "language", "")
            if _supported(code):
                return code
        code = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if _supported(code):
            return code
        return settings.LANGUAGE_CODE
