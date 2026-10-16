import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class CertificateTemplate(TimeStampedModel):
    """The look and wording of one course's certificate (ARCHITECTURE §7). Texts are in Kazakh (course content)."""

    course = models.OneToOneField(
        "courses.Course", on_delete=models.CASCADE, related_name="certificate_template", verbose_name=_("course")
    )
    background = models.ImageField(
        _("background"), upload_to="certificates/backgrounds/", blank=True, help_text=_("A4 landscape, 297 × 210 mm")
    )
    title_text = models.CharField(_("title"), max_length=200, default="СЕРТИФИКАТ")
    body_text = models.TextField(
        _("text"),
        default="«{course}» курсын {score} ұпаймен ({letter}) сәтті аяқтады.",
        help_text=_(
            "Shown under the holder's name. Placeholders: {full_name}, {course}, {score}, {letter}, {date}, {number}"
        ),
    )
    signatory_name = models.CharField(_("signatory"), max_length=200, blank=True)
    signatory_position = models.CharField(_("signatory's position"), max_length=200, blank=True)
    signature_image = models.ImageField(_("signature"), upload_to="certificates/signatures/", blank=True)

    class Meta:
        verbose_name = _("certificate template")
        verbose_name_plural = _("certificate templates")

    def __str__(self):
        return str(self.course)


class Certificate(TimeStampedModel):
    """Issued once per enrolment when the course is passed. The holder's name and the course title are
    copied at issue so the document stays the same if they are renamed later."""

    enrollment = models.OneToOneField(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="certificate", verbose_name=_("enrolment")
    )
    number = models.CharField(_("number"), max_length=32, unique=True, help_text=_("e.g. CET-2026-000123"))
    issued_at = models.DateTimeField(_("issued at"))
    holder_name = models.CharField(_("holder"), max_length=300)
    course_title = models.CharField(_("course"), max_length=255)
    score_percent = models.DecimalField(_("score, %"), max_digits=5, decimal_places=2)
    letter = models.CharField(_("letter grade"), max_length=2)
    pdf = models.FileField(_("PDF"), upload_to="certificates/pdf/", blank=True)
    verification_code = models.UUIDField(_("verification code"), default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        ordering = ("-issued_at",)
        verbose_name = _("certificate")
        verbose_name_plural = _("certificates")

    def __str__(self):
        return self.number
