import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

# No 0/O, 1/I/L — codes are read aloud and typed from a projector.
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 8


def generate_join_code():
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


class ResearchCohort(models.TextChoices):
    """Pedagogical experiment group. Snapshotted into enrollments and lab attempts."""

    NONE = "", _("Not assigned")
    CONTROL = "control", _("Control group")
    EXPERIMENTAL = "experimental", _("Experimental group")


class AcademicGroup(TimeStampedModel):
    """Study group, e.g. «Хим-23-1»."""

    department = models.ForeignKey(
        "organizations.Department", on_delete=models.PROTECT, related_name="groups", verbose_name=_("department")
    )
    specialty = models.ForeignKey(
        "organizations.Specialty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="groups",
        verbose_name=_("specialty"),
    )
    name = models.CharField(_("name"), max_length=64, help_text=_("e.g. Chem-23-1"))
    admission_year = models.PositiveSmallIntegerField(
        _("admission year"), validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    study_year = models.PositiveSmallIntegerField(
        _("year of study"), default=1, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    curator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"role": "teacher"},
        related_name="curated_groups",
        verbose_name=_("curator"),
    )
    join_code = models.CharField(
        _("join code"),
        max_length=JOIN_CODE_LENGTH,
        unique=True,
        default=generate_join_code,
        help_text=_("Students can enter it when signing up"),
    )
    research_cohort = models.CharField(
        _("research group"), max_length=16, choices=ResearchCohort.choices, blank=True, default=ResearchCohort.NONE
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ("-admission_year", "name")
        verbose_name = _("academic group")
        verbose_name_plural = _("academic groups")
        constraints = [models.UniqueConstraint(fields=("department", "name"), name="group_unique_name")]

    def __str__(self):
        return self.name
