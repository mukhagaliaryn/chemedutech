import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.organizations.testing import make_student

from . import frames, selectors, services
from .models import Lesson, LessonEvent, LessonTemplate, LessonVersion, Review, TemplateStage, Trial, TrialMessage

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


def fill_sheet(lesson):
    """Every field of the eight stages and part I filled (the minutes as numbers)."""
    services.save_sheet_details(lesson, {"title": "Практика", "topic": "Тепе-теңдік", "grade": "9", "aim": "Мақсат"})
    for stage in lesson.stages.all():
        values = {k: ("5" if k == "time" else f"<p>{stage.key} {k}</p>") for k in stage.fields}
        services.save(stage, title="", minutes=None, fields=values)


@override_settings(AI_TUTOR_ENABLED=True)
class PracticeTests(TestCase):
    def setUp(self):
        from apps.ai.services import client as ai_client
        from apps.ai.tests import FakeClient, answer

        self.fake = FakeClient(answer(json.dumps(SIM)))
        patcher = mock.patch.object(ai_client, "get_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.student = make_student("s1")
        self.template = make_template()
        self.source = services.start(self.student, self.template)
        self.lesson = services.start_practice(self.student, self.template)

    def trial(self, level="medium"):
        fill_sheet(self.lesson)
        return services.start_stepwise(self.lesson, grade="9", level=level)

    def run_stage(self, trial, order):
        turn = services.give_task(trial, order, explanation="<p>Түсіндірме</p>", task="<p>Тапсырма</p>", minutes=4)
        return services.analyse(turn, analysis="Қате: реакция тоқтамайды", correction="Сұрақ қостым", duration_s=95)

    def test_the_sheet_has_the_eight_stages_of_the_guide(self):
        stages = list(self.lesson.stages.all())
        self.assertEqual([s.key for s in stages], [s.key for s in frames.RESEARCH_8])
        self.assertEqual([s.minutes for s in stages], [4, 6, 9, 8, 7, 5, 4, 2])
        self.assertEqual(set(stages[2].fields), {"research_question", "hypothesis", "experiment", "parameters",
                                                 "indicators", "time", "recording"})  # fmt: skip
        self.assertEqual(self.lesson.source_lesson, self.source)
        self.assertEqual(self.lesson.stages.get(order=1).fields["teacher_explanation"], "")  # not copied (О-7)
        self.assertEqual(services.start_practice(self.student, self.template), self.lesson)

    def test_a_sheet_stage_is_saved_without_clearing_and_keeps_its_frame(self):
        stage = self.lesson.stages.get(order=3)
        stage = services.save(
            stage, title="Басқа", minutes=20, fields={"time": "9 мин", "hypothesis": "<p>NO<sub>2</sub></p>"}
        )
        self.assertEqual(stage.minutes, 9)  # the frame's minutes; the title stays the frame's too
        self.assertNotEqual(stage.title, "Басқа")
        self.assertEqual(stage.fields["time"], "9")
        self.assertEqual(stage.fields["hypothesis"], "<p>NO<sub>2</sub></p>")
        self.assertTrue(stage.edited)

    def test_the_trial_needs_a_filled_sheet_a_class_and_a_level(self):
        with self.assertRaises(services.LessonError):
            services.start_stepwise(self.lesson, grade="9", level="medium")
        fill_sheet(self.lesson)
        for grade_, level in (("6", "medium"), ("9", "genius")):
            with self.assertRaises(services.LessonError):
                services.start_stepwise(self.lesson, grade=grade_, level=level)
        trial = services.start_stepwise(self.lesson, grade="10", level="high")
        self.assertEqual((trial.mode, trial.grade, trial.version.reason), ("stepwise", "10", "trial"))

    def test_the_answer_types_are_mixed_by_level(self):
        for level, counts in (("high", (5, 2, 1)), ("medium", (3, 3, 2)), ("low", (2, 3, 3))):
            trial = Trial(pk=7, level=level, version=LessonVersion(snapshot={"stages": [{}] * 8}))
            types = services.planned_types(trial)
            self.assertEqual(tuple(types.count(t) for t in ("correct", "partial", "wrong")), counts)
            self.assertEqual(types, services.planned_types(trial))  # the same every time

    def test_stages_open_one_by_one_with_the_planned_type(self):
        trial = self.trial()
        self.assertEqual(services.current_order(trial), 1)
        with self.assertRaises(services.LessonError):
            services.give_task(trial, 2, explanation="x", task="y", minutes=3)
        turn = services.give_task(trial, 1, explanation="<p>Т</p>", task="<p>Тапсырма H<sub>2</sub></p>", minutes=50)
        self.assertEqual((turn.time_minutes, turn.task), (45, "<p>Тапсырма H<sub>2</sub></p>"))
        system = self.fake.calls[0]["system"]
        self.assertIn(f"Required answer type: {services.planned_types(trial)[0]}.", system)
        self.assertIn("grade 9", system)
        self.assertEqual(services.current_order(trial), 1)  # not analysed yet
        with self.assertRaises(services.LessonError):
            services.analyse(turn, analysis="  ")
        services.analyse(turn, analysis="Түсіндірдім", duration_s=70)
        self.assertEqual(services.current_order(trial), 2)

    def test_finish_gathers_the_results_and_closes_the_practice(self):
        trial = self.trial("low")
        for order in range(1, 8):
            self.run_stage(trial, order)
        with self.assertRaises(services.LessonError):
            services.finish(trial)
        self.run_stage(trial, 8)
        version = services.finish(trial)
        self.lesson.refresh_from_db()
        self.assertEqual((self.lesson.status, version.reason), ("final", "final"))
        turns = version.snapshot["trial"]["turns"]
        self.assertEqual(len(turns), 8)
        self.assertEqual((turns[0]["student_analysis"], turns[0]["duration_s"]), ("Қате: реакция тоқтамайды", 95))
        with self.assertRaises(services.LessonError):
            services.save(self.lesson.stages.get(order=1), title="", minutes=None, fields={})

    def test_the_teachers_grade(self):
        teacher = make_student("t1")
        with self.assertRaises(services.LessonError):
            services.grade(self.lesson, teacher, dict.fromkeys("12345", 2))  # not finished
        trial = self.trial()
        for order in range(1, 9):
            self.run_stage(trial, order)
        services.finish(trial)
        self.lesson.refresh_from_db()
        for bad in ({"1": 3, "2": 1, "3": 1, "4": 1, "5": 1}, {"1": 1}):
            with self.assertRaises(services.LessonError):
                services.grade(self.lesson, teacher, bad)
        review = services.grade(self.lesson, teacher, {"1": 2, "2": 1, "3": 2, "4": 0, "5": 2}, "Жақсы")
        self.assertEqual((review.total, review.comment), (7, "Жақсы"))
        review = services.grade(self.lesson, teacher, dict.fromkeys("12345", "2"))
        self.assertEqual((review.total, Review.objects.count()), (10, 1))


CHECK_OK = {"stages": dict.fromkeys("1234", "ok"), "criteria": dict.fromkeys(
    ("aim", "explanation", "chemistry", "task_aim", "assessment", "time", "complete"), "ok")}  # fmt: skip
REPLY = {"reply": "Себебі мырыш электрондарын береді.", "answer_type": "partial"}


def fill_micro(lesson):
    services.save_micro_details(lesson, {"topic": "Гальваникалық элемент", "grade": "11", "aim": "Мақсат",
                                         "programme": "6B01504 Химия", "study_year": "3"})  # fmt: skip
    for stage in lesson.stages.all():
        services.save(stage, title="", minutes=None, fields={k: f"<p>{stage.key} {k}</p>" for k in stage.fields})


@override_settings(AI_TUTOR_ENABLED=True)
class MicroTests(TestCase):
    def setUp(self):
        from apps.ai.services import client as ai_client
        from apps.ai.tests import FakeClient, answer

        self.answer = answer
        self.fake = FakeClient(answer(json.dumps(CHECK_OK)))
        patcher = mock.patch.object(ai_client, "get_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.student = make_student("s1")
        self.practice = services.start_practice(self.student, make_template())
        self.lesson = services.start_micro(self.student, self.practice, 3)

    def checked(self):
        fill_micro(self.lesson)
        self.lesson.refresh_from_db()
        return services.check_micro(self.lesson)

    def dialog(self):
        self.checked()
        self.fake.replies = [self.answer(json.dumps(REPLY))]
        return services.start_dialog(self.lesson, grade="11", level="medium")

    def test_one_microlesson_from_a_part_of_a_practice(self):
        self.assertEqual([s.key for s in self.lesson.stages.all()], ["interest", "explain", "apply", "check"])
        self.assertEqual([s.minutes for s in self.lesson.stages.all()], [2, 3, 3, 2])
        self.assertEqual((self.lesson.duration_min, self.lesson.details["source_stage"]), (10, 3))
        self.assertEqual(self.lesson.stages.get(order=1).fields["intro"], "")  # the part is not copied
        other = services.start_practice(self.student, make_template("chem_circuit", 2))
        self.assertEqual(services.start_micro(self.student, other, 1), self.lesson)  # no second microlesson
        self.assertEqual(Lesson.objects.filter(kind="microlesson").count(), 1)
        with self.assertRaises(services.LessonError):
            services.start_micro(make_student("s2"), self.practice, 1)  # not their practice

    def test_the_checker_marks_only_correct_or_wrong(self):
        check = self.checked()
        self.assertTrue(check.passed)
        call = self.fake.calls[-1]
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")
        self.assertIn("never explain", call["system"])
        self.assertIn("<student_text>", call["system"])
        self.assertTrue(services.check_state(self.lesson)["passed"])
        stage = self.lesson.stages.get(order=2)
        services.save(
            stage, title="", minutes=None, fields={**stage.fields, "equation": "<p>Zn → Zn<sup>2+</sup> + 2e</p>"}
        )
        self.assertEqual(services.check_state(self.lesson), {"check": check, "current": False, "passed": False})

    def test_a_wrong_stage_blocks_the_trial(self):
        fill_micro(self.lesson)
        self.fake.replies = [self.answer(json.dumps({**CHECK_OK, "stages": {**CHECK_OK["stages"], "2": "wrong"}}))]
        check = services.check_micro(self.lesson)
        self.assertFalse(check.passed)
        with self.assertRaises(services.LessonError):
            services.start_dialog(self.lesson, grade="11", level="medium")

    def test_a_wrong_criterion_blocks_the_trial_too(self):
        fill_micro(self.lesson)
        wrong = {**CHECK_OK, "criteria": {**CHECK_OK["criteria"], "complete": "wrong"}}
        self.fake.replies = [self.answer(json.dumps(wrong))]
        self.assertFalse(services.check_micro(self.lesson).passed)
        with self.assertRaises(services.LessonError):
            services.start_dialog(self.lesson, grade="11", level="medium")

    def test_the_dialogue_and_its_timer(self):
        trial = self.dialog()
        m = services.send(trial, kind="question", text="Неліктен электрондар мырыштан мысқа қозғалады?")
        self.assertEqual((m.number, m.stage_order, m.answer_type, m.reply), (1, 1, "partial", REPLY["reply"]))
        self.assertIn("Readiness level: medium.", self.fake.calls[-1]["system"])
        self.assertIn("мырыштан мысқа", self.fake.calls[-1]["system"])
        with self.assertRaises(services.LessonError):
            services.send(trial, kind="lecture", text="x")
        Trial.objects.filter(pk=trial.pk).update(started_at=timezone.now() - timedelta(minutes=6))
        trial.refresh_from_db()
        self.assertEqual(services.send(trial, kind="action", text="Түсіндіремін").stage_order, 3)
        Trial.objects.filter(pk=trial.pk).update(started_at=timezone.now() - timedelta(minutes=11))
        trial.refresh_from_db()
        with self.assertRaises(services.LessonError):
            services.send(trial, kind="explanation", text="тағы")
        trial.refresh_from_db()
        self.assertIsNotNone(trial.finished_at)  # the time is up: the trial is finished
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, "tested")

    def test_the_ai_students_thinking_is_not_counted(self):
        trial = self.dialog()
        Trial.objects.filter(pk=trial.pk).update(started_at=timezone.now() - timedelta(seconds=100))
        trial.refresh_from_db()
        services.send(trial, kind="explanation", text="Бүгін гальваникалық элемент")
        TrialMessage.objects.filter(trial=trial).update(wait_ms=40000)
        self.assertLessEqual(services.elapsed_s(trial), 61)
        self.assertEqual(
            [services.stage_at(s) for s in (0, 119, 120, 299, 300, 479, 480, 900)], [1, 1, 2, 2, 3, 3, 4, 4]
        )

    def test_trials_are_kept_apart_and_graded_apart(self):
        first = self.dialog()
        services.send(first, kind="question", text="?")
        services.finish_dialog(first)
        teacher = make_student("t1")
        with self.assertRaises(services.LessonError):
            services.grade(self.lesson, teacher, dict.fromkeys("12345", 2))  # a trial is needed
        services.grade(self.lesson, teacher, dict.fromkeys("12345", 1), trial=first)
        stage = self.lesson.stages.get(order=1)
        services.save(stage, title="", minutes=None, fields={**stage.fields, "intro": "<p>Жаңа кіріспе</p>"})
        with self.assertRaises(services.LessonError):
            services.start_dialog(self.lesson, grade="11", level="high")  # changed: check again
        self.fake.replies = [self.answer(json.dumps(CHECK_OK))]
        services.check_micro(self.lesson)
        second = services.start_dialog(self.lesson, grade="11", level="high")
        services.finish_dialog(second)
        services.grade(self.lesson, teacher, dict.fromkeys("12345", 2), trial=second)
        self.assertEqual(services.trial_number(second), 2)
        self.assertEqual(sorted(Review.objects.values_list("total", flat=True)), [5, 10])
        self.assertNotEqual(
            first.version.snapshot["stages"][0]["fields"], second.version.snapshot["stages"][0]["fields"]
        )

    def test_assemble_needs_a_finished_trial_and_closes_it(self):
        with self.assertRaises(services.LessonError):
            services.assemble_micro(self.lesson)
        trial = self.dialog()
        services.send(trial, kind="question", text="?")
        services.finish_dialog(trial)
        version = services.assemble_micro(self.lesson)
        self.lesson.refresh_from_db()
        self.assertEqual((self.lesson.status, version.reason), ("final", "final"))
        self.assertEqual(version.snapshot["trials"][0]["messages"][0]["reply"], REPLY["reply"])
        with self.assertRaises(services.LessonError):
            services.check_micro(self.lesson)


def expert_answer(keys, status="needs_more", change=""):
    return {
        "items": {k: {"status": "ok", "text": f"{k}: дәл."} for k in keys}, "status": status, "focus": "Ғылыми дәлдік",
        "summary": "Жоба құрылымы логикалы.", "strengths": ["Мақсат нақты"], "suggestions": ["Дескрипторды нақтыла"],
        "change": change,
    }  # fmt: skip


DRAFT = expert_answer(("accuracy", "fit", "sequence", "cognition", "assessment", "authorship"))
AFTER = expert_answer(("content", "aim", "time", "tasks", "feedback", "method", "reflection"), status="ok")


def fill_independent(lesson, stages=((10, "Қызығушылық"), (20, "Зерттеу"), (15, "Рефлексия"))):
    ind = services.independent
    ind.save_details(lesson, {"topic": "Электролиз", "grade": "11", "aim": "Электролиз заңдылықтарын түсіндіру",
                              "idea": "Зерттеушілік оқыту", "outcomes": "<p>Теңдеу құрады</p>"})  # fmt: skip
    for minutes, title in stages:
        stage = ind.add_stage(lesson, title=title, minutes=minutes)
        services.save(
            stage, title=title, minutes=minutes, fields={"teacher": f"<p>{title}</p>", "task": "<p>Тапсырма</p>"}
        )
    lesson.refresh_from_db()
    return lesson


@override_settings(AI_TUTOR_ENABLED=True)
class IndependentTests(TestCase):
    """Section 8: the student's own stages (45 minutes at most), «Айгерім», submit, the stepwise or real trial, the
    analysis after the trial and the teacher's confirmation."""

    def setUp(self):
        from apps.ai.services import client as ai_client
        from apps.ai.tests import FakeClient, answer

        self.answer = answer
        self.fake = FakeClient(answer(json.dumps(DRAFT)))
        patcher = mock.patch.object(ai_client, "get_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ind = services.independent
        self.student = make_student("s1")
        self.teacher = make_student("t1")
        self.lesson = self.ind.start_independent(self.student)

    def submitted(self):
        fill_independent(self.lesson)
        self.ind.submit(self.lesson)
        self.lesson.refresh_from_db()
        return self.lesson

    def tried(self):
        self.submitted()
        self.fake.replies = [self.answer(json.dumps(SIM))]
        trial = self.ind.start_trial(self.lesson, grade="11", level="medium")
        for order in (1, 2, 3):
            turn = services.give_task(trial, order, explanation="<p>Т</p>", task="<p>Тапсырма</p>", minutes=5)
            services.analyse(turn, analysis="Талдадым")
        return self.ind.finish_trial(trial)

    def test_one_open_lesson_and_the_next_cycle(self):
        self.assertEqual((self.lesson.kind, self.lesson.frame, self.lesson.cycle), ("independent", "free", 1))
        self.assertEqual(self.ind.start_independent(self.student), self.lesson)
        Lesson.objects.filter(pk=self.lesson.pk).update(status=Lesson.Status.FINAL)
        self.assertEqual(self.ind.start_independent(self.student).cycle, 2)

    def test_stages_of_the_students_choosing_take_45_minutes_at_most(self):
        fill_independent(self.lesson)
        self.assertEqual(self.ind.total_minutes(self.lesson), 45)
        with self.assertRaises(services.LessonError):
            self.ind.add_stage(self.lesson, title="Тағы", minutes=1)
        for bad in (("", 5), ("Атау", "x"), ("Атау", 0)):
            with self.assertRaises(services.LessonError):
                self.ind.add_stage(self.lesson, title=bad[0], minutes=bad[1])
        stage = self.lesson.stages.get(order=1)
        with self.assertRaises(services.LessonError):
            services.save(stage, title="Қызығушылық", minutes=11, fields={})
        stage = services.save(stage, title="Ой шақыру", minutes=5, fields={"teacher": "<p>Сұрақ</p>"})
        self.assertEqual((stage.title, stage.minutes), ("Ой шақыру", 5))
        self.ind.delete_stage(self.lesson.stages.get(order=2))
        self.assertEqual([(s.order, s.title) for s in self.lesson.stages.all()], [(1, "Ой шақыру"), (2, "Рефлексия")])

    def test_submit_checks_the_structure(self):
        self.assertEqual({p["code"] for p in self.ind.problems(self.lesson)}, {"details", "no_stages"})
        with self.assertRaises(services.LessonError):
            self.ind.submit(self.lesson)
        fill_independent(self.lesson)
        version = self.ind.submit(self.lesson)
        self.lesson.refresh_from_db()
        self.assertEqual((self.lesson.status, version.snapshot["stages"][1]["title"]), ("submitted", "Зерттеу"))

    def test_aigerim_reviews_the_project_and_compares_with_the_previous_opinion(self):
        fill_independent(self.lesson)
        first = self.ind.expert_review(self.lesson)
        self.assertEqual((first.kind, first.status, first.items["accuracy"]["status"]), ("draft", "needs_more", "ok"))
        call = self.fake.calls[-1]
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")
        self.assertIn("«Айгерім»", call["system"])
        self.assertIn("Stage 2 «Зерттеу» (10–30 min)", call["system"])
        self.assertNotIn("previous opinion (on", call["system"])
        self.fake.replies = [self.answer(json.dumps({**DRAFT, "change": "Дескриптор нақтыланды"}))]
        second = self.ind.expert_review(self.lesson)
        self.assertEqual((second.previous, second.change), (first, "Дескриптор нақтыланды"))
        self.assertIn("The previous opinion (on the earlier version)", self.fake.calls[-1]["system"])
        self.assertEqual(self.lesson.review, None)  # the section 4–6 review is a different thing

    def test_the_stepwise_trial_with_the_free_frame(self):
        with self.assertRaises(services.LessonError):
            self.ind.start_trial(self.lesson, grade="11", level="medium")  # not submitted
        self.submitted()
        self.fake.replies = [self.answer(json.dumps(SIM))]
        trial = self.ind.start_trial(self.lesson, grade="11", level="medium")
        self.assertEqual((trial.mode, len(trial.version.snapshot["stages"])), ("stepwise", 3))
        with self.assertRaises(services.LessonError):
            self.ind.start_trial(self.lesson, grade="11", level="high")  # one at a time
        self.assertEqual(services.prefill(trial.version.snapshot["stages"][0])["explanation"], "<p>Қызығушылық</p>")
        with self.assertRaises(services.LessonError):
            self.ind.finish_trial(trial)
        for order in (1, 2, 3):
            turn = services.give_task(trial, order, explanation="<p>Т</p>", task="<p>Тапсырма</p>", minutes=5)
            services.analyse(turn, analysis="Талдадым")
        self.ind.finish_trial(trial)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, "tested")

    def test_the_analysis_after_a_trial_and_the_teachers_confirmation(self):
        trial = self.tried()
        self.fake.replies = [self.answer(json.dumps(AFTER))]
        review = self.ind.trial_review(trial)
        self.assertEqual((review.kind, review.trial, set(review.items)), ("trial", trial, set(AFTER["items"])))
        self.assertIn("A trial with the AI student (medium level, grade 11)", self.fake.calls[-1]["system"])
        with self.assertRaises(services.LessonError):
            self.ind.confirm(review, self.teacher, status="ok", score=11)
        with self.assertRaises(services.LessonError):
            self.ind.confirm(review, self.teacher, status="great", score=8)
        self.ind.confirm(review, self.teacher, status="needs_more", comment="Уақытты қайта бөл", score="6")
        self.lesson.refresh_from_db()
        self.assertEqual((self.lesson.status, Review.objects.get(trial=trial).total), ("tested", 6))
        self.ind.confirm(review, self.teacher, status="ok", score=9)
        self.lesson.refresh_from_db()
        self.assertEqual((self.lesson.status, Review.objects.get(trial=trial).total), ("final", 9))
        with self.assertRaises(services.LessonError):
            self.ind.expert_review(self.lesson)  # the final version is not changed

    def test_a_real_audience_trial_entered_by_the_teacher(self):
        fill_independent(self.lesson)
        with self.assertRaises(services.LessonError):
            self.ind.record_real_trial(self.lesson, self.teacher, grade="10", notes="  ")
        trial = self.ind.record_real_trial(self.lesson, self.teacher, grade="10", notes="Оқушылар белсенді болды.")
        self.assertEqual((trial.mode, trial.recorded_by, trial.level), ("real", self.teacher, ""))
        self.assertIsNotNone(trial.finished_at)
        self.fake.replies = [self.answer(json.dumps({**AFTER, "change": "Алдыңғымен салыстырғанда"}))]
        self.ind.trial_review(trial)
        self.assertIn("The teacher's protocol:\nОқушылар белсенді болды.", self.fake.calls[-1]["system"])
