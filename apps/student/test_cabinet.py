"""STEP-09: student cabinet — dashboard, gradebook, certificates, profile."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.assessments.models import QuizAttempt
from apps.courses.models import Course, Stage
from apps.courses.services import enroll
from apps.feedback.models import Notification
from apps.labs.models import LabAttempt
from apps.organizations.testing import make_group, make_student
from apps.practice.models import PracticeSubmission
from apps.progress import services as progress
from apps.progress.models import CourseResult

from . import cabinet


@override_settings(ALLOWED_HOSTS=["testserver"])
class CabinetBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")
        cls.stages = list(Stage.objects.filter(topic__number=1).order_by("order", "pk"))
        cls.theory = cls.stages[0]
        cls.lab = next(s for s in cls.stages if s.kind == "lab")

    def setUp(self):
        self.student = make_student("s1", group=make_group(name="Хим-23-1"))
        self.student.first_name = "Айгерім"
        self.student.save()
        self.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.enrollment = enroll(self.student, self.course, "admin")
        self.client.force_login(self.student)

    def pass_theory(self):
        quiz = self.theory.checkpoint_quiz
        QuizAttempt.objects.create(
            enrollment=self.enrollment, user=self.student, quiz=quiz, attempt_no=1,
            finished_at=timezone.now(), percent=Decimal("100"), passed=True,
        )  # fmt: skip
        progress.complete_stage(self.enrollment, self.theory, 100, passed=True)


class DashboardTests(CabinetBase):
    def test_login_lands_on_the_dashboard(self):
        self.client.logout()
        r = self.client.post(reverse("accounts:login"), {"username": "s1", "password": "pw-12345"})
        self.assertRedirects(r, reverse("student:dashboard"), fetch_redirect_response=False)

    def test_first_visit(self):
        r = self.client.get(reverse("student:dashboard"))
        self.assertContains(r, "Айгерім")
        card = r.context["card"]
        self.assertEqual(card["stage"], self.theory)
        self.assertEqual([t["status"] for t in card["tiles"]][:2], ["available", "locked"])
        self.assertTrue(card["tiles"][0]["current"])
        self.assertEqual(r.context["labs_total"], 4)
        self.assertEqual(r.context["recent"], [])
        self.assertContains(r, reverse("student:stage", args=["chemistry", 1, self.theory.pk]))

    def test_after_some_work(self):
        self.pass_theory()
        LabAttempt.objects.create(
            user=self.student, enrollment=self.enrollment, stage=self.lab, lab_key="t01", experiment_key="hydrogen",
            status="analysed", finished_at=timezone.now(), score_percent=Decimal("79"), safety_warnings=1,
        )  # fmt: skip
        r = self.client.get(reverse("student:dashboard"))
        self.assertEqual(r.context["card"]["stage"], self.stages[1])
        self.assertEqual(r.context["labs_done"], 1)
        self.assertEqual([i["icon"] for i in r.context["recent"]], ["lab", "test"])
        self.assertIn("1", r.context["recent"][0]["meta"])  # one safety warning
        self.assertIsNone(r.context["result"].current_percent)  # current score counts completed topics only
        self.assertEqual(r.context["modules"][0]["passed"], 1)

    def test_teacher_comment_and_notifications(self):
        PracticeSubmission.objects.create(
            enrollment=self.enrollment, stage=self.stages[3], attempt_no=1, status="graded",
            percent=Decimal("80"), graded_by=self.teacher, teacher_comment="Есепті қайта тексеріңіз.",
        )  # fmt: skip
        Notification.objects.create(user=self.student, kind="graded", title="Практикалық жұмыс 1")
        r = self.client.get(reverse("student:dashboard"))
        self.assertContains(r, "Есепті қайта тексеріңіз.")
        self.assertEqual(len(r.context["notifications"]), 1)

    def test_no_course(self):
        self.client.force_login(make_student("lonely"))
        r = self.client.get(reverse("student:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context.get("card"))
        self.assertContains(r, reverse("student:courses"))

    def test_teacher_is_sent_home(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("student:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertNotEqual(r.url, reverse("student:dashboard"))


class GradebookTests(CabinetBase):
    def test_topic_table(self):
        self.pass_theory()
        r = self.client.get(reverse("student:results"))
        self.assertEqual(r.status_code, 200)
        topic = r.context["topics"][0]
        rows = topic["table"]
        self.assertEqual(len(rows), len(self.stages))
        self.assertAlmostEqual(float(sum(row["weight"] for row in rows if row["weight"] is not None)), 100, places=5)
        lab_row = next(row for row in rows if row["stage"].kind == "lab")
        self.assertIn("30", lab_row["method"])
        self.assertEqual(lab_row["attempts"].split()[0:3], ["0", "/", "4"])
        self.assertEqual((rows[0]["status"], rows[0]["score"], rows[0]["attempts"]), ("passed", Decimal("100.00"), "1"))
        self.assertEqual(len(r.context["closed"]), 0)  # only topic 1 is published by the seed
        self.assertFalse(any(g["current"] for g in r.context["scale"]))
        scale = cabinet.scale("B+")
        self.assertEqual([g["letter"] for g in scale if g["current"]], ["B+"])
        self.assertEqual((scale[0]["range"], scale[-1]["range"]), ("95–100", "0–49"))

    def test_course_switch(self):
        self.assertEqual(cabinet.pick(cabinet.enrollments_of(self.student), "nope"), self.enrollment)
        r = self.client.get(reverse("student:results") + "?course=chemistry")
        self.assertEqual(r.context["course"], self.course)

    def test_students_only(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("student:results")).status_code, 403)


class CertificateTests(CabinetBase):
    def test_progress_towards_the_certificate(self):
        r = self.client.get(reverse("student:certificates"))
        row = r.context["rows"][0]
        self.assertFalse(row["passed"])
        self.assertContains(r, self.course.title)

    def test_passed_course(self):
        progress.recalculate(self.enrollment)
        CourseResult.objects.filter(enrollment=self.enrollment).update(passed=True, score_percent=Decimal("91"))
        rows = cabinet.certificate_rows(cabinet.enrollments_of(self.student))
        self.assertTrue(rows[0]["passed"])
        self.assertEqual(rows[0]["grade"].letter, "A-")


class ProfileTests(CabinetBase):
    def test_update(self):
        data = {
            "form": "profile", "last_name": "Сапарова", "first_name": "Айгерім", "middle_name": "",
            "email": "aigerim@example.kz", "phone": "+7 700 000 00 00", "language": "ru",
        }  # fmt: skip
        r = self.client.post(reverse("student:profile"), data)
        self.assertRedirects(r, reverse("student:profile"), fetch_redirect_response=False)
        self.student.refresh_from_db()
        self.assertEqual(
            (self.student.last_name, self.student.email, self.student.language),
            ("Сапарова", "aigerim@example.kz", "ru"),
        )
        self.assertEqual(r.cookies["django_language"].value, "ru")

    def test_email_must_be_unique(self):
        r = self.client.post(
            reverse("student:profile"),
            {"form": "profile", "last_name": "A", "first_name": "B", "email": "T@example.kz", "language": "kk"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("email", r.context["profile_form"].errors)

    def test_password_change_keeps_the_session(self):
        r = self.client.post(
            reverse("student:profile"),
            {
                "form": "password",
                "old_password": "pw-12345",
                "new_password1": "Zertxana-2026!",
                "new_password2": "Zertxana-2026!",
            },
        )
        self.assertRedirects(r, reverse("student:profile"), fetch_redirect_response=False)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("Zertxana-2026!"))
        self.assertEqual(self.client.get(reverse("student:profile")).status_code, 200)

    def test_teacher_profile(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("student:profile"))
        self.assertTemplateUsed(r, "layouts/teacher.html")
