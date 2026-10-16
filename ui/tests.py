from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.courses import services
from apps.courses.models import Topic
from apps.labs.engine import get_lab
from apps.organizations.testing import make_group, make_student
from ui.templatetags.ui_tags import initials, percent_of, status_variant

INTER = "fonts.googleapis.com/css2?family=Inter"
CSS = "css/dist/styles.css"


class FilterTests(TestCase):
    def test_status_variant_follows_design_system(self):
        self.assertEqual(status_variant("passed"), "success")
        self.assertEqual(status_variant("in_progress"), "info")
        self.assertEqual(status_variant("awaiting_check"), "warning")
        self.assertEqual(status_variant("failed"), "danger")
        self.assertEqual(status_variant("locked"), "neutral")
        self.assertEqual(status_variant("unknown"), "neutral")

    def test_percent_of(self):
        self.assertEqual(percent_of(3, 12), 25.0)
        self.assertEqual(percent_of(40, ""), 40.0)
        self.assertEqual(percent_of(150, 100), 100.0)
        self.assertEqual(percent_of(1, 0), 0)
        self.assertEqual(percent_of("x", 10), 0)

    def test_initials(self):
        self.assertEqual(initials("Айгерім Сапарова"), "АС")
        self.assertEqual(initials(User(username="s1")), "S")
        self.assertEqual(initials(""), "?")


class ComponentTests(TestCase):
    def render(self, name, **context):
        request = RequestFactory().get("/")
        return render_to_string(f"components/{name}.html", context, request=request)

    def test_icon_partials(self):
        html = render_to_string("components/icons.html#lab", {"size": 20})
        self.assertIn('width="20"', html)
        self.assertNotIn("partialdef", render_to_string("components/icons.html"))

    def test_badge_maps_status(self):
        html = self.render("badge", status="awaiting_check", label="Тексеруді күтуде", dot=True)
        self.assertIn("badge-warning", html)
        self.assertIn('class="dot"', html)

    def test_progress_bar(self):
        self.assertIn("width: 50.0%", self.render("progress_bar", value=6, max=12, label="P"))
        self.assertIn("progress-success", self.render("progress_bar", value=12, max=12))

    def test_stage_stepper_handles_any_number_of_stages(self):
        stages = [{"title": f"S{i}", "kind": "practice", "status": "locked", "url": f"/s/{i}/"} for i in range(9)]
        stages[0].update(kind="theory", status="passed", meta="100%")
        stages[1].update(kind="video", status="awaiting_check")
        stages[2].update(kind="lab", status="in_progress", current=True)
        html = self.render("stage_stepper", stages=stages, label="Stages")
        self.assertEqual(html.count("<li"), 9)
        self.assertEqual(html.count('aria-current="step"'), 1)
        self.assertIn("stage-theory", html)
        self.assertIn("badge-warning", html)
        self.assertIn("bg-line-strong", html)  # locked icon tile

    def test_nav_item_hidden_until_page_exists(self):
        self.assertEqual(self.render("nav_item", url_name="student:nowhere", icon="home", label="X").strip(), "")
        self.assertIn(
            'href="/me/courses/"', self.render("nav_item", url_name="student:courses", icon="home", label="X")
        )

    def test_table_and_states(self):
        html = self.render("table", headers=["A", "B"], rows=[["x", "1"]], numeric="1")
        self.assertIn('class="num text-right"', html)
        self.assertIn("—", self.render("table", headers=["A"], rows=[]))
        self.assertIn("Locked", self.render("lock_state", title="Locked", action_url="/a/", action_label="Go"))
        self.assertIn("btn-primary", self.render("empty_state", title="Empty", action_url="/a/", action_label="Go"))
        self.assertIn("<dialog", self.render("modal", id="m", title="T", action="/x/"))


@override_settings(ALLOWED_HOSTS=["testserver"])
class PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.student = make_student("student1", group=make_group(), first_name="Айгерім", last_name="С")
        cls.teacher = User.objects.create_user("teacher1", "t1@example.kz", "pw-12345", role=User.Role.TEACHER)
        cls.staff = User.objects.create_user("admin1", "a1@example.kz", "pw-12345", role=User.Role.ADMIN)

    def assertDesignSystemPage(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, INTER)
        self.assertContains(response, CSS)
        self.assertContains(response, "vendor/htmx.min.js")
        self.assertNotContains(response, "golos")

    def test_public_pages(self):
        for name in ("core:home", "accounts:login", "accounts:signup"):
            self.assertDesignSystemPage(self.client.get(reverse(name)))

    def test_student_cabinet_pages(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("student:courses"))
        self.assertDesignSystemPage(response)
        self.assertContains(response, 'id="cabinet-nav"')
        self.assertContains(response, 'aria-current="page"')
        self.assertNotContains(response, reverse("research:dashboard"))
        topic = Topic.objects.filter(is_published=True).select_related("module__course").first()
        services.enroll(self.student, topic.module.course, "admin")
        response = self.client.get(topic.get_absolute_url())
        self.assertDesignSystemPage(response)
        self.assertContains(response, "stage-lab")  # stage stepper

    def test_teacher_layout_on_research_page(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("research:dashboard"))
        self.assertDesignSystemPage(response)
        self.assertContains(response, 'class="table num"')

    def test_all_lab_experiments_render(self):
        self.client.force_login(self.teacher)  # preview outside a stage; students run labs inside their stage
        lab = get_lab("t01")
        for exp in lab.experiments:
            response = self.client.get(reverse("labs:run", args=[lab.key, exp.key]))
            self.assertDesignSystemPage(response)
            self.assertContains(response, "js/lab/engine.js")
            self.assertContains(response, exp.scene_script)
            self.assertContains(response, 'id="lab-config"')

    def test_styleguide_is_staff_only(self):
        url = reverse("ui:styleguide")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.staff)
        response = self.client.get(url)
        self.assertDesignSystemPage(response)
        for marker in ("btn-primary", "badge-success", "progress", "<dialog", "stage-lab", 'class="table"'):
            self.assertContains(response, marker)
