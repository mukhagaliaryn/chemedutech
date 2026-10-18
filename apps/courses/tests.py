import shutil
import tempfile
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.assessments.models import QuizAttempt
from apps.core.html import clean_html
from apps.organizations.testing import make_group, make_student

from . import selectors, services
from .models import Course, CourseGroup, Enrollment, LabContent, Module, Stage, Topic


def make_course(**fields):
    fields.setdefault("title", "Химия")
    fields.setdefault("slug", f"chem-{Course.objects.count() + 1}")
    fields.setdefault("status", Course.Status.PUBLISHED)
    return Course.objects.create(**fields)


def make_topic(course, number=1, **fields):
    module, _ = Module.objects.get_or_create(course=course, order=1, defaults={"title": "M1"})
    return Topic.objects.create(module=module, number=number, title=fields.pop("title", f"T{number}"), **fields)


class StageFlexibilityTests(TestCase):
    """ARCHITECTURE §3.3: any number of stages of any kind, in any order."""

    def test_topic_with_three_practices_and_no_video(self):
        topic = make_topic(make_course())
        kinds = ["theory", "theory", "lab", "practice", "practice", "practice", "test"]
        for order, kind in enumerate(kinds, start=1):
            stage = Stage.objects.create(topic=topic, order=order, kind=kind, title=f"{kind} {order}")
            services.ensure_stage_content(stage)
        stages = list(selectors.stages_of(topic))
        self.assertEqual([s.kind for s in stages], kinds)
        self.assertEqual(sum(1 for s in stages if s.kind == Stage.Kind.PRACTICE), 3)
        theory = [s for s in stages if s.kind == Stage.Kind.THEORY]
        self.assertTrue(all(s.content is not None for s in theory))
        self.assertIsNone(stages[3].content)  # practice content arrives in STEP-07a

    def test_ensure_stage_content_is_idempotent_and_updates(self):
        stage = Stage.objects.create(topic=make_topic(make_course()), kind="lab", title="Lab")
        services.ensure_stage_content(stage, lab_key="t01")
        services.ensure_stage_content(stage, lab_key="t01", experiments=["oxygen"])
        self.assertEqual(LabContent.objects.filter(stage=stage).count(), 1)
        self.assertEqual([e.key for e in LabContent.objects.get(stage=stage).experiment_specs()], ["oxygen"])

    def test_lab_content_validates_experiment_keys(self):
        stage = Stage.objects.create(topic=make_topic(make_course()), kind="lab", title="Lab")
        content = LabContent(stage=stage, lab_key="t01", experiments=["nope"])
        with self.assertRaises(ValidationError):
            content.full_clean()
        content.experiments = ["hydrogen", "rate"]
        content.full_clean()

    def test_topic_number_unique_within_course(self):
        course = make_course()
        make_topic(course, 1)
        clash = Topic(module=course.modules.first(), number=1, title="Again")
        with self.assertRaises(ValidationError):
            clash.full_clean()
        make_topic(make_course(), 1)  # another course may reuse the number


class EnrollmentServiceTests(TestCase):
    def setUp(self):
        self.course = make_course(enrollment_mode=Course.EnrollmentMode.GROUP)
        self.group = make_group(research_cohort="experimental")
        self.s1 = make_student("s1", group=self.group)
        self.s2 = make_student("s2", group=self.group)

    def test_assign_group_enrols_its_students_with_cohort_snapshot(self):
        services.assign_group(self.course, self.group)
        enrollments = Enrollment.objects.filter(course=self.course)
        self.assertEqual(enrollments.count(), 2)
        self.assertTrue(all(e.source == "group" and e.research_cohort == "experimental" for e in enrollments))
        # the snapshot stays when the group changes cohort later
        self.group.research_cohort = "control"
        self.group.save()
        services.assign_group(self.course, self.group)
        self.assertEqual(Enrollment.objects.get(student=self.s1).research_cohort, "experimental")

    def test_late_group_member_is_enrolled_on_sync(self):
        services.assign_group(self.course, self.group)
        late = make_student("late", group=self.group)
        self.assertEqual(services.sync_student_enrollments(late), 1)
        self.assertEqual(services.sync_student_enrollments(late), 0)
        self.assertTrue(Enrollment.objects.filter(student=late, course=self.course).exists())

    def test_enroll_is_unique_and_students_only(self):
        e1 = services.enroll(self.s1, self.course, "admin")
        e2 = services.enroll(self.s1, self.course, "self")
        self.assertEqual(e1.pk, e2.pk)
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        with self.assertRaises(services.EnrollmentError):
            services.enroll(teacher, self.course, "admin")

    def test_self_enroll_only_open_published(self):
        with self.assertRaises(services.EnrollmentError):
            services.self_enroll(self.s1, self.course)
        self.course.enrollment_mode = Course.EnrollmentMode.OPEN
        self.course.status = Course.Status.DRAFT
        self.course.save()
        with self.assertRaises(services.EnrollmentError):
            services.self_enroll(self.s1, self.course)
        self.course.status = Course.Status.PUBLISHED
        self.course.save()
        self.assertEqual(services.self_enroll(self.s1, self.course).source, "self")

    def test_enroll_by_code(self):
        self.course.enrollment_mode = Course.EnrollmentMode.CODE
        self.course.enroll_code = "CHEM2026"
        self.course.save()
        self.assertEqual(services.enroll_by_code(self.s1, " chem2026 ").course, self.course)
        with self.assertRaises(services.EnrollmentError):
            services.enroll_by_code(self.s2, "WRONG")

    def test_courses_for_by_role(self):
        services.assign_group(self.course, self.group)
        other = make_course()
        self.assertEqual(list(selectors.courses_for(self.s1)), [self.course])
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        self.course.course_teachers.create(teacher=teacher)
        self.assertEqual(list(selectors.courses_for(teacher)), [self.course])
        admin = User.objects.create_superuser("root", "root@example.kz", "x")
        self.assertEqual(set(selectors.courses_for(admin)), {self.course, other})


@override_settings(ALLOWED_HOSTS=["testserver"])
class CoursePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", topics=[1], verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")
        cls.student = make_student("s1", group=make_group())

    def test_seed_builds_topic_one_from_the_content(self):
        topic = Topic.objects.get(module__course=self.course, number=1)
        kinds = list(topic.stages.order_by("order").values_list("kind", flat=True))
        self.assertEqual(kinds, ["theory", "video", "lab", "practice", "practice", "practice", "practice", "test"])
        self.assertEqual(topic.stages.get(kind="lab").lab_content.lab_key, "t01")
        self.assertIn("<h2>1. Сутегіне жалпы сипаттама</h2>", topic.stages.get(kind="theory").theory_content.body)
        self.assertEqual(topic.stages.get(kind="test").test_content.quiz.questions.count(), 10)
        call_command("seed_course", topics=[1], verbosity=0)  # idempotent
        self.assertEqual(Stage.objects.filter(topic=topic).count(), 8)

    def test_replace_keeps_attempted_quizzes_and_stage_kinds(self):
        topic = Topic.objects.get(module__course=self.course, number=1)
        test_stage = topic.stages.get(kind="test")
        quiz = test_stage.test_content.quiz
        first = quiz.questions.order_by("order").first()
        attempt = QuizAttempt.objects.create(user=self.student, quiz=quiz, attempt_no=1, question_ids=[first.pk])
        theory = topic.stages.get(kind="theory").theory_content
        theory.body = "<p>edited</p>"
        theory.save()
        call_command("seed_course", topics=[1], verbosity=0)  # a plain run fills blanks only
        theory.refresh_from_db()
        self.assertEqual(theory.body, "<p>edited</p>")
        call_command("seed_course", replace=True, topics=[1], verbosity=0)
        theory.refresh_from_db()
        self.assertIn("Сутегіне жалпы сипаттама", theory.body)
        self.assertTrue(quiz.questions.filter(pk=first.pk).exists())  # attempted: never rewritten
        self.assertEqual(attempt.quiz_id, quiz.pk)
        test_stage.refresh_from_db()
        self.assertEqual((test_stage.kind, test_stage.order), ("test", 8))


class SanitizeTests(TestCase):
    def test_keeps_chemistry_markup_and_strips_scripts(self):
        html = '<h2 style="color:red">H<sub>2</sub>O</h2><a href="javascript:x">x</a><table><tr><td>1</td></tr></table>'
        cleaned = clean_html(html)
        self.assertIn("<h2>H<sub>2</sub>O</h2>", cleaned)
        self.assertNotIn("javascript", cleaned)
        self.assertNotIn("style", cleaned)
        self.assertIn("<td>1</td>", cleaned)


class CKEditorUploadTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def image(self):
        buf = BytesIO()
        Image.new("RGB", (4, 4), "white").save(buf, "PNG")
        return SimpleUploadedFile("pic.png", buf.getvalue(), content_type="image/png")

    def test_only_teachers_and_admins_upload(self):
        url = reverse("ckeditor_upload")
        with self.settings(MEDIA_ROOT=__import__("pathlib").Path(self.media)):
            self.assertEqual(self.client.post(url, {"upload": self.image()}).status_code, 403)
            self.client.force_login(make_student("s"))
            self.assertEqual(self.client.post(url, {"upload": self.image()}).status_code, 403)
            self.client.force_login(User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER))
            r = self.client.post(url, {"upload": self.image()})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertTrue(r.json()["url"].startswith("/media/ckeditor/"))


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", topics=[1], verbosity=0)
        cls.admin = User.objects.create_superuser("root", "root@example.kz", "x")

    def setUp(self):
        self.client.force_login(self.admin)

    def test_pages_render(self):
        topic = Topic.objects.get(number=1)
        for stage in topic.stages.all():
            self.assertEqual(self.client.get(reverse("admin:courses_stage_change", args=[stage.pk])).status_code, 200)
        for name in ("course", "module", "topic", "stage", "enrollment", "coursegroup", "theorycontent"):
            self.assertEqual(self.client.get(reverse(f"admin:courses_{name}_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:courses_topic_change", args=[topic.pk])).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("admin:courses_course_change", args=[topic.module.course_id])).status_code, 200
        )

    def test_group_inline_enrols_students(self):
        group = make_group()
        make_student("s1", group=group)
        course_group = CourseGroup.objects.create(course=Course.objects.get(), group=group)
        self.client.post(
            reverse("admin:courses_coursegroup_changelist"),
            {"action": "sync_enrollments", "_selected_action": [course_group.pk]},
        )
        self.assertEqual(Enrollment.objects.count(), 1)
