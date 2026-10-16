import random
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.courses.models import Course, Stage
from apps.courses.services import enroll
from apps.organizations.testing import make_student

from . import selectors, services
from .models import AttemptAnswer, Choice, Question, Quiz, QuizAttempt


def make_quiz(**fields):
    return Quiz.objects.create(title=fields.pop("title", "Q"), **fields)


def single(quiz, order=1, points=1, correct_index=0, n=3):
    q = Question.objects.create(quiz=quiz, order=order, kind="single", text=f"<p>S{order}</p>", points=points)
    choices = [
        Choice.objects.create(question=q, order=i, text=f"opt{i}", is_correct=i == correct_index) for i in range(n)
    ]
    return q, choices


class GradingTests(TestCase):
    def setUp(self):
        self.quiz = make_quiz()

    def test_single(self):
        q, ch = single(self.quiz, points=2)
        self.assertEqual(services.grade(q, ch[0].pk).points, Decimal("2"))
        self.assertFalse(services.grade(q, ch[1].pk).is_correct)
        self.assertFalse(services.grade(q, None).is_correct)
        self.assertFalse(services.grade(q, "junk").is_correct)
        # two values for a single-choice question: only the first one counts
        self.assertEqual(services.grade(q, [ch[1].pk, ch[0].pk]).choice_ids, [ch[0].pk])

    def test_multiple_needs_the_exact_set(self):
        q = Question.objects.create(quiz=self.quiz, kind="multiple", text="m")
        a, b, c = (Choice.objects.create(question=q, text=t, is_correct=t != "c") for t in "abc")
        self.assertTrue(services.grade(q, [a.pk, b.pk]).is_correct)
        self.assertTrue(services.grade(q, [str(b.pk), str(a.pk)]).is_correct)
        self.assertFalse(services.grade(q, [a.pk]).is_correct)
        self.assertFalse(services.grade(q, [a.pk, b.pk, c.pk]).is_correct)
        self.assertFalse(services.grade(q, []).is_correct)

    def test_choice_of_another_question_is_ignored(self):
        q, _ = single(self.quiz)
        _other_q, other = single(self.quiz, order=2)
        self.assertEqual(services.grade(q, other[0].pk).choice_ids, [])

    def test_numeric_comma_dot_and_tolerance(self):
        q = Question.objects.create(
            quiz=self.quiz, kind="numeric", text="n", numeric_answer=Decimal("2.24"), numeric_tolerance=Decimal("0.02")
        )
        for raw in ("2,24", "2.24", " 2.25 ", "2.22"):
            self.assertTrue(services.grade(q, raw).is_correct, raw)
        for raw in ("2.27", "", "abc", "2,2,4", "inf"):
            self.assertFalse(services.grade(q, raw).is_correct, raw)
        self.assertEqual(services.grade(q, "2,24").numeric_value, Decimal("2.24"))

    def test_numeric_exact_and_negative(self):
        q = Question.objects.create(quiz=self.quiz, kind="numeric", text="n", numeric_answer=Decimal("-3"))
        self.assertTrue(services.grade(q, "−3").is_correct)  # unicode minus
        self.assertFalse(services.grade(q, "-3.01").is_correct)

    def test_short_text_normalisation(self):
        q = Question.objects.create(
            quiz=self.quiz, kind="short_text", text="t", accepted_answers=["күркіреуік газ", "Катализатор"]
        )
        for raw in ("Күркіреуік   газ.", "КАТАЛИЗАТОР", " катализатор! "):
            self.assertTrue(services.grade(q, raw).is_correct, raw)
        for raw in ("күркіреуік", "", "катализаторлар"):
            self.assertFalse(services.grade(q, raw).is_correct, raw)


class AttemptTests(TestCase):
    def setUp(self):
        self.user = make_student("s1")
        self.quiz = make_quiz(max_attempts=2, pass_percent=50)
        self.q1, self.c1 = single(self.quiz, order=1)
        self.q2, self.c2 = single(self.quiz, order=2, points=3)

    def test_submit_scores_and_passes(self):
        attempt = services.start_attempt(self.user, self.quiz)
        self.assertEqual(attempt.attempt_no, 1)
        services.submit_attempt(attempt, {self.q1.pk: self.c1[0].pk, str(self.q2.pk): self.c2[1].pk})
        attempt.refresh_from_db()
        self.assertEqual((attempt.score, attempt.max_score), (Decimal("1.00"), Decimal("4.00")))
        self.assertEqual(attempt.percent, Decimal("25.00"))
        self.assertFalse(attempt.passed)
        self.assertEqual(AttemptAnswer.objects.filter(attempt=attempt).count(), 2)
        self.assertEqual(list(attempt.answers.get(question=self.q1).choices.all()), [self.c1[0]])
        with self.assertRaises(services.AttemptError):
            services.submit_attempt(attempt, {})

    def test_unfinished_attempt_is_resumed_not_duplicated(self):
        a1 = services.start_attempt(self.user, self.quiz)
        a2 = services.start_attempt(self.user, self.quiz)
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(services.attempts_left(self.user, self.quiz), 1)

    def test_attempt_limit(self):
        for _ in range(2):
            services.submit_attempt(services.start_attempt(self.user, self.quiz), {})
        self.assertEqual(services.attempts_left(self.user, self.quiz), 0)
        with self.assertRaises(services.AttemptError):
            services.start_attempt(self.user, self.quiz)
        self.quiz.max_attempts = None
        self.quiz.save()
        self.assertIsNone(services.attempts_left(self.user, self.quiz))
        self.assertEqual(services.start_attempt(self.user, self.quiz).attempt_no, 3)

    def test_inactive_questions_are_not_asked(self):
        self.q2.is_active = False
        self.q2.save()
        attempt = services.start_attempt(self.user, self.quiz)
        self.assertEqual(attempt.question_ids, [self.q1.pk])

    def test_empty_quiz(self):
        with self.assertRaises(services.AttemptError):
            services.start_attempt(self.user, make_quiz(title="empty"))

    def test_pool_selection_and_stable_order(self):
        quiz = make_quiz(questions_per_attempt=3, shuffle_choices=True)
        questions = [single(quiz, order=i, n=4)[0] for i in range(1, 9)]
        attempt = services.start_attempt(self.user, quiz, rng=random.Random(7))
        self.assertEqual(len(attempt.question_ids), 3)
        self.assertTrue(set(attempt.question_ids) <= {q.pk for q in questions})
        # not shuffled: the sample keeps the authoring order
        orders = [Question.objects.get(pk=pk).order for pk in attempt.question_ids]
        self.assertEqual(orders, sorted(orders))
        # every asked question has its option order fixed for the whole attempt (reload-safe)
        self.assertEqual(set(attempt.choice_order), {str(pk) for pk in attempt.question_ids})
        rows = selectors.review_rows(attempt)
        self.assertEqual(
            [r["choice"].pk for r in rows[0]["choices"]], attempt.choice_order[str(rows[0]["question"].pk)]
        )
        # different seeds draw different pools
        pools = {tuple(services.pick_questions(quiz, random.Random(s))[0]) for s in range(20)}
        self.assertGreater(len(pools), 1)

    def test_shuffle_questions(self):
        quiz = make_quiz(shuffle_questions=True, shuffle_choices=False)
        ids = [single(quiz, order=i)[0].pk for i in range(1, 7)]
        orders = {tuple(services.pick_questions(quiz, random.Random(s))[0]) for s in range(10)}
        self.assertGreater(len(orders), 1)
        self.assertTrue(all(sorted(o) == sorted(ids) for o in orders))
        _ids, choice_order = services.pick_questions(quiz, random.Random(1))
        for order in choice_order.values():
            self.assertEqual(order, sorted(order))  # options keep their authoring order

    def test_time_limit(self):
        self.quiz.time_limit_min = 10
        self.quiz.save()
        attempt = services.start_attempt(self.user, self.quiz)
        QuizAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=11))
        attempt.refresh_from_db()
        self.assertTrue(services.is_expired(attempt))
        # a late submission is closed with no answers counted
        services.submit_attempt(attempt, {self.q1.pk: self.c1[0].pk})
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, Decimal("0.00"))

    def test_expired_open_attempt_is_closed_on_start(self):
        self.quiz.time_limit_min = 5
        self.quiz.save()
        first = services.start_attempt(self.user, self.quiz)
        QuizAttempt.objects.filter(pk=first.pk).update(started_at=timezone.now() - timedelta(minutes=6))
        second = services.start_attempt(self.user, self.quiz)
        first.refresh_from_db()
        self.assertTrue(first.is_finished)
        self.assertEqual(second.attempt_no, 2)

    def test_grading_strategies(self):
        self.quiz.max_attempts = None
        self.quiz.save()
        answers = [{}, {self.q1.pk: self.c1[0].pk, self.q2.pk: self.c2[0].pk}, {self.q1.pk: self.c1[0].pk}]
        attempts = []
        for a in answers:
            attempts.append(services.submit_attempt(services.start_attempt(self.user, self.quiz), a))
        self.assertEqual(selectors.counted_attempt(self.user, self.quiz), attempts[1])  # best = 100 %
        self.quiz.grading = Quiz.Grading.LAST
        self.assertEqual(selectors.counted_attempt(self.user, self.quiz), attempts[2])
        self.quiz.grading = Quiz.Grading.FIRST
        self.assertEqual(selectors.counted_attempt(self.user, self.quiz), attempts[0])

    def test_research_data_is_protected(self):
        attempt = services.submit_attempt(services.start_attempt(self.user, self.quiz), {self.q1.pk: self.c1[0].pk})
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.c1[0].delete()
        with self.assertRaises(ProtectedError):
            self.q1.delete()
        with self.assertRaises(ProtectedError):
            attempt.delete()


class QuizViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")
        cls.stage = Stage.objects.get(topic__number=1, kind="theory")
        cls.quiz = cls.stage.checkpoint_quiz
        cls.student = make_student("s1")

    def correct_answers(self, attempt):
        data = {}
        for qid in attempt.question_ids:
            q = Question.objects.get(pk=qid)
            correct = [c.pk for c in q.choices.filter(is_correct=True)]
            if q.kind == "multiple":
                data[f"q{qid}"] = correct
            elif q.kind == "single":
                data[f"q{qid}"] = correct[0]
            elif q.kind == "numeric":
                data[f"q{qid}"] = str(q.numeric_answer).replace(".", ",")
            elif q.kind in ("formula", "equation"):
                data[f"q{qid}"] = q.accepted_answers[0]
            else:
                data[f"q{qid}"] = q.accepted_answers[0].upper()
        return data

    def test_seed_links_quizzes_to_stages(self):
        self.assertEqual(self.quiz.questions.count(), 4)
        self.assertEqual(Stage.objects.get(topic__number=1, kind="video").checkpoint_quiz.questions.count(), 3)
        test = Stage.objects.get(topic__number=1, kind="test").test_content.quiz
        self.assertEqual(
            set(test.questions.values_list("kind", flat=True)),
            {"single", "multiple", "numeric", "short_text", "formula", "equation"},
        )
        call_command("seed_course", verbosity=0)
        self.assertEqual(Quiz.objects.count(), 3)
        self.assertEqual(test.questions.count(), 10)

    def test_not_enrolled_student_gets_404(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("assessments:take", args=[self.quiz.pk])).status_code, 404)

    def test_take_submit_result_flow(self):
        enroll(self.student, self.course, "admin")
        self.client.force_login(self.student)
        r = self.client.get(reverse("assessments:take", args=[self.quiz.pk]))
        self.assertContains(r, "quizPlayer")
        attempt = QuizAttempt.objects.get(user=self.student)
        self.assertIsNotNone(attempt.enrollment)
        r = self.client.post(reverse("assessments:submit", args=[attempt.pk]), self.correct_answers(attempt))
        self.assertRedirects(r, reverse("assessments:result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.percent, Decimal("100.00"))
        self.assertTrue(attempt.passed)
        r = self.client.get(reverse("assessments:result", args=[attempt.pk]))
        self.assertContains(r, "100%")
        self.assertContains(r, self.quiz.questions.first().explanation)  # show_answers_after
        # taking again shows the result; retry starts attempt 2
        self.assertRedirects(
            self.client.get(reverse("assessments:take", args=[self.quiz.pk])),
            reverse("assessments:result", args=[attempt.pk]),
        )
        self.client.post(reverse("assessments:retry", args=[self.quiz.pk]))
        self.assertEqual(QuizAttempt.objects.filter(user=self.student).count(), 2)

    def test_hidden_answers_for_topic_test(self):
        enroll(self.student, self.course, "admin")
        self.client.force_login(self.student)
        test = Stage.objects.get(topic__number=1, kind="test").test_content.quiz
        self.client.get(reverse("assessments:take", args=[test.pk]))
        attempt = QuizAttempt.objects.get(user=self.student, quiz=test)
        self.client.post(reverse("assessments:submit", args=[attempt.pk]), {})
        r = self.client.get(reverse("assessments:result", args=[attempt.pk]))
        self.assertContains(r, "0%")
        for q in test.questions.exclude(explanation=""):
            self.assertNotContains(r, q.explanation)

    def test_other_users_attempt_is_hidden(self):
        enroll(self.student, self.course, "admin")
        attempt = services.start_attempt(self.student, self.quiz)
        other = make_student("s2")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("assessments:result", args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("assessments:submit", args=[attempt.pk])).status_code, 404)

    def test_teacher_preview_without_enrolment(self):
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(reverse("assessments:take", args=[self.quiz.pk])).status_code, 200)
        self.assertIsNone(QuizAttempt.objects.get(user=teacher).enrollment)

    def test_admin_pages(self):
        admin = User.objects.create_superuser("root", "root@example.kz", "x")
        enroll(self.student, self.course, "admin")
        attempt = services.submit_attempt(services.start_attempt(self.student, self.quiz), {})
        self.client.force_login(admin)
        for url in (
            reverse("admin:assessments_quiz_change", args=[self.quiz.pk]),
            reverse("admin:assessments_question_change", args=[self.quiz.questions.first().pk]),
            reverse("admin:assessments_question_add"),
            reverse("admin:assessments_quizattempt_change", args=[attempt.pk]),
            reverse("admin:assessments_quizattempt_changelist"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
