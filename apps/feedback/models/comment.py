from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class Comment(models.Model):
    """Teacher ↔ student conversation about one piece of work (ARCHITECTURE §6).

    ``target`` is a PracticeSubmission, LabAttempt or QuizAttempt; threads are one level deep
    (a reply points at the first comment). Kept for the dissertation — never deleted.
    """

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comments", verbose_name=_("author")
    )
    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="comments", verbose_name=_("enrolment")
    )
    stage = models.ForeignKey(
        "courses.Stage", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("stage")
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, verbose_name=_("work type"))
    object_id = models.PositiveBigIntegerField(_("work id"))
    target = GenericForeignKey("content_type", "object_id")
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="replies", verbose_name=_("reply to")
    )
    body = models.TextField(_("text"))
    is_read = models.BooleanField(_("read"), default=False, help_text=_("Read by the other side"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = _("comment")
        verbose_name_plural = _("comments")
        indexes = [models.Index(fields=("content_type", "object_id"))]

    def __str__(self):
        return f"{self.author} · {self.body[:40]}"
