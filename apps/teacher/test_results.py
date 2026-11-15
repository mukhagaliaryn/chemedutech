"""STEP-46: a student's full course results — the teacher sees every answer, the student sees them in section 1."""

from django.core.management import call_command
from django.urls import reverse
from django.utils.translation import gettext, override

from apps.assessments import services as quiz_services
from apps.assessments.models import QuizAttempt
from apps.progress import services as progress

from .tests import TeacherBase


class StudentResultsTests(TeacherBase):
    def setUp(self):
        super().setUp()
        self.theory = next(s for s in self.stages if s.kind == "theory" and s.checkpoint_quiz_id)
        progress.complete_material(self.e1, self.theory)
        quiz = self.theory.checkpoint_quiz
        self.attempt = quiz_services.start_attempt(self.s1, quiz, self.e1)
        quiz_services.submit_attempt(self.attempt, {})
        progress.record_quiz_result(self.e1, self.theory, quiz)

    def test_stage_row_links_to_the_attempt_and_shows_the_material(self):
        r = self.client.get(reverse("teacher:student", args=[self.s1.pk]))
        url = reverse("teacher:student_quiz", args=[self.s1.pk, self.attempt.pk])
        row = next(x for x in r.context["topics"][0]["table"] if x["stage"] == self.theory)
        self.assertEqual(row["detail_url"], url)
        self.assertIsNotNone(row["material"]["done_at"])
        self.assertContains(r, url)

    def test_attempt_page_shows_answers_with_the_key(self):
        r = self.client.get(reverse("teacher:student_quiz", args=[self.s1.pk, self.attempt.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["rows"]), len(self.attempt.question_ids))
        self.assertEqual(r.context["stage"], self.theory)
        with override("kk"):
            self.assertContains(r, gettext("The student's answers"))

    def test_attempt_page_is_scoped(self):
        url = reverse("teacher:student_quiz", args=[self.s1.pk, self.attempt.pk])
        self.assertEqual(
            self.client.get(reverse("teacher:student_quiz", args=[self.s2.pk, self.attempt.pk])).status_code, 404
        )
        unfinished = QuizAttempt.objects.create(user=self.s1, enrollment=self.e1, quiz=self.attempt.quiz, attempt_no=9)
        self.assertEqual(
            self.client.get(reverse("teacher:student_quiz", args=[self.s1.pk, unfinished.pk])).status_code, 404
        )
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_student_section_1_has_the_gradebook(self):
        call_command("seed_icpai", verbosity=0)
        self.client.force_login(self.s1)
        r = self.client.get(reverse("student:section", args=[1]))
        self.assertEqual(r.status_code, 200)
        grades = r.context["course_block"]["grades"]
        row = next(x for x in grades["topics"][0]["table"] if x["stage"] == self.theory)
        self.assertEqual(row["url"], reverse("student:stage", args=["chemistry", 1, self.theory.pk]))
        self.assertContains(r, row["url"])

    def test_student_page_shows_the_knowledge_test(self):
        from apps.student.test_benchmark import make_benchmark

        from .test_benchmark import finished

        quiz = make_benchmark(self.course)
        pre = finished(self.e1, quiz, "pre", 40)
        r = self.client.get(reverse("teacher:student", args=[self.s1.pk]))
        rows = r.context["benchmark"]
        self.assertEqual([b["phase"] for b in rows], ["pre", "post"])
        self.assertEqual(rows[0]["attempt"], pre)
        self.assertIsNone(rows[1]["attempt"])
        self.assertContains(r, reverse("teacher:student_quiz", args=[self.s1.pk, pre.pk]))
        r = self.client.get(rows[0]["url"])
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["stage"])
