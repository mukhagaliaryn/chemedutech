import json
from unittest import mock

from django.test import TestCase, override_settings

from apps.organizations.testing import make_student

from . import selectors, services
from .models import Lesson, LessonEvent, LessonTemplate, TemplateStage

E = LessonEvent.Action


def make_template(code="chem_design", number=1, minutes=(5, 7, 11, 8, 10, 4)):
    template = LessonTemplate.objects.create(
        code=code, number=number, name=f"T{number}", topic="Тепе-теңдік", subject="Химия", grade="10-сынып",
        aim="Мақсат", outcomes="<ul><li>Нәтиже</li></ul>", product="Паспорт",
    )  # fmt: skip
    for order, m in enumerate(minutes, start=1):
        TemplateStage.objects.create(
            template=template, order=order, title=f"Кезең {order}", minutes=m,
            blocks=[
                {"label": "Мұғалімнің әрекеті", "field": "teacher_action", "html": f"<p>Мұғалім {order}</p>"},
                {"label": "1-тәжірибе. Қысым", "field": "experiment", "html": "<p>N<sub>2</sub> + 3H<sub>2</sub></p>"},
                {"label": "Кезең нәтижесі", "field": "result", "html": "<p>Карта</p>"},
            ],
        )  # fmt: skip
    return template


class LessonServiceTests(TestCase):
    def setUp(self):
        self.student = make_student("s1")
        self.template = make_template()

    def stage(self, lesson, order=3):
        return lesson.stages.get(order=order)

    def test_template_fields_keep_the_blocks_under_their_labels(self):
        fields = services.template_fields(self.template.stages.get(order=1).blocks)
        self.assertEqual(fields["teacher_action"], "<p><strong>Мұғалімнің әрекеті</strong></p><p>Мұғалім 1</p>")
        self.assertIn("N<sub>2</sub>", fields["experiment"])
        self.assertEqual(fields["assessment"], "")

    def test_create_my_version_copies_the_template_once(self):
        lesson = services.start(self.student, self.template)
        self.assertEqual(
            (lesson.title, lesson.topic, lesson.aim, lesson.status), ("T1", "Тепе-теңдік", "Мақсат", "draft")
        )
        self.assertEqual([s.minutes for s in lesson.stages.all()], [5, 7, 11, 8, 10, 4])
        stage = self.stage(lesson)
        self.assertEqual(stage.fields, stage.original["fields"])
        self.assertFalse(stage.cleared or stage.edited)
        self.assertEqual(services.start(self.student, self.template), lesson)
        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(LessonEvent.objects.filter(action=E.CREATED).count(), 1)

    def test_clearing_keeps_the_original_and_the_template_is_untouched(self):
        lesson = services.start(self.student, self.template)
        stage = services.clear(self.stage(lesson))
        self.assertTrue(stage.cleared)
        self.assertEqual(set(stage.fields.values()), {""})
        self.assertIn("Мұғалім 3", stage.original["fields"]["teacher_action"])
        services.save(stage, title="Менің кезеңім", minutes=12, fields={"teacher_action": "<p>Жаңа</p>"})
        self.assertEqual(self.template.stages.get(order=3).blocks[0]["html"], "<p>Мұғалім 3</p>")
        self.assertEqual(self.template.stages.get(order=3).title, "Кезең 3")

    def test_save_cleans_the_html_and_marks_the_stage_redesigned(self):
        stage = services.clear(self.stage(services.start(self.student, self.template)))
        stage = services.save(
            stage, title="  ", minutes="99",
            fields={
                "experiment": '<p onclick="x()">H<sub>2</sub>O<script>alert(1)</script></p><img src=x>',
                "result": "<p> </p>", "unknown": "<p>x</p>",
            },
        )  # fmt: skip
        stage.refresh_from_db()
        self.assertEqual(stage.fields["experiment"], "<p>H<sub>2</sub>O</p>")
        self.assertEqual(stage.fields["result"], "")  # an empty editor
        self.assertNotIn("unknown", stage.fields)
        self.assertEqual((stage.title, stage.minutes, stage.edited), ("Кезең 3", 45, True))

    def test_an_autosave_with_nothing_new_is_not_logged(self):
        stage = services.clear(self.stage(services.start(self.student, self.template)))
        services.save(stage, title="A", minutes=11, fields={"teacher_action": "<p>x</p>"})
        services.save(stage, title="A", minutes=11, fields={"teacher_action": "<p>x</p>"})
        self.assertEqual(LessonEvent.objects.filter(action=E.SAVED).count(), 1)

    def test_an_ai_suggestion_added_to_the_editor_is_logged(self):
        stage = services.clear(self.stage(services.start(self.student, self.template)))
        services.save(stage, title="A", minutes=11, fields={"experiment": "<p>идея</p>"}, inserted=42)
        event = LessonEvent.objects.get(action=E.AI_INSERTED)
        self.assertEqual((event.stage, event.data), (stage, {"message": 42}))

    def test_a_stage_that_is_not_cleared_cannot_be_saved(self):
        stage = self.stage(services.start(self.student, self.template))
        with self.assertRaises(services.LessonError):
            services.save(stage, title="A", minutes=5, fields={})

    def test_restore_brings_the_template_content_back(self):
        stage = services.clear(self.stage(services.start(self.student, self.template)))
        services.save(stage, title="Жаңа", minutes=9, fields={"teacher_action": "<p>менікі</p>"})
        stage = services.restore(stage)
        self.assertEqual((stage.title, stage.minutes, stage.edited, stage.cleared), ("Кезең 3", 11, False, False))
        self.assertEqual(stage.fields, stage.original["fields"])
        self.assertEqual(
            list(LessonEvent.objects.values_list("action", flat=True)), [E.CREATED, E.CLEARED, E.SAVED, E.RESTORED]
        )

    def test_the_final_version_cannot_be_changed(self):
        lesson = services.start(self.student, self.template)
        Lesson.objects.filter(pk=lesson.pk).update(status=Lesson.Status.FINAL)
        with self.assertRaises(services.LessonError):
            services.clear(self.stage(Lesson.objects.get(pk=lesson.pk)))

    def test_timeline_and_cards(self):
        rows = selectors.timeline(list(self.template.stages.all()))
        self.assertEqual([(r["start"], r["end"]) for r in rows][2], (12, 23))
        make_template("chem_circuit", 2)
        lesson = services.start(self.student, self.template)
        stage = services.clear(self.stage(lesson))
        services.save(stage, title="A", minutes=11, fields={"result": "<p>x</p>"})
        cards = selectors.template_cards(self.student)
        self.assertEqual([(c["template"].code, c["lesson"], c["edited"]) for c in cards],
                         [("chem_design", lesson, 1), ("chem_circuit", None, 0)])  # fmt: skip


SIM = {
    "answer": "Қысым артса, NH₃ көбейеді.",
    "answer_type": "partial",
    "possible_error": "Катализатор шығымды арттырады деп ойлайды.",
    "difficulty": "Тепе-теңдік пен жылдамдықтың айырмасы.",
    "suggestion": "Жылдамдық пен шығымды бөлек сұраңыз.",
}


@override_settings(AI_TUTOR_ENABLED=True)
class AssemblyTests(TestCase):
    def setUp(self):
        from apps.ai.services import client as ai_client
        from apps.ai.tests import FakeClient, answer

        self.fake = FakeClient(answer(json.dumps(SIM)))
        patcher = mock.patch.object(ai_client, "get_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.student = make_student("s1")
        self.lesson = services.start(self.student, make_template())

    def redesign(self, order=3):
        stage = services.clear(self.lesson.stages.get(order=order))
        return services.save(
            stage, title="Дәлел", minutes=stage.minutes, fields={"experiment": "<p>N<sub>2</sub>O<sub>4</sub></p>"}
        )

    def trial(self, level="low"):
        services.assemble(self.lesson)
        return services.start_trial(self.lesson, level)

    def test_problems_block_the_assembly(self):
        self.assertEqual(services.problems(self.lesson), [])
        stage = services.clear(self.lesson.stages.get(order=2))
        services.save(stage, title="Бос", minutes=9, fields={})
        codes = [p["code"] for p in services.problems(self.lesson)]
        self.assertEqual(codes, ["empty_stage", "minutes"])
        with self.assertRaises(services.LessonError):
            services.assemble(self.lesson)

    def test_details_are_saved_once_and_cleaned(self):
        services.save_details(
            self.lesson, title=" Менің сабағым ", topic="pH", aim="Мақсат", outcomes="<p>a<script>x</script></p>"
        )
        services.save_details(self.lesson, title="Менің сабағым", topic="pH", aim="Мақсат", outcomes="<p>a</p>")
        self.lesson.refresh_from_db()
        self.assertEqual((self.lesson.title, self.lesson.outcomes), ("Менің сабағым", "<p>a</p>"))
        self.assertEqual(LessonEvent.objects.filter(action=E.DETAILS_SAVED).count(), 1)

    def test_assemble_freezes_a_version(self):
        self.redesign()
        version = services.assemble(self.lesson)
        self.lesson.refresh_from_db()
        self.assertEqual((version.number, version.reason, self.lesson.status), (1, "assemble", "assembled"))
        stage = version.snapshot["stages"][2]
        self.assertEqual((stage["title"], stage["start"], stage["end"], stage["redesigned"]), ("Дәлел", 12, 23, True))
        self.assertEqual(version.snapshot["subject"], "Химия")
        services.save(self.lesson.stages.get(order=3), title="Кейін", minutes=11, fields={"result": "<p>x</p>"})
        version.refresh_from_db()
        self.assertEqual(version.snapshot["stages"][2]["title"], "Дәлел")  # versions do not change
        self.assertEqual(services.assemble(self.lesson).number, 2)

    def test_a_trial_needs_an_assembled_lesson_and_a_level(self):
        with self.assertRaises(services.LessonError):
            services.start_trial(self.lesson, "low")
        services.assemble(self.lesson)
        with self.assertRaises(services.LessonError):
            services.start_trial(self.lesson, "genius")

    def test_the_ai_student_answers_a_stage_once(self):
        self.redesign()
        trial = self.trial()
        turn = services.run_turn(trial, 3)
        self.assertEqual((turn.answer_type, turn.difficulty, turn.stage_title), ("partial", SIM["difficulty"], "Дәлел"))
        self.assertIn("N<sub>2</sub>O<sub>4</sub>", turn.task)
        self.assertEqual(services.run_turn(trial, 3), turn)
        self.assertEqual(len(self.fake.calls), 1)
        call = self.fake.calls[0]
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")
        self.assertIn("Readiness level: low.", call["system"])
        self.assertIn("<student_text>", call["system"])
        self.assertIn("N₂O₄", call["system"])

    def test_every_stage_done_finishes_the_trial(self):
        trial = self.trial()
        for order in range(1, 7):
            services.run_turn(trial, order)
        trial.refresh_from_db()
        self.lesson.refresh_from_db()
        self.assertIsNotNone(trial.finished_at)
        self.assertEqual(self.lesson.status, "tested")
        self.assertEqual(services.finished_trial(self.lesson), trial)

    def test_a_failed_ai_student_leaves_no_answer_but_a_log(self):
        from apps.ai import services as ai
        from apps.ai.models import AIMessage
        from apps.ai.tests import answer

        self.fake.replies = [answer("not json")]
        trial = self.trial()
        with self.assertRaises(ai.AIUnavailable):
            services.run_turn(trial, 1)
        self.assertFalse(trial.turns.exists())
        self.assertTrue(AIMessage.objects.filter(conversation__mode="student_sim", error__gt="").exists())

    def test_final_version_needs_a_finished_trial_and_closes_the_lesson(self):
        trial = self.trial()
        with self.assertRaises(services.LessonError):
            services.finalize(self.lesson)
        for order in range(1, 7):
            services.run_turn(trial, order)
        self.redesign(2)  # revised after the trial
        self.assertEqual(selectors.changed_since(self.lesson, trial.version.snapshot), {2})
        version = services.finalize(self.lesson)
        self.lesson.refresh_from_db()
        self.assertEqual((version.reason, version.number, self.lesson.status), ("final", 2, "final"))
        self.assertEqual(version.snapshot["stages"][1]["title"], "Дәлел")
        with self.assertRaises(services.LessonError):
            services.save(self.lesson.stages.get(order=2), title="x", minutes=7, fields={})
        with self.assertRaises(services.LessonError):
            services.start_trial(self.lesson, "high")

    def test_plan_rows_put_the_fields_in_the_columns(self):
        self.redesign()
        rows = selectors.plan_rows(services.assemble(self.lesson).snapshot)
        self.assertEqual(rows[2]["cells"]["students"][0]["html"], "<p>N<sub>2</sub>O<sub>4</sub></p>")
        self.assertTrue(rows[2]["cells"]["students"][0]["label"])  # two fields share the column
        self.assertEqual(rows[2]["cells"]["teacher"], [])
        self.assertEqual(rows[0]["cells"]["teacher"][0]["label"], "")
