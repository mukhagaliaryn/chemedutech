"""STEP-08: the virtual lab inside the learning flow."""

import json
from decimal import Decimal
from types import SimpleNamespace

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import Course, Stage
from apps.courses.services import enroll
from apps.labs.engine import LabScoring, get_lab
from apps.labs.models import LabAttempt
from apps.labs.scoring import attempt_score
from apps.organizations.testing import make_group, make_student
from apps.progress import services as progress
from apps.progress.models import StageProgress

S = StageProgress.Status


def metrics(**kw):
    base = {
        "order_errors": 0, "safety_warnings": 0, "wrong_items": 0, "wrong_choices": 0,
        "journal_correct": 0, "journal_total": 0, "analysis_correct": 0, "analysis_total": 0,
    }  # fmt: skip
    return SimpleNamespace(**{**base, **kw})


class LabScoringTests(SimpleTestCase):
    def test_formula(self):
        # process 100 − 10 − 15 − 5·2 = 65; journal 50; analysis 75 → 0.3·65 + 0.2·50 + 0.5·75 = 67
        attempt = metrics(
            order_errors=1, safety_warnings=1, wrong_items=1, wrong_choices=1,
            journal_correct=1, journal_total=2, analysis_correct=3, analysis_total=4,
        )  # fmt: skip
        self.assertEqual(attempt_score(attempt, LabScoring()), Decimal("67.00"))

    def test_process_never_goes_below_zero(self):
        self.assertEqual(
            attempt_score(metrics(order_errors=20, analysis_correct=1, analysis_total=1), LabScoring()),
            Decimal("62.50"),
        )

    def test_missing_parts_are_rescaled(self):
        # no journal choice fields: (0.3·100 + 0.5·50) / 0.8
        attempt = metrics(analysis_correct=1, analysis_total=2)
        self.assertEqual(attempt_score(attempt, LabScoring()), Decimal("68.75"))
        self.assertEqual(attempt_score(metrics(), LabScoring()), Decimal("100.00"))

    def test_lab_can_override_the_formula(self):
        strict = LabScoring(order_error_penalty=50, weight_process=1, weight_journal=0, weight_analysis=0)
        self.assertEqual(attempt_score(metrics(order_errors=1, analysis_total=1), strict), Decimal("50.00"))


@override_settings(ALLOWED_HOSTS=["testserver"])
class LabStageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")
        cls.lab_stage = Stage.objects.get(topic__number=1, kind="lab")
        cls.practice = Stage.objects.filter(topic__number=1, kind="practice").order_by("order").first()
        cls.lab = get_lab("t01")

    def setUp(self):
        self.student = make_student("s1", group=make_group(research_cohort="experimental"))
        self.teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.enrollment = enroll(self.student, self.course, "admin")
        progress.unlock_stage(self.enrollment, self.lab_stage, self.teacher)
        self.client.force_login(self.student)

    def url(self, name, *extra):
        return reverse(name, args=["chemistry", 1, self.lab_stage.pk, *extra])

    def run_experiment(self, experiment, correct=True):
        """Open the page, send a few events, finish and send the analysis — as engine.js does."""
        r = self.client.get(self.url("student:lab_run", experiment.key))
        self.assertEqual(r.status_code, 200)
        config = r.context["config"]
        attempt = LabAttempt.objects.get(pk=config["attempt"])
        events = [{"seq": 1, "t": 0, "type": "start"}, {"seq": 2, "t": 500, "type": "step_done", "step": "x"}]
        self.client.post(config["urls"]["events"], json.dumps({"events": events}), "application/json")
        self.client.post(config["urls"]["finish"], json.dumps({}), "application/json")
        answers = {
            q.key: next((o.key for o in q.options if o.correct == correct), q.options[0].key if q.options else "")
            if q.options else "Түсініктеме"
            for q in experiment.questions
        }  # fmt: skip
        r = self.client.post(config["urls"]["analysis"], json.dumps(answers), "application/json")
        self.assertEqual(r.status_code, 200)
        attempt.refresh_from_db()
        return attempt, r.json()

    def test_attempt_is_tied_to_the_enrolment_and_stage(self):
        self.enrollment.research_cohort = "control"  # the enrolment snapshot wins over the group's current value
        self.enrollment.save()
        r = self.client.get(self.url("student:lab_run", "hydrogen"))
        attempt = LabAttempt.objects.get(pk=r.context["config"]["attempt"])
        self.assertEqual(
            (attempt.enrollment, attempt.stage, attempt.research_cohort), (self.enrollment, self.lab_stage, "control")
        )
        self.assertTrue(r.context["config"]["urls"]["analysis"].startswith(self.url("student:lab_run", "hydrogen")))
        self.assertEqual(r.context["config"]["urls"]["topic"], self.url("student:stage"))

    def test_experiments_open_one_after_another(self):
        rows = progress.lab_experiments(self.enrollment, self.lab_stage)
        self.assertEqual([r["open"] for r in rows], [True, False, False, False])
        r = self.client.get(self.url("student:lab_run", "oxygen"))
        self.assertRedirects(r, self.url("student:stage"))
        self.assertFalse(LabAttempt.objects.exists())
        self.run_experiment(self.lab.experiment("hydrogen"))
        rows = progress.lab_experiments(self.enrollment, self.lab_stage)
        self.assertEqual([r["open"] for r in rows], [True, True, False, False])
        self.assertEqual(self.client.get(self.url("student:lab_run", "oxygen")).status_code, 200)

    def test_finishing_every_experiment_passes_the_stage(self):
        for stage in Stage.objects.filter(topic=self.lab_stage.topic, order__lt=self.lab_stage.order):
            progress.complete_stage(self.enrollment, stage, 100, passed=True)
        scores = []
        for experiment in self.lab.experiments:
            attempt, payload = self.run_experiment(experiment)
            self.assertEqual(attempt.status, "analysed")
            self.assertIsNotNone(attempt.score_percent)
            self.assertEqual(payload["score"], float(attempt.score_percent))
            scores.append(attempt.score_percent)
            if experiment is not self.lab.experiments[-1]:
                self.assertNotEqual(
                    StageProgress.objects.get(enrollment=self.enrollment, stage=self.lab_stage).status, S.PASSED
                )
        sp = StageProgress.objects.get(enrollment=self.enrollment, stage=self.lab_stage)
        self.assertEqual(sp.status, S.PASSED)
        self.assertEqual(sp.score_percent, (sum(scores) / len(scores)).quantize(Decimal("0.01")))
        self.assertEqual(StageProgress.objects.get(enrollment=self.enrollment, stage=self.practice).status, S.AVAILABLE)

    def test_best_attempt_counts(self):
        experiments = list(self.lab.experiments)
        worse, _ = self.run_experiment(experiments[0], correct=False)
        better, _ = self.run_experiment(experiments[0], correct=True)
        for experiment in experiments[1:]:
            self.run_experiment(experiment)
        rows = progress.lab_experiments(self.enrollment, self.lab_stage)
        self.assertEqual(rows[0]["attempt"], better if better.score_percent >= worse.score_percent else worse)

    def test_locked_lab_stage(self):
        other = make_student("s2")
        enroll(other, self.course, "admin")
        self.client.force_login(other)
        r = self.client.get(self.url("student:lab_run", "hydrogen"))
        self.assertTemplateUsed(r, "student/locked.html")

    def test_old_lab_url_sends_the_student_to_the_stage(self):
        r = self.client.get(reverse("labs:run", args=["t01", "oxygen"]))
        self.assertRedirects(r, self.url("student:lab_run", "oxygen"), fetch_redirect_response=False)

    def test_teacher_preview_outside_a_stage(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("labs:run", args=["t01", "rate"]))
        self.assertEqual(r.status_code, 200)
        attempt = LabAttempt.objects.get(pk=r.context["config"]["attempt"])
        self.assertIsNone(attempt.enrollment)

    def test_stage_page_lists_experiment_states(self):
        self.run_experiment(self.lab.experiment("hydrogen"))
        r = self.client.get(self.url("student:stage"))
        rows = r.context["experiments"]
        self.assertEqual(
            [(row["done"], row["open"]) for row in rows], [(True, True), (False, True), (False, False), (False, False)]
        )
        self.assertContains(r, self.url("student:lab_run", "oxygen"))

    def test_research_export_has_the_new_columns(self):
        self.run_experiment(self.lab.experiment("hydrogen"))
        self.client.force_login(User.objects.create_superuser("root", "root@example.kz", "x"))
        r = self.client.get(reverse("research:export_attempts"))
        lines = b"".join(r.streaming_content).decode("utf-8-sig").splitlines()
        header = lines[0].split(",")
        self.assertEqual(header[4], "cohort")  # unchanged position for existing scripts
        self.assertEqual(header[-4:], ["enrollment_id", "course", "stage_id", "score_percent"])
        row = lines[1].split(",")
        self.assertEqual(row[4], "experimental")
        self.assertEqual(row[-3:-1], ["chemistry", str(self.lab_stage.pk)])
