"""seed_demo: made-up students walk through the course with dates set back; nothing is sent to the AI."""

import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import load_workbook

from apps.accounts.models import User
from apps.ai.models import AIConversation, AIMessage
from apps.assessments.models import QuizAttempt
from apps.courses.models import Course
from apps.organizations.models import AcademicGroup, Department, Faculty, University
from apps.practice.models import AIGrade
from apps.progress.models import StageProgress


@override_settings(DEBUG=True)
class SeedDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", topics=[1], verbosity=0)
        call_command("seed_icpai", verbosity=0)
        faculty = Faculty.objects.create(university=University.objects.create(name="U"), name="F")
        Department.objects.create(faculty=faculty, name="D")
        cls.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        Course.objects.get(slug="chemistry").course_teachers.create(teacher=cls.teacher)
        cls.real = User.objects.create_user("real", "real@example.kz", "x", role=User.Role.STUDENT)

    def setUp(self):
        self.excel = Path(tempfile.mkdtemp()) / "demo.xlsx"

    def run_demo(self, *args):
        no_ai = AssertionError("no AI")
        with (
            mock.patch("apps.practice.services.ai_grading.get_client", side_effect=no_ai),
            mock.patch("anthropic.Anthropic", side_effect=no_ai),
        ):
            call_command("seed_demo", *args, excel=str(self.excel), per_group=3, verbosity=0)

    def test_demo_students_walk_the_course_in_the_past(self):
        self.run_demo()
        demo = User.objects.filter(username__startswith="student")
        self.assertEqual(demo.count(), 6)
        cohorts = dict(AcademicGroup.objects.values_list("name", "research_cohort"))
        self.assertEqual(cohorts, {"1504-14": "control", "1507-14": "experimental"})
        self.assertEqual(set(demo.values_list("enrollments__research_cohort", flat=True)), {"control", "experimental"})
        self.assertTrue(QuizAttempt.objects.filter(user__in=demo).exists())
        self.assertTrue(StageProgress.objects.filter(enrollment__student__in=demo, status="passed").exists())
        self.assertLess(QuizAttempt.objects.filter(user__in=demo).latest("started_at").started_at, timezone.now())
        self.assertEqual(set(AIGrade.objects.values_list("model", flat=True)) - {"demo"}, set())
        self.assertEqual(set(AIConversation.objects.values_list("model", flat=True)) - {"demo"}, set())
        self.assertFalse(AIMessage.objects.exclude(error="").exists())
        rows = list(load_workbook(self.excel).active.values)
        self.assertEqual(len(rows), 7)  # the header + 6 students
        self.assertTrue(self.client.login(username=rows[1][2], password=rows[1][4]))
        with self.assertRaises(CommandError):
            self.run_demo()  # they exist already

        call_command("seed_demo", delete=True, verbosity=0)
        self.assertFalse(User.objects.filter(username__startswith="student").exists())
        self.assertEqual(AcademicGroup.objects.count(), 2)  # the groups stay
        self.assertTrue(User.objects.filter(username="real").exists())  # only the demo students go

    def test_wipe_removes_every_student_but_keeps_teachers(self):
        self.run_demo("--wipe-students", "--yes")
        self.assertFalse(User.objects.filter(username="real").exists())
        self.assertTrue(User.objects.filter(pk=self.teacher.pk).exists())
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT).count(), 6)

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", verbosity=0)
