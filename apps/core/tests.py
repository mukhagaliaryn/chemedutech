from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.middleware import KazakhFirstLocaleMiddleware

KK_TITLE = "Білім беру платформасы"
RU_TITLE = "Образовательная платформа"


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


class StatsTests(SimpleTestCase):
    def test_describe_and_share(self):
        from apps.core import stats

        self.assertEqual(stats.describe([1, 2, 3, 10, None]), {"n": 4, "mean": 4.0, "median": 2.5})
        self.assertEqual(stats.describe([]), {"n": 0, "mean": None, "median": None})
        self.assertEqual(stats.share([True, False, True, True])["rate"], 75.0)

    def test_pearson(self):
        from apps.core import stats

        self.assertAlmostEqual(stats.pearson([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)
        self.assertIsNone(stats.pearson([1, 2], [1, 2]))
        self.assertIsNone(stats.pearson([1, 1, 1], [1, 2, 3]))

    def test_cohen_kappa(self):
        from apps.core import stats

        # textbook example: 50 items, agree 20 yes + 15 no → p_o = .7, p_e = .5 → κ = .4
        pairs = [("y", "y")] * 20 + [("y", "n")] * 5 + [("n", "y")] * 10 + [("n", "n")] * 15
        self.assertAlmostEqual(stats.cohen_kappa(pairs), 0.4)
        self.assertEqual(stats.cohen_kappa([("1", "1"), ("1", "1")]), 1.0)
        self.assertIsNone(stats.cohen_kappa([]))
        self.assertEqual(stats.label(Decimal("1.50")), "1.5")


class RichTextTests(SimpleTestCase):
    """STEP-25: answer options keep inline marks only; rich answers reach the AI as plain text."""

    def test_inline_html_keeps_marks_on_one_line(self):
        from apps.core.html import inline_html

        self.assertEqual(inline_html("<p>H<sub>2</sub>SO<sub>4</sub></p>"), "H<sub>2</sub>SO<sub>4</sub>")
        self.assertEqual(inline_html("<p>a</p><p>b <script>x()</script></p>"), "a<br>b")
        self.assertEqual(inline_html("<p>&nbsp;</p>"), "")

    def test_html_to_text_uses_unicode_indices(self):
        from apps.core.html import html_to_text

        self.assertEqual(html_to_text("<p>SO<sub>4</sub><sup>2-</sup> &amp; Zn<sup>2+</sup></p>"), "SO₄²⁻ & Zn²⁺")
        self.assertEqual(html_to_text("<ul><li>a</li><li>b</li></ul>"), "• a\n• b")
        self.assertEqual(html_to_text("plain 2 < 3"), "plain 2 < 3")

    def test_rich_filter_sanitises_html_and_keeps_old_plain_text(self):
        from ui.templatetags.ui_tags import rich

        self.assertEqual(rich("<p>H<sub>2</sub>O<script>x</script></p>"), "<p>H<sub>2</sub>O</p>")
        self.assertEqual(rich("line 1\nline <2>"), "line 1<br>line &lt;2&gt;")


@override_settings(ALLOWED_HOSTS=["testserver"])
class AboutPagesTests(TestCase):
    """STEP-30: the platform introduction (ICPAI guide @S0-INTRO) — public pages on the way to sign-up."""

    def test_three_public_pages_with_the_guide_texts(self):
        r = self.client.get(reverse("core:about"))
        self.assertContains(r, "ChemEduTech платформа таныстырылымы")
        self.assertContains(r, "Мақсаты")
        self.assertContains(r, "Білім беруді ақпараттандырудың ғылыми-педагогикалық негіздерін меңгерту.")
        self.assertContains(r, reverse("core:about_page", args=[2]))
        r = self.client.get(reverse("core:about_page", args=[2]))
        self.assertContains(r, "Күтілетін нәтижелер")
        self.assertContains(r, "химиялық үдерістерді макро-, субмикро- және символдық деңгейлерде түсіндіреді;")
        r = self.client.get(reverse("core:about_page", args=[3]))
        self.assertContains(r, "ICPAI авторлық моделі")
        self.assertContains(r, "ICPAI моделіне негізделген")
        self.assertNotContains(r, "ICPAT")
        self.assertEqual(self.client.get(reverse("core:about_page", args=[4])).status_code, 404)

    def test_sign_up_goes_through_the_pages_log_in_does_not(self):
        landing = self.client.get(reverse("core:home"))
        self.assertNotContains(landing, reverse("accounts:signup"))
        self.assertContains(landing, reverse("core:about"))
        self.assertContains(landing, reverse("accounts:login"))
        self.assertNotContains(self.client.get(reverse("core:about")), f'href="{reverse("accounts:signup")}"')
        last = self.client.get(reverse("core:about_page", args=[3]))
        self.assertContains(last, f'href="{reverse("accounts:signup")}"')
        login = self.client.get(reverse("accounts:login"))
        self.assertContains(login, reverse("core:about"))

    def test_navbar_links_lead_to_the_pages(self):
        r = self.client.get(reverse("core:about_page", args=[2]))
        for n in (1, 2, 3):
            self.assertContains(r, reverse("core:about_page", args=[n]))
        self.assertContains(r, 'aria-current="page"', count=3)  # navbar, mobile menu, the page tabs

    def test_model_page_shows_the_four_components(self):
        r = self.client.get(reverse("core:about_page", args=[3]))
        for part in ("I — Information", "C — Chemistry", "P — Pedagogy", "AI — Artificial Intelligence"):
            self.assertContains(r, part)
        self.assertContains(r, "Платформада жүзеге асатын мазмұны")
