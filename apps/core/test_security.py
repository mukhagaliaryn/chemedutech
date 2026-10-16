"""STEP-14: who may open what (role matrix) and rich-text sanitising on the pages students see."""

import uuid

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Choice
from apps.courses.models import Course, CourseTeacher, Stage
from apps.courses.services import enroll
from apps.feedback.services import add_comment
from apps.organizations.testing import make_student
from apps.practice.models import PracticeSubmission
from apps.progress import services as progress

STUDENT_PAGES = ["student:dashboard", "student:courses", "student:results", "student:certificates", "student:profile"]
TEACHER_PAGES = [
    "teacher:dashboard", "teacher:groups", "teacher:group_new", "teacher:students", "teacher:grading",
    "teacher:courses", "research:dashboard",
]  # fmt: skip
TEACHER_REDIRECTS = ["teacher:gradebook", "research:analytics"]  # to the first course
SHARED_PAGES = ["feedback:notifications"]
XSS = (
    '<script>alert("x")</script><img src="x" onerror="alert(1)"><p style="color:red" onclick="x()">ok <sub>2</sub></p>'
)


@override_settings(ALLOWED_HOSTS=["testserver"])
class AccessMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")

    def setUp(self):
        self.student = make_student("s1")
        enroll(self.student, self.course, "admin")
        self.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, teacher=self.teacher)
        self.admin = User.objects.create_superuser("root", "root@example.kz", "x")

    def codes(self, names):
        return {name: self.client.get(reverse(name)).status_code for name in names}

    def test_anonymous_is_sent_to_login(self):
        for name in STUDENT_PAGES + TEACHER_PAGES + TEACHER_REDIRECTS + SHARED_PAGES:
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), r.url, name)
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("certificates:verify", args=[uuid.uuid4()])).status_code, 404)

    def test_student(self):
        self.client.force_login(self.student)
        self.assertEqual(set(self.codes(STUDENT_PAGES + SHARED_PAGES).values()), {200})
        self.assertEqual(set(self.codes(TEACHER_PAGES + TEACHER_REDIRECTS).values()), {403})
        for name in ("teacher:comment", "teacher:group_new"):
            self.assertEqual(self.client.post(reverse(name), {}).status_code, 403, name)
        self.assertEqual(self.client.get(reverse("research:export_attempts")).status_code, 403)
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 302)  # not staff → the admin login

    def test_teacher(self):
        self.client.force_login(self.teacher)
        self.assertEqual(set(self.codes(TEACHER_PAGES + SHARED_PAGES).values()), {200})
        self.assertEqual(set(self.codes(TEACHER_REDIRECTS).values()), {302})
        self.assertEqual(
            self.codes(["student:results", "student:certificates"]),
            {"student:results": 403, "student:certificates": 403},
        )
        self.assertEqual(self.client.get(reverse("student:dashboard")).status_code, 302)  # → the teacher's home
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_admin(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["kpis"]), 7)
        self.assertEqual(set(self.codes(TEACHER_PAGES).values()), {200})


@override_settings(ALLOWED_HOSTS=["testserver"])
class SanitisingTests(TestCase):
    """Rich text written in CKEditor reaches students only through the nh3 sanitiser."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")
        cls.stages = list(Stage.objects.filter(topic__number=1).order_by("order"))

    def setUp(self):
        self.student = make_student("s1")
        self.enrollment = enroll(self.student, self.course, "admin")
        self.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(self.student)

    def assert_clean(self, response):
        html = response.content.decode()
        self.assertNotIn('<script>alert("x")', html)
        self.assertNotIn("onerror=", html)
        self.assertNotIn('onclick="x()"', html)
        self.assertNotIn("color:red", html)
        self.assertIn("ok <sub>2</sub>", html)

    def stage_url(self, stage):
        return reverse("student:stage", args=["chemistry", 1, stage.pk])

    def test_theory_body(self):
        theory = self.stages[0]
        theory.theory_content.body = XSS
        theory.theory_content.save()
        self.assert_clean(self.client.get(self.stage_url(theory)))

    def test_practice_instructions(self):
        practice = next(s for s in self.stages if s.kind == "practice")
        progress.unlock_stage(self.enrollment, practice, self.teacher)
        practice.practice_task.instructions = XSS
        practice.practice_task.save()
        self.assert_clean(self.client.get(self.stage_url(practice)))

    def test_quiz_question_and_option(self):
        theory = self.stages[0]
        quiz = theory.checkpoint_quiz
        quiz.questions.update(text=XSS)
        Choice.objects.filter(question__quiz=quiz).update(text='<img src=x onerror="alert(1)">ok <sub>2</sub>')
        progress.complete_material(self.enrollment, theory)
        r = self.client.post(reverse("student:quiz_take", args=["chemistry", 1, theory.pk]), follow=True)
        self.assert_clean(r)

    def test_comment_is_escaped(self):
        practice = next(s for s in self.stages if s.kind == "practice")
        progress.unlock_stage(self.enrollment, practice, self.teacher)
        submission = PracticeSubmission.objects.create(
            enrollment=self.enrollment, stage=practice, attempt_no=1, status="graded"
        )
        add_comment(self.teacher, submission, '<script>alert("c")</script>')
        r = self.client.get(self.stage_url(practice))
        self.assertNotIn('<script>alert("c")', r.content.decode())
        self.assertContains(r, "&lt;script&gt;")
