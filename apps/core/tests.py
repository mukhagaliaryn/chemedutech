from types import SimpleNamespace

from django.conf import settings
from django.test import RequestFactory, TestCase

from apps.core.middleware import KazakhFirstLocaleMiddleware

KK_TITLE = "Әрдайым ашық химия зертханасы"
RU_TITLE = "Химическая лаборатория, которая всегда открыта"


class KazakhFirstLocaleTests(TestCase):
    def test_browser_language_is_ignored(self):
        response = self.client.get("/", HTTP_ACCEPT_LANGUAGE="ru,en;q=0.8")
        self.assertContains(response, '<html lang="kk">')
        self.assertContains(response, KK_TITLE)
        self.assertEqual(response["Content-Language"], "kk")

    def test_cookie_selects_language(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"
        response = self.client.get("/", HTTP_ACCEPT_LANGUAGE="kk")
        self.assertContains(response, '<html lang="ru">')
        self.assertContains(response, RU_TITLE)

    def test_unknown_cookie_falls_back_to_kazakh(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "de"
        response = self.client.get("/", HTTP_ACCEPT_LANGUAGE="de,ru")
        self.assertContains(response, '<html lang="kk">')

    def test_set_language_sets_cookie(self):
        response = self.client.post("/i18n/setlang/", {"language": "ru", "next": "/"}, HTTP_ACCEPT_LANGUAGE="kk")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "ru")
        self.assertContains(self.client.get("/"), RU_TITLE)

    def test_saved_user_language_wins_over_cookie(self):
        request = RequestFactory().get("/", HTTP_ACCEPT_LANGUAGE="kk")
        request.COOKIES[settings.LANGUAGE_COOKIE_NAME] = "kk"
        request.user = SimpleNamespace(is_authenticated=True, language="ru")
        self.assertEqual(KazakhFirstLocaleMiddleware.get_language(request), "ru")

    def test_invalid_user_language_is_skipped(self):
        request = RequestFactory().get("/")
        request.COOKIES[settings.LANGUAGE_COOKIE_NAME] = "ru"
        request.user = SimpleNamespace(is_authenticated=True, language="xx")
        self.assertEqual(KazakhFirstLocaleMiddleware.get_language(request), "ru")
