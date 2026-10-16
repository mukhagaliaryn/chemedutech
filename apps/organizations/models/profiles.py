from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class StudentProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile", verbose_name=_("user")
    )
    group = models.ForeignKey(
        "organizations.AcademicGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="students",
        verbose_name=_("group"),
    )
    student_id = models.CharField(_("student ID"), max_length=32, blank=True, help_text=_("Record book number"))
    study_year = models.PositiveSmallIntegerField(
        _("year of study"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    research_consent = models.BooleanField(
        _("research consent"),
        default=False,
        help_text=_("Agreed that anonymised learning data may be used in pedagogical research"),
    )
    research_consent_at = models.DateTimeField(_("consent given at"), null=True, blank=True)

    class Meta:
        verbose_name = _("student profile")
        verbose_name_plural = _("student profiles")

    def __str__(self):
        return str(self.user)


class TeacherProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher_profile", verbose_name=_("user")
    )
    department = models.ForeignKey(
        "organizations.Department", on_delete=models.PROTECT, related_name="teachers", verbose_name=_("department")
    )
    position = models.CharField(_("position"), max_length=128, blank=True, help_text=_("e.g. Senior lecturer"))
    academic_degree = models.CharField(_("academic degree"), max_length=128, blank=True, help_text=_("e.g. PhD"))

    class Meta:
        verbose_name = _("teacher profile")
        verbose_name_plural = _("teacher profiles")

    def __str__(self):
        return str(self.user)
