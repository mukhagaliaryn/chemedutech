"""STEP-22: the course's pre/post knowledge test — pre before the first stage, post after the course."""

from django.urls import reverse

from apps.assessments.models import Choice, Question, Quiz, QuizAttempt
from apps.assessments.services import authoring as quiz_authoring
from apps.courses.models import CourseGroup
from apps.courses.services import assign_group, authoring, set_posttest_open
from apps.organizations.testing import make_group, make_student
from apps.progress import services as progress
from apps.progress.models import CourseResult
from apps.progress.services import benchmark

from .tests import StudentFlowBase, answers


def make_benchmark(course, n=4):
    quiz = quiz_authoring.create_quiz("Білім тесті", Quiz.Kind.BENCHMARK)
    for i in range(n):
        q = Question.objects.create(quiz=quiz, order=i, kind="single", text=f"<p>Сұрақ {i}</p>")
        Choice.objects.create(question=q, order=1, text="иә", is_correct=True)
        Choice.objects.create(question=q, order=2, text="жоқ", is_correct=False)
    authoring.attach_benchmark(course, quiz)
    return quiz


class BenchmarkBase(StudentFlowBase):
    def setUp(self):
        super().setUp()
        self.quiz = make_benchmark(self.course)
        self.course.refresh_from_db()

    def bm_url(self, phase, name="student:benchmark", *extra):
        return reverse(name, args=["chemistry", phase, *extra])

    def take(self, phase, correct=True):
        self.client.post(self.bm_url(phase, "student:benchmark_start"))
        attempt = QuizAttempt.objects.get(user=self.student, quiz=self.quiz, phase=phase, finished_at=None)
        self.client.post(self.bm_url(phase, "student:benchmark_submit", attempt.pk), answers(attempt, correct))
        attempt.refresh_from_db()
        return attempt


class PretestTests(BenchmarkBase):
    def test_new_student_must_take_the_pretest_before_the_first_stage(self):
        self.assertTrue(benchmark.pretest_required(self.enrollment))
        r = self.client.get(self.url(self.theory))
        self.assertRedirects(r, self.bm_url("pre"))
        r = self.client.get(reverse("student:course", args=["chemistry"]))
        self.assertContains(r, self.bm_url("pre"))

    def test_pretest_once_then_the_stages_open(self):
        attempt = self.take("pre", correct=False)
        self.assertTrue(attempt.is_finished)
        self.assertEqual(attempt.percent, 0)
        self.assertEqual(attempt.enrollment, self.enrollment)
        self.assertEqual(benchmark.pretest_state(self.enrollment), benchmark.DONE)
        self.assertEqual(self.client.get(self.url(self.theory)).status_code, 200)
        # a second attempt is refused
        self.client.post(self.bm_url("pre", "student:benchmark_start"))
        self.assertEqual(QuizAttempt.objects.filter(user=self.student, phase="pre").count(), 1)

    def test_done_page_shows_only_the_percent(self):
        self.take("pre")
        r = self.client.get(self.bm_url("pre"))
        self.assertContains(r, "100%")
        self.assertNotContains(r, "иә")  # neither the options nor the right answers

    def test_pretest_does_not_touch_progress_or_grades(self):
        self.take("pre")
        progress.recalculate(self.enrollment)
        result = CourseResult.objects.get(enrollment=self.enrollment)
        self.assertIsNone(result.current_percent)
        self.assertFalse(self.enrollment.stage_progress.filter(status="passed").exists())

    def test_students_who_already_started_are_not_sent_back(self):
        progress.complete_material(self.enrollment, self.theory)
        progress.complete_stage(self.enrollment, self.theory, 100, passed=True)
        self.assertEqual(benchmark.pretest_state(self.enrollment), benchmark.NONE)
        self.assertEqual(self.client.get(self.url(self.theory)).status_code, 200)

    def test_empty_test_gates_nobody(self):
        self.quiz.questions.all().delete()
        self.assertFalse(benchmark.pretest_required(self.enrollment))

    def test_teacher_preview_is_not_gated(self):
        from apps.accounts.models import User

        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.ADMIN)
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(self.url(self.theory)).status_code, 200)


class PosttestTests(BenchmarkBase):
    def setUp(self):
        super().setUp()
        self.take("pre", correct=False)

    def test_posttest_locked_until_the_course_is_completed(self):
        self.assertEqual(benchmark.posttest_state(self.enrollment), benchmark.LOCKED)
        self.client.post(self.bm_url("post", "student:benchmark_start"))
        self.assertFalse(QuizAttempt.objects.filter(user=self.student, phase="post").exists())
        CourseResult.objects.update_or_create(enrollment=self.enrollment, defaults={"score_percent": 80})
        self.assertEqual(benchmark.posttest_state(self.enrollment), benchmark.OPEN)
        attempt = self.take("post")
        self.assertEqual(attempt.percent, 100)
        self.assertEqual(attempt.attempt_no, 2)  # numbered over both phases, one attempt each
        self.assertEqual(benchmark.posttest_state(self.enrollment), benchmark.DONE)

    def test_teacher_opens_the_posttest_for_the_group(self):
        group = make_group(name="Хим-1")
        student = make_student("s9", group=group)
        assign_group(self.course, group)
        enrollment = student.enrollments.get(course=self.course)
        self.assertEqual(benchmark.posttest_state(enrollment), benchmark.LOCKED)
        set_posttest_open(CourseGroup.objects.get(course=self.course, group=group), True)
        self.assertEqual(benchmark.posttest_state(enrollment), benchmark.OPEN)

    def test_stage_quizzes_ignore_the_phases(self):
        self.client.post(self.url(self.theory, "student:material_done"))
        attempt = self.take_quiz(self.theory)
        self.assertEqual(attempt.phase, "")
        self.assertEqual(attempt.attempt_no, 1)
