import json

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Question, QuizAttempt
from apps.courses.models import Course, Enrollment, Stage
from apps.courses.services import enroll
from apps.organizations.testing import make_student
from apps.progress import services as progress
from apps.progress.models import StageProgress

S = StageProgress.Status


def answers(attempt, correct=True):
    data = {}
    for qid in attempt.question_ids:
        q = Question.objects.get(pk=qid)
        choices = list(q.choices.all())
        if q.kind in ("single", "multiple"):
            picked = [c.pk for c in choices if c.is_correct == correct] or [choices[0].pk]
            data[f"q{qid}"] = picked if q.kind == "multiple" else picked[0]
        elif q.kind == "numeric":
            data[f"q{qid}"] = str(q.numeric_answer) if correct else "999"
        else:
            data[f"q{qid}"] = q.accepted_answers[0] if correct else "жоқ"
    return data


@override_settings(ALLOWED_HOSTS=["testserver"])
class StudentFlowBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")
        stages = {}
        for s in Stage.objects.filter(topic__number=1).order_by("order"):
            stages.setdefault(s.kind, s)
        cls.theory, cls.video, cls.lab, cls.test = stages["theory"], stages["video"], stages["lab"], stages["test"]

    def setUp(self):
        self.student = make_student("s1", first_name="Айгерім", last_name="С")
        self.enrollment = enroll(self.student, self.course, "admin")
        self.client.force_login(self.student)

    def url(self, stage, name="student:stage", *extra):
        return reverse(name, args=["chemistry", 1, stage.pk, *extra])

    def status(self, stage):
        return StageProgress.objects.get(enrollment=self.enrollment, stage=stage).status

    def take_quiz(self, stage, correct=True, user=None):
        self.client.get(self.url(stage, "student:quiz_take"))
        attempt = QuizAttempt.objects.filter(user=user or self.student).order_by("-pk").first()
        self.client.post(self.url(stage, "student:quiz_submit", attempt.pk), answers(attempt, correct))
        attempt.refresh_from_db()
        return attempt


class CoursePagesTests(StudentFlowBase):
    def test_my_courses_and_continue(self):
        r = self.client.get(reverse("student:courses"))
        self.assertContains(r, self.course.title)
        self.assertContains(r, self.url(self.theory))  # «Continue» goes to the first open stage

    def test_open_course_enrolment(self):
        other = make_student("s2")
        self.client.force_login(other)
        r = self.client.get(reverse("student:courses"))
        self.assertContains(r, reverse("student:enroll", args=["chemistry"]))
        r = self.client.post(reverse("student:enroll", args=["chemistry"]))
        self.assertRedirects(r, reverse("student:course", args=["chemistry"]))
        self.assertTrue(Enrollment.objects.filter(student=other, course=self.course).exists())

    def test_course_map_shows_states(self):
        r = self.client.get(reverse("student:course", args=["chemistry"]))
        self.assertContains(r, "Сутегі және оттегі")
        self.assertContains(r, self.url(self.theory))
        self.assertContains(r, reverse("student:topic", args=["chemistry", 1]))
        self.assertEqual(r.context["stages_total"], 6)
        self.assertEqual(r.context["stages_passed"], 0)

    def test_topic_page_has_stepper_with_every_stage(self):
        r = self.client.get(reverse("student:topic", args=["chemistry", 1]))
        self.assertEqual(len(r.context["stepper"]), 6)
        self.assertEqual([s["status"] for s in r.context["stepper"]][:2], [S.AVAILABLE, S.LOCKED])
        self.assertEqual(r.context["target"], self.theory)

    def test_old_course_url_redirects(self):
        self.assertRedirects(self.client.get("/courses/"), reverse("student:courses"), fetch_redirect_response=False)

    def test_not_enrolled_or_dropped_gets_404(self):
        Enrollment.objects.filter(pk=self.enrollment.pk).update(status="dropped")
        self.assertEqual(self.client.get(reverse("student:course", args=["chemistry"])).status_code, 404)
        self.assertEqual(self.client.get(self.url(self.theory)).status_code, 404)


class GatingTests(StudentFlowBase):
    def test_locked_stage_shows_what_to_finish_first(self):
        r = self.client.get(self.url(self.video))
        self.assertTemplateUsed(r, "student/locked.html")
        self.assertEqual(r.context["blocking"], self.theory)
        self.assertContains(r, self.url(self.theory))

    def test_locked_stage_actions_do_nothing(self):
        self.client.post(self.url(self.video, "student:material_done"))
        self.client.post(self.url(self.video, "student:watch"), json.dumps({"percent": 100}), "application/json")
        self.client.get(self.url(self.test, "student:quiz_take"))
        self.assertEqual(self.status(self.video), S.LOCKED)
        self.assertFalse(QuizAttempt.objects.exists())

    def test_stage_opened_by_teacher(self):
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        progress.unlock_stage(self.enrollment, self.test, teacher)
        r = self.client.get(self.url(self.test))
        self.assertTemplateUsed(r, "student/stage.html")


class TheoryAndQuizTests(StudentFlowBase):
    def test_checkpoint_opens_after_reading_and_passing_opens_the_next_stage(self):
        r = self.client.get(self.url(self.theory))
        self.assertContains(r, "Сутегі")
        self.assertEqual(self.status(self.theory), S.IN_PROGRESS)
        self.assertFalse(r.context["quiz_open"])
        # the quiz cannot be opened before the theory is read
        self.assertRedirects(self.client.get(self.url(self.theory, "student:quiz_take")), self.url(self.theory))
        self.client.post(self.url(self.theory, "student:material_done"))
        sp = StageProgress.objects.get(enrollment=self.enrollment, stage=self.theory)
        self.assertIsNotNone(sp.material_done_at)
        attempt = self.take_quiz(self.theory)
        self.assertEqual(attempt.enrollment, self.enrollment)
        self.assertTrue(attempt.passed)
        self.assertEqual(self.status(self.theory), S.PASSED)
        self.assertEqual(self.status(self.video), S.AVAILABLE)
        r = self.client.get(self.url(self.theory, "student:quiz_review", attempt.pk))
        self.assertContains(r, self.url(self.video))  # «Go to the next stage»

    def test_failed_checkpoint_keeps_the_next_stage_locked(self):
        self.client.post(self.url(self.theory, "student:material_done"))
        attempt = self.take_quiz(self.theory, correct=False)
        self.assertFalse(attempt.passed)
        self.assertEqual(self.status(self.theory), S.IN_PROGRESS)
        self.assertEqual(self.status(self.video), S.LOCKED)
        r = self.client.get(self.url(self.theory))
        self.assertContains(r, self.url(self.theory, "student:quiz_retry"))

    def test_exhausted_attempts_pass_with_attention(self):
        """D26: three failed checkpoint attempts → passed with «needs attention», the next stage opens."""
        self.client.post(self.url(self.theory, "student:material_done"))
        for _ in range(3):
            self.client.post(self.url(self.theory, "student:quiz_retry"))
            self.take_quiz(self.theory, correct=False)
        sp = StageProgress.objects.get(enrollment=self.enrollment, stage=self.theory)
        self.assertEqual((sp.status, sp.needs_attention), (S.PASSED, True))
        self.assertEqual(self.status(self.video), S.AVAILABLE)
        self.assertEqual(QuizAttempt.objects.filter(user=self.student).count(), 3)

    def test_theory_html_is_sanitised(self):
        content = self.theory.theory_content
        content.body = '<p onclick="x()">H<sub>2</sub>O</p><script>alert(1)</script>'
        content.save()
        r = self.client.get(self.url(self.theory))
        self.assertContains(r, "<p>H<sub>2</sub>O</p>")
        self.assertNotContains(r, "alert(1)")

    def test_attempts_of_others_and_other_stages_are_hidden(self):
        self.client.post(self.url(self.theory, "student:material_done"))
        attempt = self.take_quiz(self.theory)
        other = make_student("s2")
        enroll(other, self.course, "admin")
        self.client.force_login(other)
        self.client.post(self.url(self.theory, "student:material_done"))
        self.assertEqual(self.client.get(self.url(self.theory, "student:quiz_review", attempt.pk)).status_code, 404)

    def test_time_on_the_stage(self):
        self.client.get(self.url(self.theory))
        self.client.post(self.url(self.theory, "student:ping"))
        self.assertEqual(StageProgress.objects.get(enrollment=self.enrollment, stage=self.theory).time_spent_s, 30)


class VideoAndTestStageTests(StudentFlowBase):
    def pass_theory(self):
        self.client.post(self.url(self.theory, "student:material_done"))
        self.take_quiz(self.theory)

    def test_video_watch_percentage(self):
        self.pass_theory()
        video = self.video.video_content
        video.url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        video.save()
        r = self.client.get(self.url(self.video))
        self.assertContains(r, "videoTracker")
        self.assertContains(r, "dQw4w9WgXcQ")

        def post(percent):
            return self.client.post(
                self.url(self.video, "student:watch"), json.dumps({"percent": percent}), "application/json"
            )

        self.assertEqual(post(50).json(), {"percent": 50, "done": False})
        self.assertEqual(post(30).json()["percent"], 50)  # never goes down
        self.assertEqual(self.client.post(self.url(self.video, "student:material_done")).status_code, 404)
        self.assertEqual(post(85).json(), {"percent": 85, "done": True})
        self.assertEqual(self.client.get(self.url(self.video)).context["quiz_open"], True)

    def test_video_without_a_source_can_be_skipped(self):
        self.pass_theory()
        r = self.client.get(self.url(self.video))
        self.assertContains(r, self.url(self.video, "student:material_done"))
        self.client.post(self.url(self.video, "student:material_done"))
        attempt = self.take_quiz(self.video)
        self.assertTrue(attempt.passed)
        self.assertEqual(self.status(self.lab), S.AVAILABLE)
        r = self.client.get(self.url(self.lab))
        self.assertContains(r, self.url(self.lab, "student:lab_run", "hydrogen"))

    def test_topic_test_opens_without_material(self):
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        progress.unlock_stage(self.enrollment, self.test, teacher)
        r = self.client.get(self.url(self.test))
        self.assertTrue(r.context["quiz_open"])
        attempt = self.take_quiz(self.test)
        self.assertEqual(attempt.percent, 100)
        self.assertEqual(self.status(self.test), S.PASSED)


class PreviewTests(StudentFlowBase):
    def test_teacher_sees_every_stage_without_progress(self):
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.course.course_teachers.create(teacher=teacher)
        self.client.force_login(teacher)
        r = self.client.get(self.url(self.test))
        self.assertTrue(r.context["place"].preview)
        self.assertContains(r, "Алдын ала қарау")  # the preview banner
        attempt = self.take_quiz(self.test, user=teacher)
        self.assertIsNone(attempt.enrollment)
        self.assertFalse(StageProgress.objects.filter(enrollment__student=teacher).exists())
        self.assertEqual(self.client.get(reverse("student:course", args=["chemistry"])).status_code, 200)

    def test_teacher_of_another_course_gets_404(self):
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(self.url(self.theory)).status_code, 404)


class InlineQuizTests(StudentFlowBase):
    """STEP-18: the checkpoint quiz is played on the theory page, question by question."""

    def test_inline_quiz_flow(self):
        quiz = self.theory.checkpoint_quiz
        self.assertTrue(quiz.instant_feedback)
        self.client.post(self.url(self.theory, "student:material_done"))
        r = self.client.get(self.url(self.theory, "student:quiz_take"))
        self.assertRedirects(r, self.url(self.theory) + "#quiz", fetch_redirect_response=False)
        attempt = QuizAttempt.objects.get(user=self.student, quiz=quiz)
        r = self.client.get(self.url(self.theory))
        rows = r.context["inline_rows"]
        self.assertEqual(len(rows), len(attempt.question_ids))
        self.assertEqual(r.context["inline_current"], 0)
        self.assertContains(r, rows[0]["check_url"])
        # check every question with its correct option
        right = answers(attempt, correct=True)
        for row in rows:
            key = f"q{row['question'].pk}"
            r = self.client.post(row["check_url"], {key: right[key]}, headers={"HX-Request": "true"})
            self.assertContains(r, "bg-success-50")
        self.assertContains(r, self.url(self.theory, "student:quiz_submit", attempt.pk))  # «See the result»
        r = self.client.post(self.url(self.theory, "student:quiz_submit", attempt.pk))
        self.assertRedirects(r, self.url(self.theory) + f"?result={attempt.pk}#quiz", fetch_redirect_response=False)
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)
        self.assertEqual(self.status(self.theory), S.PASSED)
        r = self.client.get(self.url(self.theory), {"result": attempt.pk})
        self.assertEqual(r.context["result_dialog"]["correct"], len(rows))
        self.assertContains(r, "<dialog")
        self.assertContains(r, self.url(self.video))  # «Next: …»

    def test_check_needs_the_open_quiz_and_own_attempt(self):
        self.client.post(self.url(self.theory, "student:material_done"))
        self.client.get(self.url(self.theory, "student:quiz_take"))
        attempt = QuizAttempt.objects.get(user=self.student)
        qid = attempt.question_ids[0]
        other = make_student("s2")
        enroll(other, self.course, "admin")
        self.client.force_login(other)
        self.client.post(self.url(self.theory, "student:material_done"))
        r = self.client.post(self.url(self.theory, "student:quiz_check", attempt.pk, qid), {})
        self.assertEqual(r.status_code, 404)
