"""STEP-22: teacher controls and the research view of the pre/post knowledge test."""

import csv
import io

from django.urls import reverse

from apps.assessments.models import Quiz, QuizAttempt
from apps.courses.models import CourseGroup
from apps.organizations.models import ResearchCohort
from apps.student.test_benchmark import make_benchmark

from .tests import TeacherBase


def finished(enrollment, quiz, phase, percent):
    return QuizAttempt.objects.create(
        user=enrollment.student, enrollment=enrollment, quiz=quiz, phase=phase, attempt_no=1 if phase == "pre" else 2,
        question_ids=[],
        percent=percent, score=0, max_score=0, finished_at="2026-10-01T10:00:00Z",
    )  # fmt: skip


class TeacherBenchmarkTests(TeacherBase):
    def test_create_the_test_once(self):
        url = reverse("teacher:benchmark_create", args=["chemistry"])
        r = self.client.post(url)
        self.course.refresh_from_db()
        quiz = self.course.benchmark_quiz
        self.assertRedirects(r, reverse("teacher:quiz", args=["chemistry", quiz.pk]))
        self.assertEqual((quiz.kind, quiz.max_attempts, quiz.show_answers_after), (Quiz.Kind.BENCHMARK, 1, False))
        self.client.post(url)
        self.assertEqual(Quiz.objects.filter(kind=Quiz.Kind.BENCHMARK).count(), 1)
        r = self.client.get(reverse("teacher:course_content", args=["chemistry"]))
        self.assertContains(r, reverse("teacher:quiz", args=["chemistry", quiz.pk]))
        r = self.client.get(reverse("teacher:quiz", args=["chemistry", quiz.pk]))
        self.assertNotContains(r, 'name="show_answers_after"')

    def test_open_and_close_the_posttest_for_a_group(self):
        make_benchmark(self.course)
        link = CourseGroup.objects.get(course=self.course, group=self.g1)
        url = reverse("teacher:group_posttest", args=[self.g1.pk, link.pk])
        self.client.post(url, {"open": "1"})
        link.refresh_from_db()
        self.assertIsNotNone(link.posttest_opened_at)
        self.assertContains(self.client.get(reverse("teacher:group", args=[self.g1.pk])), 'name="open" value="0"')
        self.client.post(url, {"open": "0"})
        link.refresh_from_db()
        self.assertIsNone(link.posttest_opened_at)

    def test_other_teachers_group_is_refused(self):
        self.client.force_login(self.other)
        link = CourseGroup.objects.get(course=self.course, group=self.g1)
        r = self.client.post(reverse("teacher:group_posttest", args=[self.g1.pk, link.pk]), {"open": "1"})
        self.assertEqual(r.status_code, 404)


class PrePostAnalyticsTests(TeacherBase):
    def setUp(self):
        super().setUp()
        self.g1.research_cohort = ResearchCohort.EXPERIMENTAL
        self.g1.save()
        self.quiz = make_benchmark(self.course)
        self.e2 = self.s2.enrollments.get(course=self.course)
        for e in (self.e1, self.e2):
            e.research_cohort = ResearchCohort.EXPERIMENTAL
            e.save()
        finished(self.e1, self.quiz, "pre", 40)
        finished(self.e1, self.quiz, "post", 70)
        finished(self.e2, self.quiz, "pre", 50)  # no post yet: not a pair

    def test_table_and_csv(self):
        url = reverse("research:analytics_course", args=["chemistry"])
        r = self.client.get(url)
        exp = next(row for row in r.context["pre_post_rows"] if row["cohort"] == "experimental")
        self.assertEqual(exp["pre"]["n"], 2)
        self.assertAlmostEqual(exp["pre"]["mean"], 45)
        self.assertEqual(exp["paired"], 1)
        self.assertAlmostEqual(exp["gain"]["mean"], 30)
        self.assertAlmostEqual(exp["norm_gain"]["mean"], 0.5)
        self.assertContains(r, 'id="prepost"')
        r = self.client.get(url + "?format=csv")
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        header = rows[0]
        self.assertEqual(header[-4:], ["pre_percent", "post_percent", "gain", "normalized_gain"])
        mine = next(row for row in rows if row[0] == str(self.e1.pk))
        self.assertEqual(mine[-4:], ["40.0", "70.0", "30.0", "0.5"])

    def test_quiz_answers_export_has_the_phase(self):
        r = self.client.get(reverse("research:export_quiz_answers"))
        header = next(csv.reader(io.StringIO(b"".join(r.streaming_content).decode("utf-8-sig"))))
        self.assertEqual(header[-1], "phase")
