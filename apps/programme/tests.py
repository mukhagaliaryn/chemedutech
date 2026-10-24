"""STEP-29: the ICPAI programme — sections, the 80 % rule, manual opening, the student and teacher pages."""

from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext, override

from apps.accounts.models import User
from apps.assessments import selectors as quiz_selectors
from apps.assessments import services as quiz_services
from apps.assessments.models import Quiz, QuizAttempt
from apps.courses import services as course_services
from apps.courses.models import Course, CourseTeacher, Enrollment, Stage, Topic
from apps.feedback.models import Notification
from apps.organizations.testing import make_group, make_student
from apps.progress import services as progress
from apps.progress.tests import build_course

from . import selectors, services
from .models import (
    DiagnosticResult,
    DiagnosticTest,
    Programme,
    ProgrammeEnrollment,
    Section,
    SectionEvent,
    SectionProgress,
)
from .providers import PROVIDERS, Provider
from .services import diagnostics

S = SectionProgress.Status
KINDS = [k for k, _label in Section.Kind.choices]  # course, diagnostic, … — the 8 kinds in section order


class Fixed(Provider):
    """A provider whose percent the test sets."""

    def __init__(self, value):
        self.value = Decimal(value)

    def percent(self, enrollment, section):
        return self.value


def make_programme(course, kinds=KINDS):
    programme = Programme.objects.create(title="ICPAI", slug=f"icpai{Programme.objects.count()}", course=course)
    for number, kind in enumerate(kinds, start=1):
        Section.objects.create(programme=programme, number=number, kind=kind, title=f"S{number}", purpose=f"P{number}")
    return programme


@override_settings(ALLOWED_HOSTS=["testserver"])
class Base(TestCase):
    def setUp(self):
        self.group = make_group(name="Хим-23-1", research_cohort="experimental")
        self.student = make_student("s1", group=self.group)
        # one topic of 5 required stages → each stage is 20 % of section 1
        self.course, (self.stages,) = build_course([["theory", "video", "lab", "practice", "test"]])
        self.programme = make_programme(self.course)
        self.course_enrollment = course_services.enroll(self.student, self.course, "group", group=self.group)
        progress.ensure_progress(self.course_enrollment)

    def enrollment(self):
        return services.refresh(self.student)

    def status(self, number):
        return SectionProgress.objects.get(enrollment__student=self.student, section__number=number).status

    def section(self, number):
        return self.programme.sections.get(number=number)

    def pass_stages(self, count):
        for stage in self.stages[:count]:
            progress.complete_stage(self.course_enrollment, stage, 100)


class EnrolmentTests(Base):
    def test_join_copies_group_and_research_group(self):
        enrollment = self.enrollment()
        self.assertEqual((enrollment.group, enrollment.research_cohort), (self.group, "experimental"))
        self.assertEqual(ProgrammeEnrollment.objects.filter(student=self.student).count(), 1)
        self.enrollment()  # idempotent
        self.assertEqual(ProgrammeEnrollment.objects.filter(student=self.student).count(), 1)

    def test_only_active_programmes_and_students(self):
        Programme.objects.update(is_active=False)
        self.assertIsNone(self.enrollment())
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.assertEqual(services.sync_student(teacher), [])

    def test_a_dropped_course_enrolment_does_not_join(self):
        Enrollment.objects.filter(pk=self.course_enrollment.pk).update(status=Enrollment.Status.DROPPED)
        self.assertIsNone(self.enrollment())


class EngineTests(Base):
    def test_only_the_first_section_is_open_at_the_start(self):
        self.enrollment()
        self.assertEqual(self.status(1), S.AVAILABLE)
        self.assertTrue(all(self.status(n) == S.LOCKED for n in range(2, 9)))

    def test_section_one_percent_is_the_share_of_done_required_stages(self):
        self.pass_stages(3)
        self.enrollment()
        row = SectionProgress.objects.get(section__number=1)
        self.assertEqual((row.status, row.percent), (S.IN_PROGRESS, Decimal("60.00")))
        self.assertEqual(self.status(2), S.LOCKED)

    def test_four_of_five_stages_is_80_percent_and_opens_section_two(self):
        self.pass_stages(4)
        self.enrollment()
        self.assertEqual(self.status(1), S.PASSED)
        self.assertEqual(self.status(2), S.AVAILABLE)  # not built yet: 0 %, but open
        self.assertEqual(self.status(3), S.LOCKED)

    def test_79_percent_keeps_the_next_section_locked_80_opens_it(self):
        with patch.dict(PROVIDERS, {Section.Kind.COURSE: Fixed("79.99")}):
            self.enrollment()
            self.assertEqual((self.status(1), self.status(2)), (S.IN_PROGRESS, S.LOCKED))
        with patch.dict(PROVIDERS, {Section.Kind.COURSE: Fixed(80)}):
            self.enrollment()
            self.assertEqual((self.status(1), self.status(2)), (S.PASSED, S.AVAILABLE))

    def test_the_pass_mark_is_a_setting_of_the_section(self):
        Section.objects.filter(pk=self.section(1).pk).update(pass_percent=60)
        self.pass_stages(3)
        self.enrollment()
        self.assertEqual(self.status(2), S.AVAILABLE)

    def test_awaiting_check_counts_as_done_score_does_not_matter(self):
        progress.complete_stage(self.course_enrollment, self.stages[0], 10, passed=True)  # a low score, passed
        progress.complete_stage(self.course_enrollment, self.stages[1], 0, awaiting_check=True)
        self.enrollment()
        self.assertEqual(SectionProgress.objects.get(section__number=1).percent, Decimal("40.00"))

    def test_optional_stages_and_unpublished_topics_do_not_count(self):
        Stage.objects.filter(pk=self.stages[4].pk).update(is_required=False)
        topic = self.stages[0].topic
        hidden = Topic.objects.create(module=topic.module, number=2, order=2, title="T2", is_published=False)
        Stage.objects.create(topic=hidden, order=1, kind="theory", title="hidden")
        self.pass_stages(3)
        self.enrollment()
        self.assertEqual(SectionProgress.objects.get(section__number=1).percent, Decimal("75.00"))

    def test_a_passed_section_stays_passed_when_the_percent_falls(self):
        with patch.dict(PROVIDERS, {Section.Kind.COURSE: Fixed(90)}):
            self.enrollment()
        with patch.dict(PROVIDERS, {Section.Kind.COURSE: Fixed(10)}):
            self.enrollment()
        row = SectionProgress.objects.get(section__number=1)
        self.assertEqual((row.status, row.percent), (S.PASSED, Decimal("10.00")))
        self.assertEqual(self.status(2), S.AVAILABLE)
        self.assertTrue(SectionEvent.objects.filter(action="percent", percent=Decimal("10.00")).exists())

    def test_events_are_logged_once(self):
        self.pass_stages(4)
        self.enrollment()
        self.enrollment()
        events = list(SectionEvent.objects.order_by("pk").values_list("section__number", "action"))
        self.assertEqual(events.count((1, "opened")), 1)
        self.assertEqual(events.count((1, "passed")), 1)
        self.assertEqual(events.count((2, "opened")), 1)
        self.assertEqual(events.count((1, "percent")), 1)

    def test_a_new_section_is_announced_the_first_is_not(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.enrollment()
        self.assertFalse(Notification.objects.filter(user=self.student, kind="section").exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.pass_stages(4)
            self.enrollment()
        note = Notification.objects.get(user=self.student, kind="section")
        self.assertEqual((note.title, note.url), ("2. S2", reverse("student:section", args=[2])))

    def test_completed_when_every_section_is_passed(self):
        with patch.dict(PROVIDERS, {k: Fixed(100) for k in KINDS}):
            enrollment = self.enrollment()
        enrollment.refresh_from_db()
        self.assertIsNotNone(enrollment.completed_at)
        self.assertTrue(all(self.status(n) == S.PASSED for n in range(1, 9)))

    def test_sections_added_or_reordered_later(self):
        self.pass_stages(4)
        self.enrollment()
        Section.objects.create(programme=self.programme, number=9, kind="independent", title="S9")
        self.enrollment()
        self.assertEqual(self.status(9), S.LOCKED)
        # section 3 moves before section 2: it follows passed section 1 now and opens; old 2 (now 4) stays open
        Section.objects.filter(pk=self.section(3).pk).update(number=20)
        Section.objects.filter(pk=self.section(2).pk).update(number=3)
        Section.objects.filter(number=20).update(number=2)
        self.enrollment()
        self.assertEqual((self.status(2), self.status(3)), (S.AVAILABLE, S.LOCKED))

    def test_access_and_the_blocking_section(self):
        enrollment = self.enrollment()
        self.assertTrue(services.can_access(enrollment, self.section(1)))
        self.assertFalse(services.can_access(enrollment, self.section(3)))
        self.assertEqual(services.blocking_section(enrollment, self.section(3)), self.section(1))
        other = make_programme(self.course)
        self.assertFalse(services.can_access(enrollment, other.sections.get(number=1)))

    def test_a_teacher_opens_a_section_by_hand(self):
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        enrollment = self.enrollment()
        with self.captureOnCommitCallbacks(execute=True):
            row = services.unlock_section(enrollment, self.section(4), teacher)
        self.assertEqual((row.status, row.unlocked_by), (S.AVAILABLE, teacher))
        self.assertEqual(self.status(5), S.LOCKED)  # the order goes on from there: 4 is not passed
        self.assertTrue(SectionEvent.objects.filter(section__number=4, action="unlocked", actor=teacher).exists())
        self.assertTrue(Notification.objects.filter(user=self.student, kind="section", title="4. S4").exists())
        self.enrollment()
        self.assertEqual(self.status(4), S.AVAILABLE)  # stays open whatever the order says
        with self.assertRaises(services.SectionLocked):
            services.unlock_section(enrollment, make_programme(self.course).sections.get(number=2), teacher)


class StudentPageTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.student)

    def test_home_shows_the_guide_and_the_sections_instead_of_the_key_figures(self):
        r = self.client.get(reverse("student:dashboard"))
        self.assertTemplateUsed(r, "student/home.html")
        self.assertContains(r, "P4")  # the section's «what it does»
        self.assertContains(r, reverse("student:section", args=[8]))
        with override("kk"):
            self.assertNotContains(r, gettext("Key figures"))
        self.assertContains(r, self.stages[0].title)  # «Continue» leads to the next course stage

    def test_without_a_programme_the_old_dashboard_stays(self):
        Programme.objects.update(is_active=False)
        r = self.client.get(reverse("student:dashboard"))
        self.assertTemplateUsed(r, "student/dashboard.html")

    def test_sidebar_lists_the_sections(self):
        r = self.client.get(reverse("student:dashboard"))
        with override("kk"):
            self.assertContains(r, f'aria-label="{gettext("Programme sections")}"')
        for n in range(1, 9):
            self.assertContains(r, f"{n}. S{n}")

    def test_section_one_page_leads_to_the_course(self):
        r = self.client.get(reverse("student:section", args=[1]))
        self.assertTemplateUsed(r, "student/section.html")
        self.assertContains(r, "P1")
        self.assertContains(r, reverse("student:course", args=[self.course.slug]))
        self.assertContains(r, 'aria-current="page"')

    def test_a_locked_section_cannot_be_opened_by_url(self):
        r = self.client.get(reverse("student:section", args=[3]))
        self.assertTemplateUsed(r, "student/section_locked.html")
        self.assertTemplateNotUsed(r, "student/section.html")
        self.assertContains(r, reverse("student:section", args=[1]))

    def test_an_open_section_not_built_yet(self):
        Section.objects.filter(pk=self.section(2).pk).update(kind="video")  # an unbuilt kind
        self.pass_stages(4)
        r = self.client.get(reverse("student:section", args=[2]))
        self.assertTemplateUsed(r, "student/section.html")
        with override("kk"):
            self.assertContains(r, gettext("The section is in development"))

    def test_unknown_section_or_no_programme_is_404(self):
        self.assertEqual(self.client.get(reverse("student:section", args=[42])).status_code, 404)
        Programme.objects.update(is_active=False)
        self.assertEqual(self.client.get(reverse("student:section", args=[1])).status_code, 404)

    def test_a_student_cannot_open_a_section_by_hand(self):
        self.enrollment()
        url = reverse("teacher:unlock_section", args=[self.student.pk, 3])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(self.status(3), S.LOCKED)


class TeacherPageTests(Base):
    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user("ta", "ta@example.kz", "x", role=User.Role.TEACHER)
        self.other = User.objects.create_user("tb", "tb@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, teacher=self.teacher)
        Course.objects.filter(pk=self.course.pk).update(title="C")
        course_services.assign_group(self.course, self.group, teacher=self.teacher)
        self.client.force_login(self.teacher)

    def test_group_page_shows_students_by_sections(self):
        self.pass_stages(2)
        r = self.client.get(reverse("teacher:group", args=[self.group.pk]))
        self.assertEqual(len(r.context["sections"]), 8)
        cells = r.context["matrix"][0]["cells"]
        self.assertEqual((cells[0]["progress"].percent, cells[1]["progress"].status), (Decimal("40.00"), S.LOCKED))
        self.assertContains(r, reverse("teacher:unlock_section", args=[self.student.pk, 2]))

    def test_teacher_opens_a_section_from_the_group_page(self):
        back = reverse("teacher:group", args=[self.group.pk])
        r = self.client.post(reverse("teacher:unlock_section", args=[self.student.pk, 3]), {"next": back})
        self.assertRedirects(r, back, fetch_redirect_response=False)
        self.assertEqual(self.status(3), S.AVAILABLE)

    def test_another_teacher_cannot_open_it(self):
        self.client.force_login(self.other)
        r = self.client.post(reverse("teacher:unlock_section", args=[self.student.pk, 3]))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(SectionProgress.objects.filter(section__number=3, status=S.AVAILABLE).exists())


class SeedTests(TestCase):
    def test_seed_icpai(self):
        with self.assertRaises(CommandError):
            call_command("seed_icpai", verbosity=0)  # no course yet
        call_command("seed_course", topics=[1], verbosity=0)
        call_command("seed_icpai", verbosity=0)
        programme = Programme.objects.get(slug="icpai")
        self.assertEqual(programme.course.slug, "chemistry")
        sections = list(programme.sections.order_by("number"))
        self.assertEqual([s.kind for s in sections], KINDS)
        self.assertEqual(sections[0].title, "Теориялық таным")
        self.assertEqual(sections[1].title, "Кәсіби даярлық")
        self.assertTrue(sections[7].purpose.startswith("Бұл кезеңде бұрынғы дайын авторлық сабақ үлгілері"))
        self.assertEqual({s.pass_percent for s in sections}, {80})
        Section.objects.filter(number=3).update(title="Edited", pass_percent=70)
        call_command("seed_icpai", verbosity=0)  # kept
        self.assertEqual(programme.sections.get(number=3).title, "Edited")
        call_command("seed_icpai", replace=True, verbosity=0)  # texts from the code, the pass mark stays
        section = programme.sections.get(number=3)
        self.assertEqual((section.title, section.pass_percent), ("Ақпараттық білім беру ортасы", 70))
        self.assertEqual(programme.sections.count(), 8)

    def test_seed_course_renames_the_legacy_title_only(self):
        call_command("seed_course", topics=[1], verbosity=0)
        course = Course.objects.get(slug="chemistry")
        self.assertEqual(course.title, "Жалпы химия")
        Course.objects.filter(pk=course.pk).update(title="Бейорганикалық химия")
        call_command("seed_course", topics=[1], verbosity=0)
        self.assertEqual(Course.objects.get(pk=course.pk).title, "Жалпы химия")
        Course.objects.filter(pk=course.pk).update(title="Менің курсым")
        call_command("seed_course", topics=[1], verbosity=0)
        self.assertEqual(Course.objects.get(pk=course.pk).title, "Менің курсым")

    def test_selectors_current_section(self):
        rows = [{"status": S.PASSED}, {"status": S.IN_PROGRESS}, {"status": S.LOCKED}]
        self.assertIs(selectors.current_section(rows), rows[1])
        rows = [{"status": S.PASSED}, {"status": S.LOCKED}]
        self.assertIs(selectors.current_section(rows), rows[0])


# --- STEP-31: section 2 — the diagnostics I → II → III (D71) ---------------------------------------------------


def make_diagnostics(section):
    """The three tests of the guide (seed data) on a section of kind «diagnostic»."""
    from .management.commands._icpai.diagnostics import DIAGNOSTICS
    from .management.commands.seed_icpai import Command

    tests = {}
    for phase, data in DIAGNOSTICS.items():
        quiz = Quiz.objects.create(title=data["stage"], kind=Quiz.Kind.DIAGNOSTIC, pass_percent=0, max_attempts=1)
        Command.fill(quiz, data["questions"])
        tests[phase] = DiagnosticTest.objects.create(
            section=section, phase=phase, quiz=quiz, stage_name=data["stage"], note=data["note"], title=data["title"],
            aim=data["aim"], levels=data["levels"],
        )  # fmt: skip
    return tests


class DiagnosticsBase(Base):
    def setUp(self):
        super().setUp()
        self.tests = make_diagnostics(self.section(2))
        self.pass_stages(4)  # section 1 at 80 % → section 2 opens
        self.penr = self.enrollment()

    def take(self, phase, correct=None):
        """Take a stage; ``correct`` — the question numbers (1–10) answered right, the rest wrong (all by default)."""
        test = self.tests[phase]
        attempt = diagnostics.start(self.penr, test)
        answers = {}
        for n, q in enumerate(test.quiz.questions.order_by("order"), start=1):
            right = correct is None or n in correct
            answers[q.pk] = q.choices.filter(is_correct=right).first().pk
        attempt = quiz_services.submit_attempt(attempt, answers)
        return diagnostics.record(self.penr, test, attempt)


class DiagnosticsTests(DiagnosticsBase):
    def test_stages_open_one_after_another_and_section_2_needs_all_three(self):
        self.assertEqual(diagnostics.state(self.penr, self.tests["I"]), diagnostics.OPEN)
        self.assertEqual(diagnostics.state(self.penr, self.tests["II"]), diagnostics.LOCKED)
        with self.assertRaises(quiz_services.AttemptError):
            diagnostics.start(self.penr, self.tests["II"])
        self.take("I")
        self.assertEqual(diagnostics.state(self.penr, self.tests["II"]), diagnostics.OPEN)
        self.assertEqual(diagnostics.state(self.penr, self.tests["III"]), diagnostics.LOCKED)
        self.assertEqual(SectionProgress.objects.get(section__number=2).percent, Decimal("33.33"))
        self.take("II")
        self.assertEqual((self.status(2), self.status(3)), (S.IN_PROGRESS, S.LOCKED))  # 66.67 % < 80 %
        self.take("III")
        self.assertEqual((self.status(2), self.status(3)), (S.PASSED, S.AVAILABLE))

    def test_closed_while_section_2_is_locked(self):
        other = make_student("s2", group=self.group)
        enr = course_services.enroll(other, self.course, "group", group=self.group)
        progress.ensure_progress(enr)
        penr = services.refresh(other)
        self.assertEqual(diagnostics.state(penr, self.tests["I"]), diagnostics.LOCKED)

    def test_component_percent_and_level(self):
        # the guide's example: 2 of the 3 cognitive questions (3–5) right → 66.7 %
        rows = {r.component: r for r in self.take("I", correct={1, 2, 3, 4, 6, 7})}
        self.assertEqual(rows["cognitive"].percent, Decimal("66.67"))
        self.assertEqual(
            (rows["motivational"].percent, rows["activity"].percent), (Decimal("100.00"), Decimal("66.67"))
        )
        self.assertEqual(rows["reflective"].percent, Decimal("0.00"))
        self.assertEqual({r.level for r in rows.values()}, {"medium"})  # 6 of 10
        self.assertEqual(
            [diagnostics.level_for(n, 10) for n in (0, 4, 5, 7, 8, 10)],
            ["low", "low", "medium", "medium", "high", "high"],
        )

    def test_once_only_and_kept_out_of_the_course_statistics(self):
        self.take("I")
        with self.assertRaises(quiz_services.AttemptError):
            diagnostics.start(self.penr, self.tests["I"])
        attempt = QuizAttempt.objects.get(quiz=self.tests["I"].quiz)
        self.assertEqual((attempt.phase, attempt.enrollment), ("I", self.course_enrollment))
        self.assertFalse(quiz_selectors.finished_attempts(self.course_enrollment).exists())
        self.assertEqual(len(diagnostics.record(self.penr, self.tests["I"], attempt)), 4)  # recorded once
        self.assertEqual(DiagnosticResult.objects.count(), 4)


class DiagnosticsPageTests(DiagnosticsBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.student)

    def url(self, phase, name="student:diagnostic"):
        return reverse(name, args=[2, phase])

    def test_section_2_lists_the_stages(self):
        r = self.client.get(reverse("student:section", args=[2]))
        for test in self.tests.values():
            self.assertContains(r, test.stage_name)
        self.assertContains(r, self.url("I"))

    def test_intro_start_take_submit_result(self):
        r = self.client.get(self.url("I"))
        self.assertContains(r, self.tests["I"].title)
        self.assertContains(r, self.tests["I"].aim)
        self.assertRedirects(self.client.post(self.url("I", "student:diagnostic_start")), self.url("I"))
        r = self.client.get(self.url("I"))
        self.assertTemplateUsed(r, "assessments/take.html")
        attempt = QuizAttempt.objects.get(quiz=self.tests["I"].quiz)
        data = {f"q{q.pk}": q.choices.get(is_correct=True).pk for q in self.tests["I"].quiz.questions.all()}
        submit = reverse("student:diagnostic_submit", args=[2, "I", attempt.pk])
        self.assertRedirects(self.client.post(submit, data), self.url("I"))
        r = self.client.get(self.url("I"))
        self.assertTemplateUsed(r, "student/diagnostic.html")
        self.assertContains(r, self.tests["I"].levels["high"])  # 10 of 10 → the guide's «high» interpretation
        first = self.tests["I"].quiz.questions.order_by("order").first()
        self.assertNotContains(r, first.choices.get(is_correct=True).text)  # the key is not shown
        self.assertContains(r, self.url("II"))  # on to stage II

    def test_stage_two_has_no_interpretation_in_the_guide(self):
        self.take("I")
        self.take("II")
        r = self.client.get(self.url("II"))
        self.assertEqual(r.context["interpretation"], "")

    def test_locked_stage_cannot_be_started(self):
        r = self.client.get(self.url("III"))
        self.assertEqual(r.context["row"]["state"], diagnostics.LOCKED)
        self.client.post(self.url("III", "student:diagnostic_start"))
        self.assertFalse(QuizAttempt.objects.filter(quiz=self.tests["III"].quiz).exists())

    def test_results_page(self):
        r = self.client.get(reverse("student:icpai"))
        self.assertFalse(r.context["taken"])
        self.take("I", correct={1, 2, 3, 4, 6, 7})
        self.take("II")
        r = self.client.get(reverse("student:icpai"))
        cognitive = next(row for row in r.context["rows"] if row["component"] == "cognitive")
        self.assertEqual(cognitive["phases"], {"I": Decimal("66.67"), "II": Decimal("100.00"), "III": None})
        self.assertEqual(cognitive["latest"], Decimal("100.00"))
        self.assertContains(r, reverse("student:results"))  # course grades


class DiagnosticsTeacherTests(DiagnosticsBase):
    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user("ta", "ta@example.kz", "x", role=User.Role.TEACHER)
        self.other = User.objects.create_user("tb", "tb@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, teacher=self.teacher)
        course_services.assign_group(self.course, self.group, teacher=self.teacher)
        self.take("I", correct={1, 2, 3, 4, 5, 6, 7})
        self.client.force_login(self.teacher)

    def test_group_page_shows_the_stages(self):
        r = self.client.get(reverse("teacher:group", args=[self.group.pk]))
        first = r.context["matrix"][0]["diagnostics"]
        self.assertEqual((first[0]["earned"], first[0]["level"], first[1]), (Decimal("7.00"), "medium", None))

    def test_analytics_by_component_stage_and_cohort(self):
        r = self.client.get(reverse("research:analytics_course", args=[self.course.slug]))
        rows = {(row["component"], row["cohort"]): row for row in r.context["diagnostic_rows"]}
        self.assertEqual(rows[("cognitive", "experimental")]["I"]["mean"], 100.0)
        self.assertEqual(rows[("reflective", "experimental")]["I"]["mean"], 0.0)
        self.assertEqual(rows[("cognitive", "control")]["I"]["n"], 0)

    def test_csv_export_is_scoped(self):
        r = self.client.get(reverse("research:export_diagnostics"))
        lines = b"".join(r.streaming_content if r.streaming else [r.content]).decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(lines), 1 + 4)
        self.assertIn("I,cognitive", lines[1] + lines[2] + lines[3] + lines[4])
        self.client.force_login(self.other)
        r = self.client.get(reverse("research:export_diagnostics"))
        lines = b"".join(r.streaming_content if r.streaming else [r.content]).decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(lines), 1)


class DiagnosticsSeedTests(TestCase):
    def test_seed_makes_three_tests_from_the_guide(self):
        call_command("seed_course", topics=[1], verbosity=0)
        call_command("seed_icpai", verbosity=0)
        tests = list(DiagnosticTest.objects.order_by("phase"))
        self.assertEqual([t.phase for t in tests], ["I", "II", "III"])
        keys = []
        for t in tests:
            questions = list(t.quiz.questions.order_by("order"))
            self.assertEqual(len(questions), 10)
            keys.append(
                "".join("ABCD"[[c.is_correct for c in q.choices.order_by("order")].index(True)] for q in questions)
            )
        self.assertEqual(keys, ["CBADBCADBC", "DBACDBCADB", "BDACBADCBA"])  # the guide's answer keys
        self.assertEqual(tests[0].quiz.max_attempts, 1)
        self.assertEqual(tests[1].levels, {})
        call_command("seed_icpai", verbosity=0)
        self.assertEqual(DiagnosticTest.objects.count(), 3)
