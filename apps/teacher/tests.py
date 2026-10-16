"""STEP-10: teacher cabinet — scope (own courses and groups only), groups, students, manual unlock."""

from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.accounts.models import User
from apps.assessments.models import QuizAttempt
from apps.courses import selectors as course_selectors
from apps.courses import services as course_services
from apps.courses.models import Course, CourseGroup, CourseTeacher, Enrollment, Stage
from apps.feedback.models import Notification
from apps.labs.models import LabAttempt, LabEvent
from apps.organizations.models import AcademicGroup, TeacherProfile
from apps.organizations.testing import make_group, make_student
from apps.progress import services as progress
from apps.progress.models import ProgressEvent, StageProgress

from . import overview

S = StageProgress.Status


@override_settings(ALLOWED_HOSTS=["testserver"])
class TeacherBase(TestCase):
    """Teacher A teaches «chemistry» and curates Хим-23-1 (s1, s2); teacher B curates Био-23-1 (s3)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")
        cls.stages = list(Stage.objects.filter(topic__number=1).order_by("order", "pk"))

    def setUp(self):
        self.teacher = User.objects.create_user("ta", "ta@example.kz", "x", role=User.Role.TEACHER)
        self.other = User.objects.create_user("tb", "tb@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, teacher=self.teacher)
        self.g1 = make_group(name="Хим-23-1", curator=self.teacher)
        TeacherProfile.objects.create(user=self.teacher, department=self.g1.department)
        self.g2 = make_group(name="Био-23-1", curator=self.other)
        self.s1 = make_student("s1", group=self.g1, first_name="Айгерім", last_name="Сапарова")
        self.s2 = make_student("s2", group=self.g1)
        self.s3 = make_student("s3", group=self.g2)
        course_services.assign_group(self.course, self.g1, teacher=self.teacher)
        self.e1 = Enrollment.objects.get(student=self.s1, course=self.course)
        self.client.force_login(self.teacher)


class ScopeTests(TeacherBase):
    def test_selectors(self):
        self.assertEqual(set(course_selectors.teacher_groups(self.teacher)), {self.g1})
        self.assertEqual(set(course_selectors.teacher_groups(self.other)), {self.g2})  # curator, no course
        self.assertEqual(set(course_selectors.teacher_students(self.teacher)), {self.s1, self.s2})
        self.assertEqual(set(course_selectors.teacher_students(self.other)), {self.s3})
        admin = User.objects.create_superuser("root", "root@example.kz", "x")
        self.assertTrue({self.g1, self.g2} <= set(course_selectors.teacher_groups(admin)))

    def test_self_enrolled_student_without_group_is_visible(self):
        loner = make_student("loner")
        course_services.enroll(loner, self.course, Enrollment.Source.SELF)
        self.assertIn(loner, course_selectors.teacher_students(self.teacher))
        self.assertNotIn(loner, course_selectors.teacher_students(self.other))

    def test_foreign_objects_are_404(self):
        self.assertEqual(self.client.get(reverse("teacher:group", args=[self.g2.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("teacher:student", args=[self.s3.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("teacher:group_join_code", args=[self.g2.pk])).status_code, 404)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("teacher:student", args=[self.s1.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("teacher:group", args=[self.g1.pk])).status_code, 404)

    def test_students_cannot_enter(self):
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(reverse("teacher:dashboard")).status_code, 403)

    def test_teacher_lands_on_the_dashboard(self):
        self.client.logout()
        r = self.client.post(reverse("accounts:login"), {"username": "ta", "password": "x"})
        self.assertRedirects(r, reverse("teacher:dashboard"), fetch_redirect_response=False)


class DashboardTests(TeacherBase):
    def test_numbers_and_attention(self):
        quiz = self.stages[0].checkpoint_quiz
        for n in (1, 2, 3):
            QuizAttempt.objects.create(
                enrollment=self.e1, user=self.s1, quiz=quiz, attempt_no=n,
                finished_at=timezone.now(), percent=Decimal("25"), passed=False,
            )  # fmt: skip
        e2 = Enrollment.objects.get(student=self.s2)
        Enrollment.objects.filter(pk=e2.pk).update(created_at=timezone.now() - timedelta(days=10))
        r = self.client.get(reverse("teacher:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["students"], 2)
        self.assertEqual(r.context["active_week"], 1)
        reasons = {row["student"].username: reason for row, reason in r.context["attention"]}
        self.assertIn("3", reasons["s1"])  # failed the quiz 3 times
        self.assertIn("10", reasons["s2"])  # 10 days inactive
        self.assertEqual([g["group"] for g in r.context["groups"]], [self.g1])
        self.assertContains(r, "Хим-23-1")

    def test_queue(self):
        from apps.practice.models import PracticeSubmission

        practice = next(s for s in self.stages if s.kind == "practice")
        PracticeSubmission.objects.create(enrollment=self.e1, stage=practice, attempt_no=1, status="needs_review")
        r = self.client.get(reverse("teacher:dashboard"))
        self.assertEqual(r.context["queue_count"], 1)
        self.assertContains(r, reverse("teacher:student", args=[self.s1.pk]))


class GroupTests(TeacherBase):
    def test_group_page_rows(self):
        lab = next(s for s in self.stages if s.kind == "lab")
        LabAttempt.objects.create(
            user=self.s1, enrollment=self.e1, stage=lab, lab_key="t01", experiment_key="hydrogen",
            order_errors=1, safety_warnings=3, wrong_items=1, wrong_choices=1,
        )  # fmt: skip
        r = self.client.get(reverse("teacher:group", args=[self.g1.pk]))
        self.assertEqual(r.status_code, 200)
        row = next(x for x in r.context["rows"] if x["student"] == self.s2)
        self.assertEqual(row["position"]["text"], gettext("Not started yet"))
        progress.recalculate(self.e1)
        r = self.client.get(reverse("teacher:group", args=[self.g1.pk]))
        row = next(x for x in r.context["rows"] if x["student"] == self.s1)
        self.assertEqual((row["errors"]["order"], row["errors"]["safety"], row["errors"]["wrong"]), (1, 3, 2))
        self.assertEqual(row["position"]["text"], f"1.1 {self.stages[0].get_kind_display()}")
        self.assertTrue(any("3" in reason for reason in row["attention"]))
        r = self.client.get(reverse("teacher:group", args=[self.g1.pk]), {"q": "сапар"})
        self.assertEqual([x["student"] for x in r.context["rows"]], [self.s1])
        r = self.client.get(reverse("teacher:group", args=[self.g1.pk]), {"show": "attention"})
        self.assertEqual([x["student"] for x in r.context["rows"]], [self.s1])

    def test_csv(self):
        r = self.client.get(reverse("teacher:group", args=[self.g1.pk]), {"format": "csv"})
        text = r.content.decode("utf-8-sig").splitlines()
        self.assertTrue(text[0].startswith("student,username,email,group,course"))
        self.assertEqual(len(text), 3)

    def test_create_group(self):
        r = self.client.post(
            reverse("teacher:group_new"),
            {"name": "Хим-24-1", "department": self.g1.department.pk, "admission_year": 2024, "study_year": 1,
             "research_cohort": "control", "is_active": "on"},
        )  # fmt: skip
        group = AcademicGroup.objects.get(name="Хим-24-1")
        self.assertRedirects(r, reverse("teacher:group", args=[group.pk]), fetch_redirect_response=False)
        self.assertEqual((group.curator, group.research_cohort), (self.teacher, "control"))
        self.assertEqual(len(group.join_code), 8)

    def test_department_is_limited_to_the_teachers_university(self):
        r = self.client.get(reverse("teacher:group_new"))
        self.assertEqual(list(r.context["form"].fields["department"].queryset), [self.g1.department])

    def test_research_cohort_fills_only_empty_enrolments(self):
        e2 = Enrollment.objects.get(student=self.s2)
        Enrollment.objects.filter(pk=e2.pk).update(research_cohort="control")
        lab = next(s for s in self.stages if s.kind == "lab")
        attempt = LabAttempt.objects.create(
            user=self.s1, enrollment=self.e1, stage=lab, lab_key="t01", experiment_key="hydrogen", research_cohort=""
        )
        r = self.client.post(reverse("teacher:group_cohort", args=[self.g1.pk]), {"research_cohort": "experimental"})
        self.assertRedirects(r, reverse("teacher:group", args=[self.g1.pk]), fetch_redirect_response=False)
        self.g1.refresh_from_db()
        self.assertEqual(self.g1.research_cohort, "experimental")
        self.e1.refresh_from_db()
        e2.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual((self.e1.research_cohort, e2.research_cohort), ("experimental", "control"))
        self.assertEqual(attempt.research_cohort, "")  # the research log is never rewritten

    def test_edit_form_changes_the_cohort(self):
        data = {"name": self.g1.name, "department": self.g1.department.pk, "admission_year": 2023, "study_year": 2,
                "research_cohort": "control", "is_active": "on"}  # fmt: skip
        self.client.post(reverse("teacher:group_edit", args=[self.g1.pk]), data)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.research_cohort, "control")

    def test_add_and_remove_students(self):
        newcomer = make_student("new", email="new@example.kz")
        r = self.client.post(reverse("teacher:group_add_student", args=[self.g1.pk]), {"query": "NEW@example.kz"})
        self.assertRedirects(r, reverse("teacher:group", args=[self.g1.pk]), fetch_redirect_response=False)
        newcomer.student_profile.refresh_from_db()
        self.assertEqual(newcomer.student_profile.group, self.g1)
        self.assertTrue(Enrollment.objects.filter(student=newcomer, course=self.course, source="group").exists())
        # a student of another teacher's group cannot be taken
        self.client.post(reverse("teacher:group_add_student", args=[self.g1.pk]), {"query": "s3"})
        self.s3.student_profile.refresh_from_db()
        self.assertEqual(self.s3.student_profile.group, self.g2)
        # removing keeps the enrolment and progress
        self.client.post(reverse("teacher:group_remove_student", args=[self.g1.pk, self.s1.pk]))
        self.s1.student_profile.refresh_from_db()
        self.assertIsNone(self.s1.student_profile.group)
        self.assertTrue(Enrollment.objects.filter(pk=self.e1.pk).exists())

    def test_join_code_attach_detach_delete(self):
        old = self.g1.join_code
        self.client.post(reverse("teacher:group_join_code", args=[self.g1.pk]))
        self.g1.refresh_from_db()
        self.assertNotEqual(self.g1.join_code, old)
        link = CourseGroup.objects.get(group=self.g1)
        self.client.post(reverse("teacher:group_detach", args=[self.g1.pk, link.pk]))
        self.assertFalse(CourseGroup.objects.filter(group=self.g1).exists())
        self.assertTrue(Enrollment.objects.filter(pk=self.e1.pk).exists())
        r = self.client.post(reverse("teacher:group_attach", args=[self.g1.pk]), {"course": self.course.pk})
        self.assertTrue(CourseGroup.objects.filter(group=self.g1, course=self.course, teacher=self.teacher).exists())
        # a group with students cannot be deleted
        r = self.client.post(reverse("teacher:group_delete", args=[self.g1.pk]))
        self.assertRedirects(r, reverse("teacher:group_edit", args=[self.g1.pk]), fetch_redirect_response=False)
        self.assertTrue(AcademicGroup.objects.filter(pk=self.g1.pk).exists())
        empty = make_group(name="Бос", curator=self.teacher, department=self.g1.department)
        self.client.post(reverse("teacher:group_delete", args=[empty.pk]))
        self.assertFalse(AcademicGroup.objects.filter(pk=empty.pk).exists())

    def test_cannot_attach_a_foreign_course(self):
        foreign = Course.objects.create(title="Biology", slug="bio")
        r = self.client.post(reverse("teacher:group_attach", args=[self.g1.pk]), {"course": foreign.pk})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(CourseGroup.objects.filter(course=foreign).exists())


class StudentPageTests(TeacherBase):
    def test_profile(self):
        r = self.client.get(reverse("teacher:student", args=[self.s1.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["enrollment"], self.e1)
        self.assertEqual(len(r.context["topics"][0]["table"]), len(self.stages))
        self.assertContains(r, reverse("teacher:unlock_stage", args=[self.s1.pk, self.stages[2].pk]))

    def test_unlock(self):
        lab = next(s for s in self.stages if s.kind == "lab")
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse("teacher:unlock_stage", args=[self.s1.pk, lab.pk]), {"course": "chemistry"})
        self.assertEqual(r.status_code, 302)
        sp = StageProgress.objects.get(enrollment=self.e1, stage=lab)
        self.assertEqual((sp.status, sp.unlocked_by), (S.AVAILABLE, self.teacher))
        self.assertTrue(ProgressEvent.objects.filter(enrollment=self.e1, stage=lab, action="unlocked").exists())
        self.assertTrue(Notification.objects.filter(user=self.s1, kind="unlocked").exists())

    def test_lab_log(self):
        lab = next(s for s in self.stages if s.kind == "lab")
        attempt = LabAttempt.objects.create(
            user=self.s1, enrollment=self.e1, stage=lab, lab_key="t01", experiment_key="oxygen"
        )
        LabEvent.objects.create(attempt=attempt, seq=1, t_ms=65300, type="safety_warning", step="heat")
        r = self.client.get(reverse("teacher:lab_log", args=[self.s1.pk, attempt.pk]))
        self.assertContains(r, "1:05.3")
        self.assertContains(r, "heat")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("teacher:lab_log", args=[self.s1.pk, attempt.pk])).status_code, 404)

    def test_students_list(self):
        r = self.client.get(reverse("teacher:students"), {"q": "s1"})
        self.assertEqual(list(r.context["students"]), [self.s1])

    def test_rows_for_a_finished_course(self):
        rows = overview.student_rows([self.e1])
        self.assertEqual(rows[0]["total"], len([s for s in self.stages if s.is_required]))
