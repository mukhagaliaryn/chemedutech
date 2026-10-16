"""STEP-12: course analytics, AI ↔ teacher agreement, random spot-check, research exports and their scope."""

import random
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.assessments.models import AttemptAnswer, QuizAttempt
from apps.courses.models import Enrollment
from apps.labs.models import LabAttempt, LabEvent
from apps.practice.models import AIGrade, PracticeAnswer, PracticeSubmission, TeacherReview
from apps.practice.services import sampling
from apps.progress import services as progress
from apps.progress.models import StageProgress
from apps.teacher.tests import TeacherBase

from . import analytics


class ResearchBase(TeacherBase):
    def setUp(self):
        super().setUp()
        self.e2 = Enrollment.objects.get(student=self.s2)
        Enrollment.objects.filter(pk=self.e1.pk).update(research_cohort="experimental")
        Enrollment.objects.filter(pk=self.e2.pk).update(research_cohort="control")
        self.e1.refresh_from_db()
        self.e2.refresh_from_db()
        self.by_kind = {}
        for s in self.stages:
            self.by_kind.setdefault(s.kind, s)
        for e in (self.e1, self.e2):
            progress.recalculate(e)

    def done(self, enrollment, stage, score, time_s=600):
        StageProgress.objects.filter(enrollment=enrollment, stage=stage).update(
            status="passed", score_percent=Decimal(score), time_spent_s=time_s, started_at=timezone.now()
        )

    def url(self):
        return reverse("research:analytics_course", args=["chemistry"])


class AnalyticsTests(ResearchBase):
    def test_cohort_comparison(self):
        test, lab = self.by_kind["test"], self.by_kind["lab"]
        self.done(self.e1, test, 80, 3600)
        self.done(self.e2, test, 60, 1800)
        self.done(self.e1, lab, 90)
        quiz = self.stages[0].checkpoint_quiz
        QuizAttempt.objects.create(
            enrollment=self.e1, user=self.s1, quiz=quiz, attempt_no=1, finished_at=timezone.now(), passed=True
        )
        QuizAttempt.objects.create(
            enrollment=self.e2, user=self.s2, quiz=quiz, attempt_no=1, finished_at=timezone.now(), passed=False
        )
        r = self.client.get(self.url(), {"topic": 1})
        self.assertEqual(r.status_code, 200)
        rows = {row["title"]: row for row in r.context["cohorts"]["rows"]}
        test_row = rows[next(t for t in rows if "test" in t.lower() or "тест" in t.lower())]
        self.assertEqual([c["value"] for c in test_row["cells"]], ["80.0", "60.0"])
        self.assertEqual(test_row["diff"], "+20.0")
        self.assertEqual(r.context["cohorts"]["n"], {"experimental": 1, "control": 1})
        per = r.context["per"]
        self.assertEqual(per[self.e1.pk]["checkpoint_first"], [True])
        self.assertEqual(per[self.e1.pk]["time_s"], 4200)
        funnel = {row["stage"].kind: row["done"] for row in r.context["stage_rows"]}
        self.assertEqual((funnel["test"], funnel["lab"], funnel["theory"]), (2, 1, 0))

    def test_csv(self):
        self.done(self.e1, self.by_kind["test"], 75)
        r = self.client.get(self.url(), {"topic": 1, "format": "csv"})
        lines = r.content.decode("utf-8-sig").splitlines()
        self.assertTrue(lines[0].startswith("enrollment_id,username"))
        row = next(line for line in lines if line.startswith(str(self.e1.pk)))
        self.assertIn("experimental", row)
        self.assertIn("75.0", row)

    def test_lab_errors_and_step_time(self):
        lab = self.by_kind["lab"]
        attempt = LabAttempt.objects.create(
            user=self.s1, enrollment=self.e1, stage=lab, lab_key="t01", experiment_key="hydrogen",
            status="analysed", step_times={"add_acid": 42000},
        )  # fmt: skip
        LabEvent.objects.create(attempt=attempt, seq=1, t_ms=1000, type="safety_warning", step="add_acid")
        LabEvent.objects.create(attempt=attempt, seq=2, t_ms=2000, type="safety_warning", step="add_acid")
        data = analytics.lab_errors([self.e1, self.e2], self.stages)
        error = data["errors"][0]
        self.assertEqual(
            (error["type"], error["students"], error["tried"], error["events"]), ("safety_warning", 1, 1, 2)
        )
        self.assertEqual(error["time"], 42.0)

    def test_scope_and_filters(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.client.force_login(self.teacher)
        r = self.client.get(self.url(), {"group": self.g1.pk})
        self.assertEqual(len(r.context["enrollments"]), 2)
        self.assertRedirects(self.client.get(reverse("research:analytics")), self.url())


class AgreementTests(ResearchBase):
    def review(self, ai, teacher, criteria_ai, criteria_teacher):
        practice = self.by_kind["practice"]
        item = practice.practice_task.items.get(kind="open")
        crit = list(item.rubric.criteria.order_by("order"))
        no = PracticeSubmission.objects.filter(enrollment=self.e1, stage=practice).count() + 1
        sub = PracticeSubmission.objects.create(enrollment=self.e1, stage=practice, attempt_no=no, status="graded")
        answer = PracticeAnswer.objects.create(submission=sub, item=item, points=Decimal(teacher))
        AIGrade.objects.create(
            answer=answer, model="m", prompt_version="v",
            criteria_scores=[{"criterion_id": c.pk, "points": p} for c, p in zip(crit, criteria_ai, strict=True)],
        )  # fmt: skip
        TeacherReview.objects.create(
            answer=answer, teacher=self.teacher, ai_points=Decimal(ai), teacher_points=Decimal(teacher),
            criteria_scores=[{"criterion_id": c.pk, "points": p} for c, p in zip(crit, criteria_teacher, strict=True)],
        )  # fmt: skip

    def test_numbers(self):
        self.review(2, 2, (1, 1), (1, 1))
        self.review(1, 2, (1, 0), (1, 1))
        self.review(0, 0, (0, 0), (0, 0))
        result = analytics.ai_agreement([self.e1, self.e2])
        self.assertEqual((result["answers"], result["criteria"]), (3, 6))
        self.assertAlmostEqual(result["exact"], 5 / 6 * 100)
        # mean difference teacher − AI in % of 2 points: (0 + 50 + 0) / 3
        self.assertAlmostEqual(result["mean_diff"], 50 / 3)
        self.assertIsNotNone(result["kappa"])
        self.assertGreater(result["pearson"], 0.8)

    def test_export_ai_reviews_scope(self):
        self.review(1, 2, (1, 0), (1, 1))
        r = self.client.get(reverse("research:export_ai_reviews"))
        lines = b"".join(r.streaming_content).decode("utf-8-sig").splitlines()
        self.assertEqual(len(lines), 2)
        self.client.force_login(self.other)
        lines = (
            b"".join(self.client.get(reverse("research:export_ai_reviews")).streaming_content)
            .decode("utf-8-sig")
            .splitlines()
        )
        self.assertEqual(len(lines), 1)


class SampleTests(ResearchBase):
    def make_ai_graded(self, n):
        practice = self.by_kind["practice"]
        item = practice.practice_task.items.get(kind="open")
        for i in range(n):
            sub = PracticeSubmission.objects.create(
                enrollment=self.e1, stage=practice, attempt_no=i + 1, status="graded"
            )
            answer = PracticeAnswer.objects.create(submission=sub, item=item)
            AIGrade.objects.create(answer=answer, model="m", prompt_version="v", confidence="high")

    def test_draw(self):
        self.make_ai_graded(10)
        self.assertEqual(sampling.draw_review_sample([self.e1.pk], 15, rng=random.Random(1)), 2)
        self.assertEqual(sampling.draw_review_sample([self.e1.pk], 15, rng=random.Random(2)), 0)
        self.assertEqual(PracticeSubmission.objects.exclude(sampled_at=None).count(), 2)

    def test_draw_view_and_queue(self):
        self.make_ai_graded(4)
        self.course.review_sample_percent = 50
        self.course.save()
        r = self.client.post(reverse("research:draw_sample", args=["chemistry"]))
        self.assertRedirects(r, self.url(), fetch_redirect_response=False)
        r = self.client.get(reverse("teacher:grading"), {"status": "sample"})
        self.assertEqual(len(r.context["submissions"]), 2)
        self.assertEqual(self.client.get(self.url()).context["sample"], {"ai_graded": 4, "sampled": 2, "checked": 0})


class ExportScopeTests(ResearchBase):
    def test_teacher_sees_own_course_data(self):
        lab = self.by_kind["lab"]
        LabAttempt.objects.create(user=self.s1, enrollment=self.e1, stage=lab, lab_key="t01", experiment_key="oxygen")
        LabAttempt.objects.create(user=self.teacher, lab_key="t01", experiment_key="rate")  # a preview
        r = self.client.get(reverse("research:dashboard"))
        self.assertEqual(r.context["total"], 1)
        admin = User.objects.create_superuser("root", "root@example.kz", "x")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("research:dashboard")).context["total"], 2)

    def test_quiz_answers_export(self):
        quiz = self.stages[0].checkpoint_quiz
        question = quiz.questions.filter(kind="single").first()
        attempt = QuizAttempt.objects.create(
            enrollment=self.e1, user=self.s1, quiz=quiz, attempt_no=1, finished_at=timezone.now()
        )
        answer = AttemptAnswer.objects.create(attempt=attempt, question=question, is_correct=True, points=1)
        answer.choices.add(question.choices.first())
        lines = (
            b"".join(self.client.get(reverse("research:export_quiz_answers")).streaming_content)
            .decode("utf-8-sig")
            .splitlines()
        )
        self.assertEqual(len(lines), 2)
        self.assertIn(str(question.choices.first().pk), lines[1])
        self.assertIn("experimental", lines[1])

    def test_old_url_redirects(self):
        r = self.client.get("/research/?cohort=control")
        self.assertRedirects(r, reverse("research:dashboard") + "?cohort=control", fetch_redirect_response=False)
