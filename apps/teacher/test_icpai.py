"""STEP-39: the ICPAI programme in the teacher cabinet — the home block, the student's «ICPAI» tab, the read-only
lesson / trial / AI dialogue pages, the statistics (sections, grades, AI) and the CSV exports, with their scope."""

import csv
import io
import json
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import CourseTeacher
from apps.programme import services
from apps.programme.tests import Base


@override_settings(AI_TUTOR_ENABLED=True)
class IcpaiCabinetTests(Base):
    def setUp(self):
        super().setUp()
        from apps.ai.services import client as ai_client
        from apps.ai.tests import FakeClient, answer
        from apps.pedagogy import services as pedagogy
        from apps.pedagogy.tests import SIM, fill_sheet, make_template

        self.fake = FakeClient(answer(json.dumps(SIM)))
        patcher = mock.patch.object(ai_client, "get_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.teacher = User.objects.create_user("ta", "ta@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, teacher=self.teacher)
        self.group.curator = self.teacher
        self.group.save()
        self.enrollment()
        self.lesson = pedagogy.start_practice(self.student, make_template())
        fill_sheet(self.lesson)
        self.trial = pedagogy.start_stepwise(self.lesson, grade="9", level="medium")
        turn = pedagogy.give_task(self.trial, 1, explanation="<p>Түсіндірме</p>", task="<p>Тапсырма</p>", minutes=4)
        pedagogy.analyse(turn, analysis="Оқушы қысымды шатастырды", duration_s=60)
        self.conversation = self.student.ai_conversations.get()
        self.client.force_login(self.teacher)

    def csv(self, name):
        r = self.client.get(reverse(f"research:export_{name}"))
        self.assertEqual(r.status_code, 200)
        return list(csv.DictReader(io.StringIO(b"".join(r.streaming_content).decode("utf-8-sig"))))

    def test_the_home_block(self):
        r = self.client.get(reverse("teacher:dashboard"))
        self.assertTemplateUsed(r, "teacher/icpai/partials/dashboard.html")
        block = r.context["icpai"]
        self.assertEqual([g["group"] for g in block["group_rows"]], [self.group])
        self.assertEqual(len(block["group_rows"][0]["cells"]), 8)
        self.assertEqual({q["what"] for q in block["queues"]}, {"practice", "micro", "portfolio", "independent"})
        other = User.objects.create_user("tb", "tb@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(other)
        self.assertIsNone(self.client.get(reverse("teacher:dashboard")).context["icpai"])  # no programme course

    def test_the_students_icpai_tab(self):
        page = reverse("teacher:student", args=[self.student.pk])
        r = self.client.get(page + "?tab=icpai")
        self.assertTemplateUsed(r, "teacher/icpai/partials/student_tab.html")
        self.assertEqual(len(r.context["section_rows"]), 8)
        self.assertEqual(r.context["conversations_total"], 1)  # one dialogue, however many messages
        self.assertContains(r, reverse("teacher:student_lesson", args=[self.student.pk, self.lesson.pk]))
        self.assertContains(r, reverse("teacher:student_trial", args=[self.student.pk, self.trial.pk]))
        self.assertContains(r, reverse("teacher:student_ai", args=[self.student.pk, self.conversation.pk]))
        self.assertTemplateNotUsed(self.client.get(page), "teacher/icpai/partials/student_tab.html")

    def test_read_only_lesson_trial_and_dialogue(self):
        r = self.client.get(reverse("teacher:student_lesson", args=[self.student.pk, self.lesson.pk]))
        self.assertContains(r, "Тепе-теңдік")
        self.assertEqual(len(r.context["stages"]), 8)
        r = self.client.get(reverse("teacher:student_trial", args=[self.student.pk, self.trial.pk]))
        self.assertContains(r, "Оқушы қысымды шатастырды")
        r = self.client.get(reverse("teacher:student_ai", args=[self.student.pk, self.conversation.pk]))
        self.assertContains(r, self.conversation.get_mode_display())
        self.assertEqual(len(r.context["messages_"]), self.conversation.messages.count())

    def test_another_teacher_or_student_gets_404(self):
        urls = [
            reverse("teacher:student_lesson", args=[self.student.pk, self.lesson.pk]),
            reverse("teacher:student_trial", args=[self.student.pk, self.trial.pk]),
            reverse("teacher:student_ai", args=[self.student.pk, self.conversation.pk]),
        ]
        other = User.objects.create_user("tb", "tb@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(other)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        from apps.organizations.testing import make_student

        stranger = make_student("s9", group=self.group)  # in the teacher's group, but not the lesson's owner
        self.client.force_login(self.teacher)
        self.assertEqual(
            self.client.get(reverse("teacher:student_lesson", args=[stranger.pk, self.lesson.pk])).status_code, 404
        )
        self.client.force_login(self.student)
        self.assertNotEqual(self.client.get(urls[0]).status_code, 200)

    def test_the_exports(self):
        lessons = self.csv("lessons")
        self.assertEqual(
            [(x["lesson_id"], x["kind"], x["cohort"], x["trials"]) for x in lessons],
            [(str(self.lesson.pk), "research_practice", "experimental", "1")],
        )
        trials = self.csv("trials")
        self.assertEqual((trials[0]["mode"], trials[0]["turns"], trials[0]["level"]), ("stepwise", "1", "medium"))
        messages = self.csv("ai_messages")
        self.assertEqual({m["mode"] for m in messages}, {"student_sim"})
        self.assertTrue(any(m["role"] == "assistant" and m["structured"] for m in messages))
        other = User.objects.create_user("tb", "tb@example.kz", "x", role=User.Role.TEACHER)
        self.client.force_login(other)
        for name in ("lessons", "trials", "ai_messages"):
            self.assertEqual(self.csv(name), [], name)

    def test_the_statistics(self):
        services.unlock_section(self.enrollment(), self.section(2), self.teacher)
        r = self.client.get(reverse("research:analytics_course", args=[self.course.slug]))
        funnel = r.context["section_funnel"]
        self.assertEqual(len(funnel), 8)
        usage = {row["mode"]: row["cells"] for row in r.context["ai_usage"]}
        self.assertEqual(usage["student_sim"]["experimental"]["students"], 1)
        self.assertGreater(usage["student_sim"]["all"]["tokens"], 0)
        self.assertEqual(usage["expert"]["all"]["answers"], 0)
        self.assertEqual(
            [g["kind"] for g in r.context["icpai_grades"]], ["research_practice", "microlesson", "independent"]
        )
        self.assertContains(r, reverse("research:export_ai_messages"))
