from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class SectionSchedule(TimeStampedModel):
    """The dates the teacher sets for a group in a section (guide @S8 IV — the deadlines of the independent lesson):
    the project's hand-in date and the trial date. The platform sends the notifications by them."""

    section = models.ForeignKey(
        "programme.Section", on_delete=models.CASCADE, related_name="schedules", verbose_name=_("section")
    )
    group = models.ForeignKey(
        "organizations.AcademicGroup",
        on_delete=models.CASCADE,
        related_name="section_schedules",
        verbose_name=_("group"),
    )
    hand_in_on = models.DateField(_("hand in the project by"), null=True, blank=True)
    trial_on = models.DateField(_("trial date"), null=True, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name=_("set by")
    )

    class Meta:
        verbose_name = _("section schedule")
        verbose_name_plural = _("section schedules")
        constraints = [models.UniqueConstraint(fields=("section", "group"), name="section_schedule_unique")]

    def __str__(self):
        return f"{self.section} · {self.group}"
