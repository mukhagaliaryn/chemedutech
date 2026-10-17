from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class StudyDay(TimeStampedModel):
    """Seconds a student spent on stage pages on one local day (fed by the 30 s «ping» of the stage page).

    Only for the dashboard activity chart and streaks; the research log stays in LabEvent / QuizAttempt.
    """

    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="study_days", verbose_name=_("enrolment")
    )
    date = models.DateField(_("date"))
    seconds = models.PositiveIntegerField(_("seconds"), default=0)

    class Meta:
        verbose_name = _("study day")
        verbose_name_plural = _("study days")
        ordering = ("-date",)
        constraints = [models.UniqueConstraint(fields=("enrollment", "date"), name="study_day_unique")]

    def __str__(self):
        return f"{self.enrollment} · {self.date} · {self.seconds} s"
