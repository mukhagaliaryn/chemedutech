from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class University(TimeStampedModel):
    name = models.CharField(_("name"), max_length=255, unique=True)
    short_name = models.CharField(_("short name"), max_length=64, blank=True)
    city = models.CharField(_("city"), max_length=128, blank=True)
    logo = models.ImageField(_("logo"), upload_to="universities/", blank=True)
    is_active = models.BooleanField(_("active"), default=True, help_text=_("Shown in the sign-up form"))

    class Meta:
        ordering = ("name",)
        verbose_name = _("university")
        verbose_name_plural = _("universities")

    def __str__(self):
        return self.short_name or self.name


class Faculty(TimeStampedModel):
    university = models.ForeignKey(
        University, on_delete=models.PROTECT, related_name="faculties", verbose_name=_("university")
    )
    name = models.CharField(_("name"), max_length=255)
    short_name = models.CharField(_("short name"), max_length=64, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("faculty")
        verbose_name_plural = _("faculties")
        constraints = [models.UniqueConstraint(fields=("university", "name"), name="faculty_unique_name")]

    def __str__(self):
        return self.short_name or self.name


class Department(TimeStampedModel):
    """Кафедра."""

    faculty = models.ForeignKey(
        Faculty, on_delete=models.PROTECT, related_name="departments", verbose_name=_("faculty")
    )
    name = models.CharField(_("name"), max_length=255)
    short_name = models.CharField(_("short name"), max_length=64, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("department")
        verbose_name_plural = _("departments")
        constraints = [models.UniqueConstraint(fields=("faculty", "name"), name="department_unique_name")]

    def __str__(self):
        return self.short_name or self.name


class Specialty(TimeStampedModel):
    """Educational programme, e.g. 6B01501 «Химия»."""

    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="specialties", verbose_name=_("department")
    )
    code = models.CharField(_("code"), max_length=16, help_text=_("e.g. 6B01501"))
    name = models.CharField(_("name"), max_length=255)

    class Meta:
        ordering = ("code",)
        verbose_name = _("specialty")
        verbose_name_plural = _("specialties")
        constraints = [models.UniqueConstraint(fields=("department", "code"), name="specialty_unique_code")]

    def __str__(self):
        return f"{self.code} {self.name}"
