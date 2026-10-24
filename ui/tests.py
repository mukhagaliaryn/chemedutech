from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.courses import services
from apps.courses.models import Topic
from apps.labs.engine import all_labs, get_lab
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
        self.assertContains(response, "topic-contents")  # the «Contents» drawer with every stage
        self.assertContains(response, "stage-theory")

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


@override_settings(ALLOWED_HOSTS=["testserver"])
class ShellTests(TestCase):
    """STEP-15: cabinet shell (sidebars, Topbar), search, notifications dropdown, English."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.student = make_student("student1", group=make_group(name="Хим-23-1"), first_name="Айгерім")
        cls.teacher = User.objects.create_user("teacher1", "t1@example.kz", "pw-12345", role=User.Role.TEACHER)
        cls.topic = Topic.objects.filter(is_published=True).select_related("module__course").first()
        cls.course = cls.topic.module.course
        services.enroll(cls.student, cls.course, "admin")
        cls.course.course_teachers.create(teacher=cls.teacher, role="author")

    def test_student_shell(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse("student:courses"))
        self.assertContains(r, 'x-data="cabinet"')
        self.assertContains(r, reverse("student:search"))
        self.assertContains(r, 'id="notif-badge"')
        self.assertContains(r, 'id="notif-count"')
        self.assertNotContains(r, "nav-dark")
        card = r.context["request"]._sidebar_topic
        self.assertEqual(card["topic"], self.topic)
        self.assertEqual(card["passed"], 0)
        self.assertContains(r, card["url"])

    def test_teacher_shell_counts_the_grading_queue(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("teacher:dashboard"))
        self.assertContains(r, "nav-dark")
        self.assertContains(r, reverse("teacher:search"))
        self.assertContains(r, reverse("teacher:grading"))
        self.assertEqual(r.context["request"]._grading_pending, 0)

    def test_student_search_finds_only_own_course_stages(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse("student:search"), {"q": "Зертханалық"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["rows"])
        self.assertTrue(all(row["course"] == self.course for row in r.context["rows"]))
        self.assertContains(r, "Зертханалық жұмыс")
        self.assertContains(r, "badge-neutral")  # locked until the theory is passed
        r = self.client.get(reverse("student:search"), {"q": "жоқ-сөз-123"})
        self.assertEqual(r.context["rows"], [])
        self.assertEqual(self.client.get(reverse("teacher:search")).status_code, 403)

    def test_teacher_search(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("teacher:search"), {"q": "student1"})
        self.assertContains(r, reverse("teacher:student", args=[self.student.pk]))
        r = self.client.get(reverse("teacher:search"), {"q": self.topic.title[:6]})
        self.assertIn(self.topic, list(r.context["topics"]))
        self.assertEqual(self.client.get(reverse("student:search")).status_code, 403)

    def test_notifications_dropdown_and_read_all(self):
        from apps.feedback.models import Notification

        Notification.objects.create(user=self.student, kind="unlocked", title="Видеосабақ ашылды")
        self.client.force_login(self.student)
        r = self.client.get(reverse("feedback:menu"), headers={"HX-Request": "true"})
        self.assertContains(r, "Видеосабақ ашылды")
        self.assertContains(r, 'hx-swap-oob="true"')
        self.assertContains(r, reverse("feedback:read_all"))
        r = self.client.post(reverse("feedback:read_all"), headers={"HX-Request": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, reverse("feedback:read_all"))
        self.assertFalse(Notification.objects.filter(user=self.student, is_read=False).exists())

    def test_english_interface_but_kazakh_by_default(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse("student:courses"), headers={"Accept-Language": "en"})
        self.assertContains(r, '<html lang="kk">')
        self.client.cookies["django_language"] = "en"
        self.student.language = ""
        self.student.save(update_fields=["language"])
        r = self.client.get(reverse("student:courses"))
        self.assertContains(r, '<html lang="en">')
        self.assertContains(r, "My courses")

    def test_ring_component(self):
        html = render_to_string("components/ring.html", {"value": 50, "size": 64, "stroke": 8})
        self.assertIn('stroke-dasharray="87.96 175.93"', html)
        self.assertIn("50%", html)
        self.assertIn("B+", render_to_string("components/ring.html", {"value": 84, "text": "B+"}))


@override_settings(ALLOWED_HOSTS=["testserver"])
class PublicPagesTests(TestCase):
    """STEP-16: landing, login, the sign-up wizard."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.group = make_group(name="Хим-23-1")
        cls.student = make_student("taken.name", group=cls.group)

    def test_landing_uses_real_numbers(self):
        r = self.client.get(reverse("core:home"))
        facts = r.context["facts"]
        self.assertEqual((facts["modules"], facts["topics"]), (2, 15))
        labs = list(all_labs().values())
        self.assertEqual(facts["experiments"], sum(len(lab.experiments) for lab in labs))
        self.assertEqual(len(facts["lab"]["experiments"]), len(get_lab("t01").experiments))  # the showcase lab
        self.assertContains(r, 'id="lab"')
        self.assertContains(r, reverse("accounts:signup"))
        self.assertContains(r, "Zn + 2HCl → ZnCl<sub>2</sub>")  # equation HTML from the lab spec

    def test_login_page(self):
        r = self.client.get(reverse("accounts:login"))
        self.assertContains(r, "brand-ground")
        r = self.client.post(reverse("accounts:login"), {"username": "taken.name", "password": "wrong"})
        self.assertContains(r, 'role="alert"')
        self.assertContains(r, "shake")

    def test_join_code_check(self):
        url = reverse("accounts:join_code_check")
        self.assertContains(self.client.get(url, {"join_code": self.group.join_code}), "Хим-23-1")
        self.assertContains(self.client.get(url, {"join_code": "XXXX-0000"}), "error-text")

    def test_wizard_opens_on_the_step_with_the_error(self):
        url = reverse("accounts:signup")
        self.assertEqual(self.client.get(url).context["step"], 1)
        base = {
            "first_name": "Айгерім", "last_name": "Сапарова", "email": "a@example.kz",
            "password1": "Chem-2026-x", "password2": "Chem-2026-x", "group_mode": "code",
        }  # fmt: skip
        r = self.client.post(url, {**base, "join_code": "XXXX-0000"})
        self.assertEqual(r.context["step"], 2)
        r = self.client.post(url, {**base, "email": "Taken.Name@example.kz", "join_code": "XXXX-0000"})
        self.assertEqual(r.context["step"], 1)
        r = self.client.post(url, {**base, "join_code": self.group.join_code})
        self.assertRedirects(r, reverse("student:dashboard"), fetch_redirect_response=False)
