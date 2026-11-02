"""STEP-45: the teacher's preview of the ICPAI sections — every page of the student's way opens with everything open,
stays inside the preview, runs on samples and writes nothing."""

import re
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Choice, QuizAttempt
from apps.courses.models import Course, CourseTeacher
from apps.organizations.testing import make_student
from apps.pedagogy.models import Lesson, LessonTemplate, Trial
from apps.programme.models import DiagnosticTest, Portfolio, ProgrammeEnrollment, Section

from .preview.samples import SAMPLE

ROOT = "/teacher/preview/"
LINK = re.compile(r'(?:href|hx-get)="(/[^"#?]*(?:\?[^"#]*)?)')
WRITES = ("INSERT", "UPDATE", "DELETE")


class PreviewBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", topics=[1], verbosity=0)
        call_command("seed_icpai", verbosity=0)
        cls.course = Course.objects.get(programmes__is_active=True)
        cls.teacher = User.objects.create_user("preview", "preview@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=cls.course, teacher=cls.teacher)

    def setUp(self):
        self.client.force_login(self.teacher)

    def url(self, name, *args):
        return reverse(f"student_preview:{name}", args=args)

    def deep(self) -> list[str]:
        """The pages a student reaches by a form (the crawl only follows links)."""
        lesson, trial = SAMPLE + LessonTemplate.objects.order_by("number").first().number, SAMPLE + 1
        return [
            self.url("lesson_stage", 4, lesson, 1),
            self.url("lesson_stage", 4, lesson, 2) + "?cleared=1",
            self.url("lesson_trial", 4, lesson) + "?trial=1",
            self.url("practice", 5, lesson),
            self.url("practice_step", 5, lesson, trial, 1) + "?answered=1",
            self.url("micro", 6),
            self.url("micro_dialog", 6, trial),
            self.url("portfolio_view"),
            self.url("independent", trial),
            self.url("independent_stage", trial, 1),
            self.url("independent", trial) + "?submitted=1",
            self.url("independent_step", trial, trial, 1) + "?answered=1",
            self.url("independent_trial", trial, trial),
        ]

    def crawl(self) -> dict:
        """Every page reachable from the preview's root by links, {url: html}; the teacher's pages are not followed."""
        pages, queue = {}, [ROOT, *self.deep()]
        while queue:
            url = queue.pop()
            if url in pages:
                continue
            response = self.client.get(url, follow=True)
            self.assertEqual(response.status_code, 200, url)
            if response.redirect_chain and not response.redirect_chain[-1][0].startswith(ROOT):
                continue  # OUTSIDE: the real pages a teacher may open
            pages[url] = response.content.decode()
            queue += [link.replace("&amp;", "&") for link in LINK.findall(pages[url]) if link.startswith(ROOT)]
        return pages


class PreviewPagesTests(PreviewBase):
    def test_the_student_is_refused(self):
        self.client.force_login(make_student("pupil"))
        self.assertEqual(self.client.get(self.url("section", 4)).status_code, 403)

    def test_a_teacher_without_a_programme_gets_404(self):
        other = User.objects.create_user("other", "other@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url("section", 4)).status_code, 404)

    def test_the_teacher_pages_lead_to_the_preview(self):
        response = self.client.get(reverse("teacher:section", args=[6]))
        self.assertContains(response, self.url("section", 6))
        self.assertContains(response, self.url("dashboard"))  # the sidebar

    def test_every_section_is_open(self):
        for section in Section.objects.filter(programme__course=self.course):
            with self.subTest(section.number):
                response = self.client.get(self.url("section", section.number))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "partials/shell/sidebar_preview.html")
                self.assertTemplateNotUsed(response, "student/section_locked.html")
                self.assertContains(response, "Алдын ала қарау")

    def test_the_crawl_stays_in_the_preview_and_writes_nothing(self):
        with CaptureQueriesContext(
            connection,
        ) as queries:
            pages = self.crawl()
        self.assertGreater(len(pages), 40)
        written = [
            q["sql"]
            for q in queries
            if q["sql"].lstrip().upper().startswith(WRITES) and "django_session" not in q["sql"]
        ]
        self.assertEqual(written, [])
        for url, html in pages.items():
            actions = re.findall(r'(?:action|hx-post)="(/[^"]*)"', html)
            actions = [
                a for a in actions if not a.startswith(("/accounts/", "/i18n/", "/notifications/", "/teacher/search/"))
            ]
            self.assertEqual([a for a in actions if not a.startswith(ROOT)], [], url)
            links = [link for link in LINK.findall(html) if link.startswith("/me/")]
            self.assertEqual([x for x in links if not x.startswith("/me/courses/")], [], url)

    def test_nothing_of_a_student_is_shown_or_made(self):
        before = (Lesson.objects.count(), Trial.objects.count(), QuizAttempt.objects.count(), Portfolio.objects.count())
        self.crawl()
        self.client.post(self.url("diagnostic_start", 2, "I"))
        self.client.post(self.url("portfolio_assemble"))
        after = (Lesson.objects.count(), Trial.objects.count(), QuizAttempt.objects.count(), Portfolio.objects.count())
        self.assertEqual(before, after)
        self.assertFalse(ProgrammeEnrollment.objects.filter(student=self.teacher).exists())

    def test_the_ai_is_never_called(self):
        with mock.patch("apps.ai.services.client.get_client") as client:
            self.crawl()
            self.client.post(self.url("micro_send", 6, SAMPLE + 1), {"kind": "question", "text": "?"})
        client.assert_not_called()


class PreviewWayTests(PreviewBase):
    def test_the_diagnostic_test_shows_the_key_and_makes_no_attempt(self):
        test = DiagnosticTest.objects.order_by("phase").first()
        response = self.client.post(self.url("diagnostic_start", 2, test.phase), follow=True)
        self.assertTemplateUsed(response, "assessments/take.html")
        correct = Choice.objects.filter(question__quiz=test.quiz, is_correct=True).count()
        self.assertContains(response, "Дұрыс жауап", count=correct)
        self.assertEqual(QuizAttempt.objects.filter(user=self.teacher).count(), 0)
        response = self.client.post(self.url("diagnostic_submit", 2, test.phase, SAMPLE), follow=True)
        self.assertTemplateUsed(response, "student/diagnostic.html")
        self.assertContains(response, "сақталмайды")

    def test_the_way_of_a_template_lesson(self):
        template = LessonTemplate.objects.order_by("number").first()
        response = self.client.post(self.url("lesson_start", 4, template.code), follow=True)
        self.assertTemplateUsed(response, "student/designer/editor.html")
        pk = SAMPLE + template.number
        response = self.client.post(self.url("lesson_stage_clear", 4, pk, 2), follow=True)
        self.assertTrue(response.context["stage"].cleared)
        response = self.client.post(self.url("lesson_assemble", 4, pk), {"action": "assemble"}, follow=True)
        self.assertTemplateUsed(response, "student/designer/plan.html")
        response = self.client.post(self.url("lesson_trial_start", 4, pk), {"level": "high"}, follow=True)
        self.assertEqual(response.context["trial"].level, "high")
        response = self.client.get(self.url("lesson_trial_turn", 4, pk, SAMPLE + 1, 1), headers={"HX-Request": "true"})
        self.assertTemplateUsed(response, "student/designer/partials/turn.html")

    def test_the_way_of_a_practice(self):
        template = LessonTemplate.objects.order_by("number").first()
        response = self.client.post(self.url("practice_start", 5, template.code), follow=True)
        self.assertTemplateUsed(response, "student/practice/sheet.html")
        pk = SAMPLE + template.number
        response = self.client.post(self.url("practice_trial", 5, pk), {"level": "low", "grade": "9"}, follow=True)
        self.assertTemplateUsed(response, "student/practice/step.html")
        self.assertEqual(response.context["trial"].grade, "9")
        step = self.url("practice_step", 5, pk, SAMPLE + 1, 8)
        response = self.client.post(step, {"action": "give"}, follow=True)
        self.assertIsNotNone(response.context["turn"])
        response = self.client.post(step, {"action": "analyse"}, follow=True)
        self.assertTemplateUsed(response, "student/practice/results.html")

    def test_the_way_of_the_microlesson(self):
        source = SAMPLE + LessonTemplate.objects.order_by("-number").first().number
        response = self.client.post(self.url("micro_start", 6), {"practice": source, "stage": "3"}, follow=True)
        self.assertTemplateUsed(response, "student/micro/editor.html")
        self.assertEqual(response.context["part"].order, 3)
        response = self.client.post(self.url("micro_trial", 6), {"level": "medium", "grade": "8"}, follow=True)
        self.assertTemplateUsed(response, "student/micro/dialog.html")
        trial = SAMPLE + 1
        response = self.client.post(self.url("micro_send", 6, trial), {"kind": "question", "text": "?"})
        self.assertTemplateUsed(response, "student/micro/partials/messages.html")
        response = self.client.post(self.url("micro_finish", 6, trial), follow=True)
        self.assertTemplateUsed(response, "student/micro/protocol.html")

    def test_the_way_of_the_portfolio(self):
        response = self.client.post(self.url("portfolio_assemble"), follow=True)
        self.assertTemplateUsed(response, "student/portfolio/view.html")

    def test_the_way_of_an_independent_lesson(self):
        pk = SAMPLE + 1
        response = self.client.post(self.url("independent_start"), follow=True)
        self.assertTemplateUsed(response, "student/independent/editor.html")
        response = self.client.post(self.url("independent_stage_add", pk), {"title": "x", "minutes": 5}, follow=True)
        self.assertIsNotNone(response.context["stage"])
        response = self.client.post(
            self.url("independent_trial_start", pk), {"level": "low", "grade": "7"}, follow=True
        )
        self.assertTemplateUsed(response, "student/practice/step.html")
        step = self.url("independent_step", pk, SAMPLE + 1, 1)
        response = self.client.post(step, {"action": "analyse"}, follow=True)
        self.assertTemplateUsed(response, "student/independent/trial.html")

    def test_an_autosave_and_the_video_report_store_nothing(self):
        save = self.url("lesson_stage_save", 4, SAMPLE + 1, 1)
        response = self.client.post(save, "{}", content_type="application/json")
        self.assertEqual(response.json()["preview"], True)
        watch = self.url("section_watch", 3)
        response = self.client.post(watch, '{"percent": 40}', content_type="application/json")
        self.assertEqual(response.json(), {"preview": True, "percent": 40, "done": False})

    def test_an_action_without_a_page_says_it_is_not_saved(self):
        response = self.client.post(self.url("lesson_finalize", 4, SAMPLE + 1), follow=True)
        self.assertContains(response, "сақталмайды")

    def test_the_profile_and_the_course_lead_out_of_the_preview(self):
        self.assertRedirects(
            self.client.get(self.url("profile")), reverse("student:profile"), fetch_redirect_response=False
        )
        self.assertRedirects(
            self.client.get(self.url("course", self.course.slug)),
            reverse("student:course", args=[self.course.slug]),
            fetch_redirect_response=False,
        )
