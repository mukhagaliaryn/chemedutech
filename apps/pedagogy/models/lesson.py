from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Lesson(TimeStampedModel):
    """A student's own lesson (docs/icpai/SPEC.md §2.3). Section 4: a copy of an authorial template the student
    redesigns stage by stage with the AI assistant (guide @S4-AI), then assembles and tries out (@S4-ASSEMBLE).
    Research data — never deleted."""

    class Kind(models.TextChoices):
        TEMPLATE_COPY = "template_copy", _("Template copy")
        RESEARCH_PRACTICE = "research_practice", _("Digital research practice")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ASSEMBLED = "assembled", _("Assembled")
        TESTED = "tested", _("Tried out")
        FINAL = "final", _("Final version")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lessons", verbose_name=_("student")
    )
    kind = models.CharField(_("kind"), max_length=24, choices=Kind.choices, default=Kind.TEMPLATE_COPY)
    frame = models.CharField(_("frame"), max_length=24, default="template", help_text=_("pedagogy/frames.py"))
    source_template = models.ForeignKey(
        "pedagogy.LessonTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name=_("template"),
    )
    source_lesson = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="derived",
        verbose_name=_("source lesson"),
        help_text=_("Section 5: the student's section 4 lesson, shown beside the sheet (not copied)"),
    )
    title = models.CharField(_("title"), max_length=255)
    topic = models.CharField(_("lesson topic"), max_length=255, blank=True)
    grade = models.CharField(_("grade"), max_length=32, blank=True)
    duration_min = models.PositiveSmallIntegerField(_("duration, min"), default=45)
    aim = models.TextField(_("lesson aim"), blank=True)
    outcomes = models.TextField(_("expected results"), blank=True, help_text=_("HTML"))
    method = models.TextField(_("authorial method used"), blank=True)
    digital_tools = models.TextField(_("digital tools used"), blank=True)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = _("lesson")
        verbose_name_plural = _("lessons")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "source_template"),
                condition=Q(kind="template_copy"),
                name="lesson_one_copy_per_template",
            ),
            models.UniqueConstraint(
                fields=("owner", "source_template"),
                condition=Q(kind="research_practice"),
                name="lesson_one_practice_per_template",
            ),
        ]

    def __str__(self):
        return f"{self.owner} · {self.title}"


class LessonStage(models.Model):
    """A stage of a student's lesson. ``fields`` — the frame's fields as HTML ({key: html}); ``original`` — what was
    copied from the template. «Clear the content» (guide @S4-AI) empties ``fields`` and keeps ``original``."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="stages", verbose_name=_("lesson"))
    order = models.PositiveSmallIntegerField(_("number"))
    key = models.CharField(_("frame stage"), max_length=32, blank=True, help_text=_("pedagogy/frames.py"))
    title = models.CharField(_("title"), max_length=255)
    minutes = models.PositiveSmallIntegerField(_("minutes"))
    fields = models.JSONField(_("content"), default=dict, blank=True)
    original = models.JSONField(_("original content"), default=dict, blank=True)
    cleared_at = models.DateTimeField(_("cleared at"), null=True, blank=True)
    edited = models.BooleanField(_("redesigned"), default=False, help_text=_("The student wrote this stage anew"))
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ("lesson", "order")
        verbose_name = _("lesson stage")
        verbose_name_plural = _("lesson stages")
        constraints = [models.UniqueConstraint(fields=("lesson", "order"), name="lesson_stage_order_unique")]

    def __str__(self):
        return f"{self.order}. {self.title}"

    @property
    def cleared(self) -> bool:
        return self.cleared_at is not None


class LessonVersion(models.Model):
    """A frozen copy of the lesson made by «Assemble the lesson» / «Assemble the final version». Never changed."""

    class Reason(models.TextChoices):
        ASSEMBLE = "assemble", _("Assembled")
        TRIAL = "trial", _("Tried out")
        FINAL = "final", _("Final version")

    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="versions", verbose_name=_("lesson"))
    number = models.PositiveSmallIntegerField(_("number"))
    reason = models.CharField(_("reason"), max_length=16, choices=Reason.choices)
    snapshot = models.JSONField(_("snapshot"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ("lesson", "number")
        verbose_name = _("lesson version")
        verbose_name_plural = _("lesson versions")
        constraints = [models.UniqueConstraint(fields=("lesson", "number"), name="lesson_version_number_unique")]

    def __str__(self):
        return f"{self.lesson} · v{self.number}"


class LessonEvent(models.Model):
    """The research log of the lesson design: what the student did and when (append-only, never deleted)."""

    class Action(models.TextChoices):
        CREATED = "created", _("Lesson created")
        CLEARED = "cleared", _("Stage content cleared")
        RESTORED = "restored", _("Original content restored")
        SAVED = "saved", _("Stage saved")
        AI_INSERTED = "ai_inserted", _("AI suggestion added to the editor")
        DETAILS_SAVED = "details_saved", _("Lesson details saved")
        ASSEMBLED = "assembled", _("Lesson assembled")
        FINAL = "final", _("Final version assembled")

    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="events", verbose_name=_("lesson"))
    stage = models.ForeignKey(
        LessonStage, on_delete=models.PROTECT, null=True, blank=True, related_name="events", verbose_name=_("stage")
    )
    action = models.CharField(_("action"), max_length=16, choices=Action.choices)
    data = models.JSONField(_("data"), default=dict, blank=True)
    created_at = models.DateTimeField(_("at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = _("lesson event")
        verbose_name_plural = _("lesson events")

    def __str__(self):
        return f"{self.lesson} · {self.get_action_display()}"
