"""STEP-47: the ICPAI section pages show one group per tab, export their table as CSV / Excel, and «Open» leads to
the student's full results in that section (section 2: every stage, component and answer)."""

import csv
import io
import zipfile

from django.urls import reverse

from apps.accounts.models import User
from apps.courses import services as course_services
from apps.courses.models import CourseTeacher
from apps.organizations.testing import make_group, make_student
from apps.programme import services
from apps.programme.tests import DiagnosticsBase


class SectionResultsTests(DiagnosticsBase):
    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user("ta", "ta@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, teacher=self.teacher)
        self.group.curator = self.teacher
        self.group.save()
        self.other_group = make_group(name="Хим-23-2", department=self.group.department, curator=self.teacher)
        self.other = make_student("s2", group=self.other_group)
        course_services.enroll(self.other, self.course, "group", group=self.other_group)
        services.refresh(self.other)
        self.take("I", correct={1, 2, 3, 4, 5, 6})
        self.client.force_login(self.teacher)

    def test_tabs_show_one_group_and_follow_the_sidebar(self):
        page = reverse("teacher:section", args=[2])
        r = self.client.get(page)
        self.assertEqual([x["student"] for x in r.context["rows"]], [self.student])
        self.assertEqual(r.context["groups"], [self.group, self.other_group])
        self.assertContains(r, f'href="?group={self.other_group.pk}"')
        r = self.client.get(page, {"group": self.other_group.pk})
        self.assertEqual([x["student"] for x in r.context["rows"]], [self.other])
        r = self.client.get(reverse("teacher:section", args=[5]))  # the choice is kept (the sidebar's active group)
        self.assertEqual(r.context["group"], self.other_group)

    def test_open_leads_to_the_section_results(self):
        r = self.client.get(reverse("teacher:section", args=[2]))
        self.assertContains(r, reverse("teacher:section_student", args=[2, self.student.pk]))
        r = self.client.get(reverse("teacher:section", args=[1]))
        self.assertContains(r, reverse("teacher:student", args=[self.student.pk]) + "?course=")
        r = self.client.get(reverse("teacher:section_student", args=[1, self.student.pk]))
        self.assertRedirects(r, reverse("teacher:student", args=[self.student.pk]) + f"?course={self.course.slug}#stages",
                             fetch_redirect_response=False)  # fmt: skip

    def test_diagnostic_results_with_every_answer(self):
        r = self.client.get(reverse("teacher:section_student", args=[2, self.student.pk]))
        self.assertEqual(r.status_code, 200)
        first = r.context["phases"][0]
        self.assertEqual(first["test"].phase, "I")
        self.assertEqual(first["summary"]["earned"], 6)
        self.assertEqual(first["summary"]["level"], "medium")
        self.assertEqual(first["level_text"], self.tests["I"].levels["medium"])
        self.assertEqual(len(first["answers"]), 10)
        self.assertEqual(sum(1 for a in first["answers"] if a["answer"].is_correct), 6)
        self.assertIsNone(r.context["phases"][1]["summary"])
        self.assertContains(r, 'aria-labelledby="ans-I"')

    def test_every_section_page_opens(self):
        for number in range(2, 9):
            r = self.client.get(reverse("teacher:section_student", args=[number, self.student.pk]))
            self.assertEqual(r.status_code, 200, number)
            self.assertTemplateUsed(r, "teacher/sections/student.html")

    def test_scope(self):
        stranger = make_student("s9", group=make_group(name="Био-1"))
        self.assertEqual(self.client.get(reverse("teacher:section_student", args=[2, stranger.pk])).status_code, 404)
        self.client.force_login(self.student)
        self.assertNotEqual(
            self.client.get(reverse("teacher:section_student", args=[2, self.student.pk])).status_code, 200
        )

    def test_csv_and_excel(self):
        page = reverse("teacher:section", args=[2])
        r = self.client.get(page, {"format": "csv"})
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)  # header + the group's one student
        self.assertEqual(rows[1][1], "s1")
        self.assertEqual(rows[1][5:8], ["6.00", "10.00", "60.00"])  # stage I: points, maximum, percent
        self.assertIn("filename", r["Content-Disposition"])
        r = self.client.get(page, {"format": "xlsx"})
        sheet = zipfile.ZipFile(io.BytesIO(r.content)).read("xl/worksheets/sheet1.xml").decode()
        self.assertIn(">s1<", sheet)
        for number in range(1, 9):
            self.assertEqual(
                self.client.get(reverse("teacher:section", args=[number]), {"format": "xlsx"}).status_code, 200
            )
