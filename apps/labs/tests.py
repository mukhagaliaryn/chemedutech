import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.labs.engine import all_labs, get_lab
from apps.labs.models import LabAttempt
from apps.labs.services import finish_attempt, record_events, save_journal, start_attempt, submit_analysis
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
        self.assertEqual(a3.cohort, "experimental")

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

    def test_api_is_owner_only(self):
        a = start_attempt(self.user, "t01", self.exp)
        other = User.objects.create_user("s2", password="x")
        self.client.force_login(other)
        r = self.client.post(
            reverse("labs:api_events", args=[a.pk]), data=json.dumps({"events": []}), content_type="application/json"
        )
        self.assertEqual(r.status_code, 404)

    def test_run_pages_render(self):
        self.client.force_login(self.user)
        for exp in self.lab.experiments:
            r = self.client.get(reverse("labs:run", args=["t01", exp.key]))
            self.assertEqual(r.status_code, 200, exp.key)
