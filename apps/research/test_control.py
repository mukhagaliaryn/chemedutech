"""seed_control: the control group's made-up students reach the topic scores of an Excel file, the diagnostics are
answered exactly as given, nothing is sent to the AI."""

import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from random import Random
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from openpyxl import Workbook, load_workbook

from apps.accounts.models import User
from apps.ai.models import AIConversation
from apps.courses import services as course_services
from apps.courses.models import Course
from apps.courses.services.groups import set_research_cohort
from apps.organizations.testing import make_group
from apps.programme.models import DiagnosticResult
from apps.progress.models import TopicResult

from .management.commands._demo.target import best_subset, quiz_only_options

PRE = [1, 0, 1, 0, 0, 1, 0, 1, 0, 0]
POST = [1, 1, 1, 0, 1, 1, 0, 1, 1, 0]


def source_file(path: Path, rows: int, tests: int):
    book = Workbook()
    scores = book.active
    scores.append(["ID", "ФИО", "Группа", "Тип", *[f"Тема {n}" for n in range(1, 11)], "Модуль 1", "Модуль 2",
                   "Текущий балл", "Итоговый балл", "Буквенная оценка", "Завершённые темы"])  # fmt: skip
    for n in range(rows):
        scores.append([f"КГ-{n + 1:03}", None, None, "Контрольная", *([64 + n] * 10), "64", "64", "64", 64 + n, "C-",
                       datetime(2026, 10, 10)])  # fmt: skip
    answers = book.create_sheet()
    answers.append(["ID", *[f"pre_q{n}" for n in range(1, 11)], *[f"post_q{n}" for n in range(1, 11)]])
    for n in range(tests):
        answers.append([f"BT-{n + 1:02}", *PRE, *POST])
    book.save(path)


class PlanTests(TestCase):
    def test_quiz_only_topics_reach_steps_of_one_and_a_quarter(self):
        options = quiz_only_options([Decimal(25), Decimal(25), Decimal(50)], [4, 4, 10], 56)
        self.assertEqual(options[0][0], Decimal("56.25"))
        a, b, c = options[0][1]
        self.assertEqual(a * Decimal("0.25") + b * Decimal("0.25") + c * Decimal("0.5"), Decimal("56.25"))

    def test_best_subset(self):
        chosen = best_subset([Decimal(3)] * 5 + [Decimal(1)], Decimal(10), Random(1))
        self.assertEqual(sum(3 if i < 5 else 1 for i in chosen), 10)


@override_settings(DEBUG=True)
class SeedControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", topics=[1], verbosity=0)
        call_command("seed_icpai", verbosity=0)
        cls.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        cls.course = Course.objects.get(slug="chemistry")
        cls.course.course_teachers.create(teacher=cls.teacher)
        cls.group = make_group(name="1504-14", curator=cls.teacher)
        set_research_cohort(cls.group, "control")
        course_services.assign_group(cls.course, cls.group, teacher=cls.teacher)

    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.source, self.excel = folder / "scores.xlsx", folder / "out.xlsx"
        source_file(self.source, rows=2, tests=3)

    def run_control(self, *args, **kwargs):
        no_ai = AssertionError("no AI")
        with (
            mock.patch("apps.practice.services.ai_grading.get_client", side_effect=no_ai),
            mock.patch("anthropic.Anthropic", side_effect=no_ai),
        ):
            call_command("seed_control", *args, source=str(self.source), excel=str(self.excel), verbosity=0, **kwargs)

    def test_students_reach_the_scores_and_the_diagnostics(self):
        self.run_control(count=3)  # two rows of the file, the third made up
        students = User.objects.filter(student_profile__group=self.group).order_by("username")
        self.assertEqual(list(students.values_list("username", flat=True)), ["student61", "student62", "student63"])
        self.assertEqual(set(students.values_list("enrollments__research_cohort", flat=True)), {"control"})
        first = TopicResult.objects.get(enrollment__student=students[0], topic__number=1)
        self.assertAlmostEqual(float(first.score_percent), 64, delta=1)
        for phase, answers in (("I", PRE), ("III", POST)):
            earned = sum(
                r.earned for r in DiagnosticResult.objects.filter(enrollment__student=students[0], phase=phase)
            )
            self.assertEqual(earned, sum(answers))
        self.assertEqual(set(AIConversation.objects.values_list("model", flat=True)), {"demo"})
        rows = list(load_workbook(self.excel).active.values)
        self.assertEqual(len(rows), 4)
        self.run_control("--delete")
        self.assertFalse(User.objects.filter(student_profile__group=self.group).exists())
