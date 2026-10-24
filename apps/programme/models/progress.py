from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.organizations.models import ResearchCohort

PERCENT = {"max_digits": 5, "decimal_places": 2}


class ProgrammeEnrollment(TimeStampedModel):
    """A student in the programme. Made for every student of the programme's course; the research group
    is copied from the course enrolment and kept fixed (research data)."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="programme_enrollments",
        verbose_name=_("student"),
    )
    programme = models.ForeignKey(
        "programme.Programme", on_delete=models.PROTECT, related_name="enrollments", verbose_name=_("programme")
    )
    group = models.ForeignKey(
        "organizations.AcademicGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("group"),
    )
    research_cohort = models.CharField(_("research group"), max_length=16, choices=ResearchCohort.choices, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("programme enrolment")
        verbose_name_plural = _("programme enrolments")
        constraints = [models.UniqueConstraint(fields=("student", "programme"), name="programme_enrollment_unique")]

    def __str__(self):
        return f"{self.student} · {self.programme}"


class SectionProgress(TimeStampedModel):
    """A student's state in one section. ``percent`` comes from the section kind's provider; the status is
    derived by programme.services.recalculate (passed stays passed even if the percent falls later)."""

    class Status(models.TextChoices):
        LOCKED = "locked", _("Locked")
        AVAILABLE = "available", _("Available")
        IN_PROGRESS = "in_progress", _("In progress")
        PASSED = "passed", _("Passed")

    enrollment = models.ForeignKey(
        ProgrammeEnrollment, on_delete=models.PROTECT, related_name="sections", verbose_name=_("enrolment")
    )
    section = models.ForeignKey(
        "programme.Section", on_delete=models.PROTECT, related_name="progress", verbose_name=_("section")
    )
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.LOCKED)
    percent = models.DecimalField(_("done, %"), default=0, **PERCENT)
    opened_at = models.DateTimeField(_("opened at"), null=True, blank=True)
    passed_at = models.DateTimeField(_("passed at"), null=True, blank=True)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("opened by"),
        help_text=_("A teacher who opened the section by hand"),
    )
    unlocked_at = models.DateTimeField(_("opened by hand at"), null=True, blank=True)

    class Meta:
        ordering = ("enrollment", "section__number")
        verbose_name = _("section progress")
        verbose_name_plural = _("section progress")
        constraints = [models.UniqueConstraint(fields=("enrollment", "section"), name="section_progress_unique")]

    def __str__(self):
        return f"{self.enrollment} · {self.section} · {self.get_status_display()}"

    @property
    def is_open(self):
        return self.status != self.Status.LOCKED


class SectionEvent(models.Model):
    """Audit trail of the sections (research data, never deleted)."""

    class Action(models.TextChoices):
        OPENED = "opened", _("Opened")
        PASSED = "passed", _("Passed")
        UNLOCKED = "unlocked", _("Opened by the teacher")
        PERCENT = "percent", _("Percent changed")

    enrollment = models.ForeignKey(
        ProgrammeEnrollment, on_delete=models.PROTECT, related_name="events", verbose_name=_("enrolment")
    )
    section = models.ForeignKey(
        "programme.Section", on_delete=models.PROTECT, related_name="events", verbose_name=_("section")
    )
    action = models.CharField(_("action"), max_length=16, choices=Action.choices)
    percent = models.DecimalField(_("done, %"), null=True, blank=True, **PERCENT)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("by"),
        help_text=_("Empty when it follows from the student's work"),
    )
    created_at = models.DateTimeField(_("at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = _("section event")
        verbose_name_plural = _("section events")

    def __str__(self):
        return f"{self.enrollment} · {self.section} · {self.get_action_display()}"
