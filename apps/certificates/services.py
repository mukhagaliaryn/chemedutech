"""Certificates (ARCHITECTURE §7): issued automatically when a course is passed; PDF by WeasyPrint with a QR code."""

import base64
import io
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.formats import date_format

from apps.feedback import services as feedback
from apps.progress.models import CourseResult

from .models import Certificate, CertificateTemplate

logger = logging.getLogger(__name__)
PREFIX = "CET"


def verification_url(certificate: Certificate) -> str:
    return settings.SITE_URL + reverse("certificates:verify", args=[certificate.verification_code])


def _next_number(year: int) -> str:
    last = (
        Certificate.objects.filter(number__startswith=f"{PREFIX}-{year}-")
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{PREFIX}-{year}-{seq:06d}"


def issue_for(enrollment) -> Certificate | None:
    """The certificate of a passed course (once per enrolment); None when the course is not passed or has none.

    Safe to call again: an existing certificate is returned as it is. The PDF is made in the background.
    """
    existing = Certificate.objects.filter(enrollment=enrollment).first()
    if existing is not None:
        return existing
    course = enrollment.course
    result = CourseResult.objects.filter(enrollment=enrollment).first()
    if not course.certificate_enabled or result is None or not result.passed or result.score_percent is None:
        return None
    now = timezone.now()
    for _attempt in range(5):  # two issues at the same moment may take the same number
        try:
            with transaction.atomic():
                certificate = Certificate.objects.create(
                    enrollment=enrollment,
                    number=_next_number(now.year),
                    issued_at=now,
                    holder_name=enrollment.student.full_name,
                    course_title=course.title,
                    score_percent=result.score_percent,
                    letter=result.letter,
                )
            break
        except IntegrityError:
            existing = Certificate.objects.filter(enrollment=enrollment).first()
            if existing is not None:
                return existing
    else:
        raise RuntimeError("Could not give the certificate a unique number")
    transaction.on_commit(lambda: _after_issue(certificate.pk))
    return certificate


def _after_issue(certificate_id: int) -> None:
    from .tasks import render_certificate_pdf

    certificate = Certificate.objects.select_related("enrollment__student").get(pk=certificate_id)
    feedback.notify(
        certificate.enrollment.student,
        feedback.Kind.CERTIFICATE,
        certificate.course_title,
        reverse("student:certificates"),
    )
    try:
        render_certificate_pdf.enqueue(certificate_id)
    except Exception:  # the PDF is also made on the first download
        logger.exception("Certificate %s: PDF task was not queued", certificate_id)


# --- PDF -----------------------------------------------------------------------------------------


def qr_data_uri(text: str) -> str:
    import qrcode

    image = qrcode.make(text, box_size=8, border=1)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


class _Missing(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def texts(certificate: Certificate, template: CertificateTemplate | None) -> dict:
    """Title and body with placeholders filled in (unknown placeholders stay as written)."""
    values = _Missing(
        full_name=certificate.holder_name,
        course=certificate.course_title,
        score=f"{certificate.score_percent:.1f}",
        letter=certificate.letter,
        date=date_format(timezone.localtime(certificate.issued_at), "d.m.Y"),
        number=certificate.number,
    )
    template = template or CertificateTemplate(course=certificate.enrollment.course)
    return {
        "title": template.title_text.format_map(values),
        "body": template.body_text.format_map(values),
    }


def render_html(certificate: Certificate) -> str:
    template = CertificateTemplate.objects.filter(course_id=certificate.enrollment.course_id).first()
    with translation.override(settings.LANGUAGE_CODE):  # the document is in Kazakh whoever downloads it
        return render_to_string(
            "certificates/pdf.html",
            {
                "certificate": certificate,
                "template": template,
                **texts(certificate, template),
                "verify_url": verification_url(certificate),
                "qr": qr_data_uri(verification_url(certificate)),
                "issued": date_format(timezone.localtime(certificate.issued_at), "d.m.Y"),
            },
        )


def render_pdf(certificate: Certificate) -> Certificate:
    """Make (or make again) the PDF file of a certificate."""
    from weasyprint import HTML

    html = render_html(certificate)
    data = HTML(string=html, base_url=str(settings.MEDIA_ROOT)).write_pdf()
    if certificate.pdf:
        certificate.pdf.delete(save=False)
    certificate.pdf.save(f"{certificate.number}.pdf", ContentFile(data), save=False)
    certificate.save(update_fields=["pdf", "updated_at"])
    return certificate
