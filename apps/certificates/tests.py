"""STEP-13: certificates — automatic issue, numbering, PDF with a QR code, verification page, access."""

import shutil
import tempfile
import uuid
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import Course, CourseTeacher, Stage
from apps.courses.services import enroll
from apps.feedback.models import Notification
from apps.organizations.testing import make_student
from apps.progress import services as progress
from apps.progress.models import CourseResult

from . import services
from .models import Certificate, CertificateTemplate

MEDIA = tempfile.mkdtemp(prefix="chem-test-media-")


@override_settings(ALLOWED_HOSTS=["testserver"], MEDIA_ROOT=MEDIA, SITE_URL="https://chem.example.kz")
class CertificateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_course", verbosity=0)
        cls.course = Course.objects.get(slug="chemistry")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.student = make_student("s1", first_name="Айгерім", last_name="Сапарова")
        self.enrollment = enroll(self.student, self.course, "admin")
        progress.recalculate(self.enrollment)

    def pass_course(self, enrollment, score="91.5"):
        CourseResult.objects.filter(enrollment=enrollment).update(
            passed=True, score_percent=Decimal(score), letter="A-"
        )

    def test_issue_numbers_and_notify(self):
        self.pass_course(self.enrollment)
        with self.captureOnCommitCallbacks(execute=True):
            cert = services.issue_for(self.enrollment)
        year = cert.issued_at.year
        self.assertEqual(cert.number, f"CET-{year}-000001")
        self.assertEqual(
            (cert.holder_name, cert.score_percent, cert.letter), ("Сапарова Айгерім", Decimal("91.50"), "A-")
        )
        self.assertEqual(services.issue_for(self.enrollment), cert)  # once per enrolment
        note = Notification.objects.get(user=self.student, kind="certificate")
        self.assertEqual(note.url, reverse("student:certificates"))
        cert.refresh_from_db()
        self.assertTrue(cert.pdf.read(4) == b"%PDF")  # rendered by the (immediate) background task
        other = enroll(make_student("s2"), self.course, "admin")
        progress.recalculate(other)
        self.pass_course(other)
        self.assertEqual(services.issue_for(other).number, f"CET-{year}-000002")

    def test_not_issued(self):
        self.assertIsNone(services.issue_for(self.enrollment))
        self.pass_course(self.enrollment)
        Course.objects.filter(pk=self.course.pk).update(certificate_enabled=False)
        self.enrollment.refresh_from_db()
        self.assertIsNone(services.issue_for(self.enrollment))

    def test_passing_the_course_issues_it(self):
        """Seed: only topic 1 is published, so passing its stages passes the course."""
        stages = Stage.objects.filter(topic__module__course=self.course, topic__is_published=True).order_by(
            "topic__number", "order"
        )
        with self.captureOnCommitCallbacks(execute=True):
            for stage in stages:
                progress.complete_stage(self.enrollment, stage, 95, passed=True)
        result = CourseResult.objects.get(enrollment=self.enrollment)
        self.assertTrue(result.passed)
        self.assertTrue(Certificate.objects.filter(enrollment=self.enrollment).exists())

    def test_texts_and_qr(self):
        self.pass_course(self.enrollment)
        cert = services.issue_for(self.enrollment)
        template = CertificateTemplate(
            course=self.course, title_text="СЕРТИФИКАТ", body_text="{course} · {score} · {unknown}"
        )
        texts = services.texts(cert, template)
        self.assertEqual(texts["body"], f"{self.course.title} · 91.5 · {{unknown}}")
        url = services.verification_url(cert)
        self.assertTrue(url.startswith("https://chem.example.kz/certificates/verify/"))
        self.assertTrue(services.qr_data_uri(url).startswith("data:image/png;base64,"))
        html = services.render_html(cert)
        self.assertIn("Сапарова Айгерім", html)
        self.assertIn(cert.number, html)

    def test_verify_page(self):
        self.pass_course(self.enrollment)
        cert = services.issue_for(self.enrollment)
        r = self.client.get(reverse("certificates:verify", args=[cert.verification_code]))
        self.assertContains(r, "Сапарова Айгерім")
        self.assertContains(r, cert.number)
        r = self.client.get(reverse("certificates:verify", args=[uuid.uuid4()]))
        self.assertEqual(r.status_code, 404)

    def test_pdf_access(self):
        self.pass_course(self.enrollment)
        cert = services.issue_for(self.enrollment)
        url = reverse("certificates:pdf", args=[cert.verification_code])
        self.assertEqual(self.client.get(url).status_code, 302)  # log in first
        self.client.force_login(self.student)
        r = self.client.get(url)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(r.streaming_content)[:4], b"%PDF")
        self.client.force_login(make_student("stranger"))
        self.assertEqual(self.client.get(url).status_code, 404)
        teacher = User.objects.create_user("t", "t@example.kz", "x", role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.course, teacher=teacher)
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_student_page(self):
        self.pass_course(self.enrollment)
        cert = services.issue_for(self.enrollment)
        self.client.force_login(self.student)
        r = self.client.get(reverse("student:certificates"))
        self.assertContains(r, reverse("certificates:pdf", args=[cert.verification_code]))
        self.assertContains(r, services.verification_url(cert))
