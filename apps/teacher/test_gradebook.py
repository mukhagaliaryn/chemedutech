"""STEP-11 (2/3): the gradebook matrix and its CSV / XLSX exports."""

import io
import zipfile
from decimal import Decimal

from django.urls import reverse

from apps.courses import services as course_services
from apps.organizations.testing import make_group, make_student
from apps.progress import services as progress
from apps.progress.models import CourseResult, TopicResult

from .tests import TeacherBase


class GradebookTests(TeacherBase):
    def setUp(self):
        super().setUp()
        progress.recalculate(self.e1)
        self.topic = self.stages[0].topic
        TopicResult.objects.filter(enrollment=self.e1, topic=self.topic).update(
            status="completed", score_percent=Decimal("86.5")
        )
        CourseResult.objects.filter(enrollment=self.e1).update(current_percent=Decimal("86.5"))
        self.url = reverse("teacher:gradebook_course", args=["chemistry"])

    def test_matrix(self):
        self.assertRedirects(self.client.get(reverse("teacher:gradebook")), self.url)
        r = self.client.get(self.url)
        rows = {row["student"].username: row for row in r.context["rows"]}
        self.assertEqual(set(rows), {"s1", "s2"})
        self.assertEqual(rows["s1"]["topics"][0]["result"].score_percent, Decimal("86.50"))
        self.assertEqual(rows["s1"]["grade"].letter, "B+")
        self.assertContains(r, "86.5")

    def test_group_filter(self):
        g3 = make_group(name="Хим-23-3", curator=self.teacher, department=self.g1.department)
        make_student("s4", group=g3)
        course_services.assign_group(self.course, g3, teacher=self.teacher)
        r = self.client.get(self.url, {"group": g3.pk})
        self.assertEqual([row["student"].username for row in r.context["rows"]], ["s4"])
        self.assertEqual({g.name for g in r.context["groups"]}, {"Хим-23-1", "Хим-23-3"})

    def test_csv(self):
        r = self.client.get(self.url, {"format": "csv"})
        lines = r.content.decode("utf-8-sig").splitlines()
        self.assertEqual(len(lines), 3)
        row = next(line for line in lines if line.startswith("Сапарова"))
        self.assertIn("86.50", row)
        self.assertIn("B+", row)

    def test_xlsx(self):
        r = self.client.get(self.url, {"format": "xlsx"})
        self.assertEqual(r["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn("[Content_Types].xml", z.namelist())
        self.assertIn("Сапарова Айгерім", sheet)
        self.assertIn("<v>86.50</v>", sheet)

    def test_scope(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
