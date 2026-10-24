from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """A short «something happened» line for one user (ARCHITECTURE §6).

    ``title`` names the subject (a stage, a work — course content is in Kazakh); the sentence around it
    comes from ``kind`` and is translated when shown, so a language switch changes old notifications too.
    """

    class Kind(models.TextChoices):
        GRADED = "graded", _("Your work is graded")
        RETURNED = "returned", _("The teacher returned your work")
        COMMENT = "comment", _("New comment")
        UNLOCKED = "unlocked", _("The teacher opened a stage for you")
        CERTIFICATE = "certificate", _("Certificate issued")
        SECTION = "section", _("A programme section is open")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", verbose_name=_("user")
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    title = models.CharField(_("subject"), max_length=255, blank=True)
    url = models.CharField(_("link"), max_length=500, blank=True)
    is_read = models.BooleanField(_("read"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        indexes = [models.Index(fields=("user", "is_read"))]

    def __str__(self):
        return f"{self.user} · {self.get_kind_display()}"
