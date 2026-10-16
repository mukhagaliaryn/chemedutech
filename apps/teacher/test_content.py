"""STEP-11 (3/3): the course content editor — structure, order, stage content, quizzes, practice fields."""

import json
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.assessments.models import AttemptAnswer, Choice, Question, QuizAttempt
from apps.courses.models import CourseTeacher, LabContent, Module, Stage, Topic
from apps.practice.models import PracticeAnswer, PracticeItem, PracticeSubmission
from apps.progress import services as progress

from .tests import TeacherBase


class ContentBase(TeacherBase):
    def setUp(self):
        super().setUp()
        self.module = Module.objects.get(course=self.course, order=1)
        self.topic = self.stages[0].topic

    def url(self, name, *args):
        return reverse(name, args=["chemistry", *args])


class AccessTests(ContentBase):
    def test_author_edits_assistant_reads(self):
        self.assertEqual(self.client.get(self.url("teacher:course_content")).status_code, 200)
        self.assertEqual(self.client.get(self.url("teacher:course_settings")).status_code, 200)
        CourseTeacher.objects.create(course=self.course, teacher=self.other, role="assistant")
        self.client.force_login(self.other)
        r = self.client.get(self.url("teacher:course_content"))
        self.assertFalse(r.context["course"].can_edit)
        self.assertEqual(self.client.get(self.url("teacher:course_settings")).status_code, 403)
        self.assertEqual(self.client.post(self.url("teacher:module_new"), {"title": "x", "weight": 1}).status_code, 403)

    def test_foreign_course_is_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("teacher:course_content")).status_code, 404)


class StructureTests(ContentBase):
    def test_module_and_topic(self):
        r = self.client.post(self.url("teacher:module_new"), {"title": "Бейорганикалық қосылыстар", "weight": "1"})
        module = Module.objects.get(title="Бейорганикалық қосылыстар")
        self.assertEqual(module.order, 3)
        self.assertRedirects(r, self.url("teacher:course_content") + f"#m{module.pk}", fetch_redirect_response=False)
        last = Topic.objects.filter(module__course=self.course).count()
        self.client.post(self.url("teacher:topic_new"), {"module": module.pk, "title": "Жаңа тақырып", "weight": "1"})
        topic = Topic.objects.get(title="Жаңа тақырып")
        self.assertEqual((topic.module, topic.number, topic.is_published), (module, last + 1, False))

    def test_topic_into_an_earlier_module_renumbers(self):
        self.client.post(self.url("teacher:topic_new"), {"module": self.module.pk, "title": "Қосымша", "weight": "1"})
        numbers = list(
            Topic.objects.filter(module__course=self.course).order_by("number").values_list("title", flat=True)
        )
        module1_count = self.module.topics.count()
        self.assertEqual(numbers[module1_count - 1], "Қосымша")
        self.assertEqual(
            list(Topic.objects.filter(module__course=self.course).order_by("number").values_list("number", flat=True)),
            list(range(1, len(numbers) + 1)),
        )

    def test_reorder_stages_and_topics(self):
        ids = [s.pk for s in self.stages]
        new = [ids[1], ids[0], *ids[2:]]
        r = self.client.post(
            self.url("teacher:reorder"),
            json.dumps({"what": "stages", "parent": self.topic.pk, "ids": new}),
            "application/json",
        )
        self.assertEqual(r.json(), {"ok": True})
        self.assertEqual(list(self.topic.stages.order_by("order").values_list("pk", flat=True)), new)
        topics = list(self.module.topics.order_by("number"))
        swapped = [topics[1].pk, topics[0].pk, *[t.pk for t in topics[2:]]]
        self.client.post(
            self.url("teacher:reorder"),
            json.dumps({"what": "topics", "parent": self.module.pk, "ids": swapped}),
            "application/json",
        )
        self.assertEqual(Topic.objects.get(pk=topics[1].pk).number, 1)
        # a stale list is refused
        r = self.client.post(
            self.url("teacher:reorder"),
            json.dumps({"what": "stages", "parent": self.topic.pk, "ids": ids[:2]}),
            "application/json",
        )
        self.assertEqual(r.status_code, 409)

    def test_publish_toggle(self):
        topic = self.module.topics.exclude(pk=self.topic.pk).first()
        self.client.post(self.url("teacher:topic_publish", topic.pk), {"published": "1"})
        topic.refresh_from_db()
        self.assertTrue(topic.is_published)

    def test_course_settings_weights(self):
        data = {
            "title": self.course.title, "status": "published", "enrollment_mode": self.course.enrollment_mode,
            "enroll_code": self.course.enroll_code, "is_sequential": "on", "passing_score": 55,
            "certificate_enabled": "on", "weight_theory": 10, "weight_video": 10, "weight_lab": 50,
            "weight_practice": 15, "weight_test": 15,
        }  # fmt: skip
        r = self.client.post(self.url("teacher:course_settings"), data)
        self.assertEqual(r.status_code, 302)
        self.course.refresh_from_db()
        self.assertEqual((self.course.passing_score, self.course.stage_kind_weights["lab"]), (55, 50))


class StageTests(ContentBase):
    def new_stage(self, kind, title):
        self.client.post(
            self.url("teacher:stage_new"),
            {"topic": self.topic.pk, "kind": kind, "title": title, "is_required": "on", "pass_percent": 60},
        )
        return Stage.objects.get(title=title)

    def test_new_stages_get_their_content(self):
        theory = self.new_stage("theory", "Теория 2")
        self.assertEqual(theory.order, len(self.stages) + 1)
        self.assertIsNotNone(theory.theory_content)
        practice = self.new_stage("practice", "Практика 3")
        self.assertEqual(practice.practice_task.title, "Практика 3")
        lab = self.new_stage("lab", "Зертхана 2")
        r = self.client.post(
            self.url("teacher:stage", lab.pk),
            {"stage-title": "Зертхана 2", "stage-pass_percent": 60, "stage-is_required": "on",
             "content-lab_key": "t01", "content-experiments": ["oxygen", "hydrogen"]},
        )  # fmt: skip
        self.assertEqual(r.status_code, 302)
        self.assertEqual(LabContent.objects.get(stage=lab).experiments, ["hydrogen", "oxygen"])

    def test_checkpoint_quiz_and_questions(self):
        theory = self.new_stage("theory", "Теория 2")
        r = self.client.post(self.url("teacher:stage_quiz_create", theory.pk))
        theory.refresh_from_db()
        quiz = theory.checkpoint_quiz
        self.assertRedirects(r, self.url("teacher:quiz", quiz.pk), fetch_redirect_response=False)
        data = {
            "kind": "single", "text": "<p>Сутегінің формуласы?</p>", "points": 1, "numeric_tolerance": 0,
            "is_active": "on", "choices-count": 3,
            "choices-0-text": "H<sub>2</sub>", "choices-0-correct": "on",
            "choices-1-text": "O<sub>2</sub>", "choices-2-text": "",
        }  # fmt: skip
        r = self.client.post(self.url("teacher:question_new", quiz.pk), data)
        self.assertEqual(r.status_code, 302)
        question = quiz.questions.get()
        self.assertEqual(
            list(question.choices.values_list("text", "is_correct")),
            [("H<sub>2</sub>", True), ("O<sub>2</sub>", False)],
        )
        data["choices-0-correct"] = ""
        r = self.client.post(self.url("teacher:question", quiz.pk, question.pk), data)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["form"].non_field_errors())

    def test_formula_question_is_validated(self):
        theory = self.new_stage("theory", "Теория 3")
        self.client.post(self.url("teacher:stage_quiz_create", theory.pk))
        theory.refresh_from_db()
        data = {"kind": "equation", "text": "<p>?</p>", "points": 1, "numeric_tolerance": 0, "is_active": "on",
                "accepted_answers": "H2 + O2 -> H2O", "choices-count": 0}  # fmt: skip
        r = self.client.post(self.url("teacher:question_new", theory.checkpoint_quiz.pk), data)
        self.assertEqual(r.status_code, 200)
        self.assertIn("accepted_answers", r.context["form"].errors)

    def test_used_stage_is_not_deleted(self):
        practice = next(s for s in self.stages if s.kind == "practice")
        progress.unlock_stage(self.e1, practice, self.teacher)
        PracticeSubmission.objects.create(enrollment=self.e1, stage=practice, attempt_no=1, status="graded")
        r = self.client.post(self.url("teacher:delete", "stage", practice.pk))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Stage.objects.filter(pk=practice.pk).exists())
        fresh = self.new_stage("video", "Видео 2")
        self.client.post(self.url("teacher:delete", "stage", fresh.pk))
        self.assertFalse(Stage.objects.filter(pk=fresh.pk).exists())

    def test_answered_question_is_retired(self):
        quiz = self.stages[0].checkpoint_quiz
        question = quiz.questions.filter(kind="single").first()
        attempt = QuizAttempt.objects.create(
            enrollment=self.e1, user=self.s1, quiz=quiz, attempt_no=1, finished_at=timezone.now()
        )
        answer = AttemptAnswer.objects.create(attempt=attempt, question=question)
        answer.choices.add(question.choices.first())
        self.client.post(self.url("teacher:delete", "question", question.pk))
        question.refresh_from_db()
        self.assertFalse(question.is_active)
        self.assertTrue(Choice.objects.filter(question=question).exists())


class PracticeItemTests(ContentBase):
    def setUp(self):
        super().setUp()
        self.practice = next(s for s in self.stages if s.kind == "practice")

    def test_create_numeric_field_and_try_it(self):
        data = {
            "action": "save",
            "label": "m(Zn)",
            "kind": "numeric",
            "points": 1,
            "answer_spec": '{"value": 6.5, "unit": "g"}',
        }
        r = self.client.post(self.url("teacher:item_new", self.practice.pk), data)
        item = PracticeItem.objects.get(label="m(Zn)")
        self.assertRedirects(r, self.url("teacher:item", self.practice.pk, item.pk), fetch_redirect_response=False)
        r = self.client.post(
            self.url("teacher:item", self.practice.pk, item.pk),
            {"action": "try", "answer": '{"value": "6500", "unit": "мг"}'},
        )
        self.assertTrue(r.context["trial"]["result"].is_correct)

    def test_bad_spec_is_refused(self):
        data = {"action": "save", "label": "x", "kind": "formula", "points": 1, "answer_spec": '{"formula": "Xx2"}'}
        r = self.client.post(self.url("teacher:item_new", self.practice.pk), data)
        self.assertEqual(r.status_code, 200)
        self.assertIn("answer_spec", r.context["form"].errors)

    def test_open_field_rubric(self):
        data = {
            "action": "save", "label": "Жаңа түсіндіру", "kind": "open", "points": 2, "answer_spec": "{}",
            "model_answer": "Сутегі суда нашар ериді.", "notes": "", "criteria-count": 2,
            "criteria-0-text": "Ерігіштігі", "criteria-0-points": "1",
            "criteria-1-text": "Қауіпсіздік", "criteria-1-points": "1",
        }  # fmt: skip
        r = self.client.post(self.url("teacher:item_new", self.practice.pk), data)
        self.assertEqual(r.status_code, 302, r.context and r.context["form"].errors)
        item = PracticeItem.objects.get(label="Жаңа түсіндіру")
        self.assertEqual(
            list(item.rubric.criteria.values_list("text", "points")),
            [("Ерігіштігі", Decimal("1.00")), ("Қауіпсіздік", Decimal("1.00"))],
        )

    def test_answered_field_cannot_be_deleted_or_change_kind(self):
        item = self.practice.practice_task.items.exclude(kind="open").first()
        sub = PracticeSubmission.objects.create(enrollment=self.e1, stage=self.practice, attempt_no=1, status="graded")
        PracticeAnswer.objects.create(submission=sub, item=item, raw_value="1")
        self.client.post(self.url("teacher:delete", "item", item.pk))
        self.assertTrue(PracticeItem.objects.filter(pk=item.pk).exists())
        new_kind = "text_short" if item.kind != "text_short" else "formula"
        r = self.client.post(
            self.url("teacher:item", self.practice.pk, item.pk),
            {
                "action": "save",
                "label": item.label,
                "kind": new_kind,
                "points": 1,
                "answer_spec": '{"accepted": ["a"], "formula": "H2O"}',
            },
        )
        self.assertEqual(r.status_code, 200)
        item.refresh_from_db()
        self.assertNotEqual(item.kind, new_kind)

    def test_pages_render(self):
        for stage in self.stages:
            self.assertEqual(self.client.get(self.url("teacher:stage", stage.pk)).status_code, 200, stage.kind)
        item = self.practice.practice_task.items.first()
        self.assertEqual(self.client.get(self.url("teacher:item", self.practice.pk, item.pk)).status_code, 200)
        quiz = self.stages[0].checkpoint_quiz
        self.assertEqual(self.client.get(self.url("teacher:quiz", quiz.pk)).status_code, 200)
        question = quiz.questions.first()
        self.assertEqual(self.client.get(self.url("teacher:question", quiz.pk, question.pk)).status_code, 200)
        self.assertEqual(self.client.get(reverse("teacher:courses")).status_code, 200)
        self.assertEqual(Question.objects.filter(quiz=quiz).count(), quiz.questions.count())
