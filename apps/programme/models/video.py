import re

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class SectionVideo(TimeStampedModel):
    """The one video of a section of kind «video» (guide @S3 «ЖИ ВИДЕО ОРНАЛАСАДЫ»): a YouTube link set in the admin.
    Until it is added the section counts as done, so the video's delay does not stop the students (D72)."""

    section = models.OneToOneField(
        "programme.Section", on_delete=models.CASCADE, related_name="video", verbose_name=_("section")
    )
    url = models.URLField(_("YouTube link"), blank=True, help_text=_("Empty — the video is being prepared"))

    class Meta:
        verbose_name = _("section video")
        verbose_name_plural = _("section videos")

    def __str__(self):
        return str(self.section)

    @property
    def youtube_id(self) -> str:
        m = re.search(
            r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/))([\w-]{11})", self.url
        )
        return m.group(1) if m else ""


class VideoWatch(models.Model):
    """How much of a section's video a student has watched (the largest share reported; skipped parts are not
    counted by the player)."""

    enrollment = models.ForeignKey(
        "programme.ProgrammeEnrollment",
        on_delete=models.PROTECT,
        related_name="video_watches",
        verbose_name=_("enrolment"),
    )
    section = models.ForeignKey(
        "programme.Section", on_delete=models.PROTECT, related_name="video_watches", verbose_name=_("section")
    )
    percent = models.PositiveSmallIntegerField(_("watched, %"), default=0)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("video watching")
        verbose_name_plural = _("video watching")
        constraints = [models.UniqueConstraint(fields=("enrollment", "section"), name="video_watch_unique")]

    def __str__(self):
        return f"{self.enrollment} · {self.section} · {self.percent}%"
