import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments import chem
from apps.labs.engine import all_labs, get_lab
from apps.labs.models import LabAttempt
from apps.labs.services import finish_attempt, record_events, save_journal, start_attempt, submit_analysis
from apps.labs.services.attempts import check_equation
from apps.organizations.testing import make_group, make_student


class SpecTests(TestCase):
    def test_every_experiment_serialises_and_is_consistent(self):
        for lab in all_labs().values():
            for exp in lab.experiments:
                data = json.loads(json.dumps(exp.as_json()))
                item_keys = {i["key"] for i in data["items"]}
                for step in data["steps"]:
                    self.assertTrue(set(step["items"]) <= item_keys, f"{exp.key}.{step['key']} uses unknown item")
                    if step["kind"] == "choice":
                        self.assertTrue(any(o["correct"] for o in step["options"]))
                kinds = [s["kind"] for s in data["steps"]]
                self.assertEqual(kinds[-1], "finish")
                self.assertIn("journal", kinds)
                # every required item belongs to exactly one step
                for item in data["items"]:
                    if item["required"]:
                        owners = [s for s in data["steps"] if item["key"] in s["items"]]
                        self.assertEqual(len(owners), 1, f"{exp.key}: {item['key']}")
                # equation answers of the journal are readable, balanced and never sent to the browser
                for field in exp.journal:
                    if field.kind == "equation":
                        self.assertTrue(chem.parse_equation(field.answer).is_balanced, f"{exp.key}.{field.key}")
                        self.assertEqual(check_equation(field.answer, field.answer), "ok")
                self.assertNotIn("answer", json.dumps(data["journal"]))
                # the generic test-tube bench: ops belong to real steps and real tubes
                if exp.scene == "tubes":
                    steps = {s["key"] for s in data["steps"]}
                    tubes = len(exp.params["tubes"])
                    for key, ops in exp.params["ops"].items():
                        self.assertIn(key, steps, f"{exp.key}: ops for an unknown step {key}")
                        for op in ops:
                            self.assertLess(op.get("tube", 0), tubes, f"{exp.key}.{key}")


@override_settings(ALLOWED_HOSTS=["testserver"])
class AttemptFlowTests(TestCase):
    def setUp(self):
        self.user = make_student("s1", group=make_group(research_cohort="experimental"))
        self.lab = get_lab("t01")
        self.exp = self.lab.experiment("hydrogen")

    def test_reload_reuses_untouched_attempt(self):
        a1 = start_attempt(self.user, "t01", self.exp)
        record_events(a1, [{"seq": 1, "t": 0, "type": "start"}])
        a2 = start_attempt(self.user, "t01", self.exp)
        self.assertEqual(a1.pk, a2.pk)
        record_events(a2, [{"seq": 1, "t": 0, "type": "start"}, {"seq": 2, "t": 50, "type": "command", "step": "x"}])
        a3 = start_attempt(self.user, "t01", self.exp)
        self.assertNotEqual(a2.pk, a3.pk)
        self.assertEqual(a3.research_cohort, "experimental")

    def test_events_idempotent_and_metrics(self):
        a = start_attempt(self.user, "t01", self.exp)
        batch = [
            {"seq": 1, "t": 0, "type": "start"},
            {"seq": 2, "t": 100, "type": "order_error", "step": "add_acid"},
            {"seq": 3, "t": 200, "type": "safety_warning", "step": "add_acid"},
            {"seq": 4, "t": 300, "type": "wrong_item", "step": "add_zn", "payload": {"item": "cu"}},
            {"seq": 5, "t": 900, "type": "step_done", "step": "select_flask"},
            {"seq": 6, "t": 1500, "type": "step_done", "step": "add_zn"},
            {"seq": 7, "t": 1600, "type": "bogus"},
        ]
        self.assertEqual(record_events(a, batch), 6)
        self.assertEqual(record_events(a, batch), 0)  # retry of the same batch
        finish_attempt(a)
        a.refresh_from_db()
        self.assertEqual((a.order_errors, a.safety_warnings, a.wrong_items), (1, 1, 1))
        self.assertEqual(a.step_times, {"select_flask": 900, "add_zn": 600})
        self.assertEqual(a.status, LabAttempt.Status.FINISHED)

    def test_journal_and_analysis_scoring(self):
        a = start_attempt(self.user, "t01", self.exp)
        save_journal(a, self.exp, {"why_water": "insoluble", "volume": "224", "hack": "x"})
        self.assertEqual((a.journal_correct, a.journal_total), (1, 1))
        self.assertNotIn("hack", a.journal)
        submit_analysis(a, self.exp, {"oxidant": "h_ion", "air_collect": "up", "no_h2": "cu", "teach_purity": "..."})
        self.assertEqual((a.analysis_correct, a.analysis_total), (2, 3))

    def test_equation_journal_fields_are_checked(self):
        exp = get_lab("t02").experiment("displacement")
        a = start_attempt(self.user, "t02", exp)
        checks = save_journal(a, exp, {"eq_a": "Cl₂ + 2I⁻ → 2Cl⁻ + I₂", "eq_b": "Cl2 + Br- -> Cl- + Br2", "obs_c": "none"})
        self.assertEqual(checks, {"eq_a": "ok", "eq_b": "coefficients"})
        self.assertEqual((a.journal_correct, a.journal_total), (2, 3))  # eq_a and obs_c right, eq_b wrong
        self.client.force_login(self.user)
        r = self.client.post(
            reverse("labs:api_journal", args=[a.pk]), {"eq_a": "Br2 + 2I- -> 2Br- + I2", "eq_b": "x ->"},
            content_type="application/json",
        )
        self.assertEqual(r.json()["checks"], {"eq_a": "species", "eq_b": "unreadable"})

    def test_options_are_shuffled_per_attempt(self):
        """The right answer is written first in the specs; the runner gets a per-attempt order (stable on reload)."""
        from apps.labs.views import shuffled_experiment

        exp = get_lab("t02").experiment("displacement")
        firsts = set()
        for _i in range(8):
            attempt = start_attempt(self.user, "t02", exp)
            record_events(attempt, [{"seq": 1, "t": 0, "type": "start"}, {"seq": 2, "t": 9, "type": "command"}])
            data = shuffled_experiment(exp, attempt)
            self.assertEqual(data, shuffled_experiment(exp, attempt))  # the same attempt → the same order
            question = next(q for q in data["questions"] if q["key"] == "why_cl2")
            self.assertEqual(sorted(o["key"] for o in question["options"]), ["absent", "liquid", "potential"])
            firsts.add(question["options"][0]["correct"])
        self.assertEqual(firsts, {True, False})  # sometimes first, sometimes not

    def test_api_is_owner_only(self):
        a = start_attempt(self.user, "t01", self.exp)
        other = User.objects.create_user("s2", password="x")
        self.client.force_login(other)
        r = self.client.post(
            reverse("labs:api_events", args=[a.pk]), data=json.dumps({"events": []}), content_type="application/json"
        )
        self.assertEqual(r.status_code, 404)

    def test_run_pages_render(self):
        # outside a course stage the simulator is a teacher's preview
        self.client.force_login(User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER))
        for exp in self.lab.experiments:
            r = self.client.get(reverse("labs:run", args=["t01", exp.key]))
            self.assertEqual(r.status_code, 200, exp.key)
