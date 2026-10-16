from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.organizations.models import ResearchCohort


class Enrollment(TimeStampedModel):
    """A student in a course — the anchor of progress, grades and research data."""

    class Source(models.TextChoices):
        SELF = "self", _("Self-enrolled")
        GROUP = "group", _("Through the group")
        CODE = "code", _("By course code")
        ADMIN = "admin", _("Added by the administrator")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        COMPLETED = "completed", _("Completed")
        DROPPED = "dropped", _("Dropped")

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="enrollments", verbose_name=_("student")
    )
    course = models.ForeignKey(
        "courses.Course", on_delete=models.PROTECT, related_name="enrollments", verbose_name=_("course")
    )
    source = models.CharField(_("source"), max_length=16, choices=Source.choices)
    group = models.ForeignKey(
        "organizations.AcademicGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
        verbose_name=_("group"),
        help_text=_("The student's group at enrolment"),
    )
    research_cohort = models.CharField(
        _("research group"),
        max_length=16,
        choices=ResearchCohort.choices,
        blank=True,
        help_text=_("Copied from the group at enrolment and kept fixed"),
    )
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.ACTIVE)
    enrolled_at = models.DateTimeField(_("enrolled at"), auto_now_add=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        ordering = ("-enrolled_at",)
        verbose_name = _("enrolment")
        verbose_name_plural = _("enrolments")
        constraints = [models.UniqueConstraint(fields=("student", "course"), name="enrollment_unique")]

    def __str__(self):
        return f"{self.student} · {self.course}"
