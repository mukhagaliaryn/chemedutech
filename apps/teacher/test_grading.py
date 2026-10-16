"""STEP-11 (1/3): the grading queue, confirming / changing AI grades, returning, comments."""

from decimal import Decimal

from django.urls import reverse

from apps.feedback.models import Comment, Notification
from apps.labs.models import LabAttempt
from apps.practice.models import AIGrade, PracticeAnswer, PracticeSubmission, TeacherReview
from apps.progress import services as progress
from apps.progress.models import StageProgress

from .tests import TeacherBase

S = StageProgress.Status


class GradingBase(TeacherBase):
    def setUp(self):
        super().setUp()
        self.practice = next(s for s in self.stages if s.kind == "practice")
        self.task = self.practice.practice_task
        self.open_item = self.task.items.get(kind="open")
        self.criteria = list(self.open_item.rubric.criteria.order_by("order"))
        progress.unlock_stage(self.e1, self.practice, self.teacher)
        self.submission = PracticeSubmission.objects.create(
            enrollment=self.e1, stage=self.practice, attempt_no=1, status="needs_review",
            score=Decimal("1"), max_score=self.open_item.points, percent=Decimal("50"),
        )  # fmt: skip
        self.answer = PracticeAnswer.objects.create(
            submission=self.submission, item=self.open_item, raw_value="Сутегі суда нашар ериді.", points=Decimal("1")
        )
        AIGrade.objects.create(
            answer=self.answer, model="claude-sonnet-5-5", prompt_version="practice-open-v1", confidence="low",
            criteria_scores=[{"criterion_id": c.pk, "points": p, "reason": "ok"} for c, p in zip(self.criteria, (1, 0), strict=True)],
        )  # fmt: skip

    def url(self):
        return reverse("teacher:grading_detail", args=[self.submission.pk])


class QueueTests(GradingBase):
    def test_queue_and_scope(self):
        r = self.client.get(reverse("teacher:grading"))
        self.assertEqual(list(r.context["submissions"]), [self.submission])
        self.assertEqual(r.context["tabs"][0]["count"], 1)
        self.client.force_login(self.other)
        self.assertEqual(list(self.client.get(reverse("teacher:grading")).context["submissions"]), [])
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_detail_shows_the_ai_suggestion(self):
        r = self.client.get(self.url())
        row = next(x for x in r.context["rows"] if x["open"])
        self.assertEqual([c["ai_points"] for c in row["criteria"]], [1, 0])
        self.assertContains(r, f'name="c_{self.answer.pk}_{self.criteria[0].pk}"')


class DecisionTests(GradingBase):
    def post(self, *points, **extra):
        data = {f"c_{self.answer.pk}_{c.pk}": p for c, p in zip(self.criteria, points, strict=True)}
        data.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url(), data)

    def test_teacher_changes_the_points(self):
        r = self.post(1, 1, action="confirm", teacher_comment="Жақсы", **{f"r_{self.answer.pk}": "толық жауап"})
        self.assertRedirects(r, reverse("teacher:grading"), fetch_redirect_response=False)
        self.submission.refresh_from_db()
        self.assertEqual((self.submission.status, self.submission.teacher_override), ("graded", True))
        self.assertEqual(self.submission.teacher_comment, "Жақсы")
        review = TeacherReview.objects.get(answer=self.answer)
        self.assertEqual(
            (review.ai_points, review.teacher_points, review.reason), (Decimal("1.00"), Decimal("2.00"), "толық жауап")
        )
        self.assertEqual([c["points"] for c in review.criteria_scores], [1.0, 1.0])
        self.assertEqual(StageProgress.objects.get(enrollment=self.e1, stage=self.practice).status, S.PASSED)
        self.assertTrue(Notification.objects.filter(user=self.s1, kind="graded").exists())

    def test_confirm_as_is(self):
        self.post(1, 0, action="confirm")
        review = TeacherReview.objects.get(answer=self.answer)
        self.assertEqual((review.teacher_points, review.reason), (Decimal("1.00"), "confirmed"))

    def test_points_are_clamped(self):
        self.post(99, -5, action="confirm")
        review = TeacherReview.objects.get(answer=self.answer)
        self.assertEqual(review.teacher_points, self.criteria[0].points)

    def test_return(self):
        self.post(1, 0, action="return", teacher_comment="Қайта қараңыз")
        self.submission.refresh_from_db()
        self.assertEqual((self.submission.status, self.submission.teacher_comment), ("returned", "Қайта қараңыз"))
        self.assertEqual(StageProgress.objects.get(enrollment=self.e1, stage=self.practice).status, S.IN_PROGRESS)
        self.assertTrue(Notification.objects.filter(user=self.s1, kind="returned").exists())
        self.assertFalse(TeacherReview.objects.exists())

    def test_next_goes_to_the_next_work(self):
        second = PracticeSubmission.objects.create(
            enrollment=self.e1, stage=self.practice, attempt_no=2, status="needs_review", percent=Decimal("30")
        )
        r = self.post(1, 0, action="confirm")
        self.assertRedirects(r, reverse("teacher:grading_detail", args=[second.pk]), fetch_redirect_response=False)


class CommentTests(GradingBase):
    def test_teacher_and_student_talk(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("teacher:comment"),
                {"kind": "practice", "id": self.submission.pk, "body": "Теңдеуді тексеріңіз", "next": self.url()},
            )
        first = Comment.objects.get()
        self.assertEqual((first.author, first.enrollment, first.stage), (self.teacher, self.e1, self.practice))
        note = Notification.objects.get(user=self.s1, kind="comment")
        self.assertTrue(note.url.endswith(f"/learn/chemistry/1/{self.practice.pk}/#comments"))

        self.client.force_login(self.s1)
        r = self.client.get(reverse("student:stage", args=["chemistry", 1, self.practice.pk]))
        self.assertContains(r, "Теңдеуді тексеріңіз")
        first.refresh_from_db()
        self.assertTrue(first.is_read)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("student:comment", args=["chemistry", 1, self.practice.pk]),
                {"kind": "practice", "id": self.submission.pk, "body": "Түсіндім", "parent": first.pk},
            )
        reply = Comment.objects.get(parent=first)
        self.assertEqual(reply.author, self.s1)
        note = Notification.objects.get(user=self.teacher, kind="comment")
        self.assertEqual(note.url, self.url())

    def test_student_cannot_comment_on_someone_elses_work(self):
        self.client.force_login(self.s2)
        r = self.client.post(
            reverse("student:comment", args=["chemistry", 1, self.practice.pk]),
            {"kind": "practice", "id": self.submission.pk, "body": "x"},
        )
        self.assertIn(r.status_code, (302, 404))
        self.assertFalse(Comment.objects.exists())

    def test_other_teacher_cannot_comment(self):
        self.client.force_login(self.other)
        r = self.client.post(reverse("teacher:comment"), {"kind": "practice", "id": self.submission.pk, "body": "x"})
        self.assertEqual(r.status_code, 404)

    def test_empty_comment(self):
        self.client.post(reverse("teacher:comment"), {"kind": "practice", "id": self.submission.pk, "body": "  "})
        self.assertFalse(Comment.objects.exists())

    def test_lab_attempt_comment_reaches_the_lab_page(self):
        lab = next(s for s in self.stages if s.kind == "lab")
        progress.unlock_stage(self.e1, lab, self.teacher)
        attempt = LabAttempt.objects.create(
            user=self.s1, enrollment=self.e1, stage=lab, lab_key="t01", experiment_key="hydrogen"
        )
        self.client.post(reverse("teacher:comment"), {"kind": "lab", "id": attempt.pk, "body": "Қауіпсіздік!"})
        self.client.force_login(self.s1)
        r = self.client.get(reverse("student:stage", args=["chemistry", 1, lab.pk]))
        self.assertEqual(len(r.context["lab_threads"]), 1)
        self.assertContains(r, "Қауіпсіздік!")

    def test_dashboard_shows_the_comment(self):
        self.client.post(reverse("teacher:comment"), {"kind": "practice", "id": self.submission.pk, "body": "Жарайсың"})
        self.client.force_login(self.s1)
        r = self.client.get(reverse("student:dashboard"))
        self.assertEqual(r.context["comments"][0]["body"], "Жарайсың")
