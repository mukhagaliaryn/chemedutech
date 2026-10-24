from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ExpertReview(models.Model):
    """«Айгерім» — the intelligent pedagogical expert of section 8 (guide @S8 III, VI): an opinion on the student's
    independent lesson by six dimensions (or, after a trial, seven directions), a status and the direction checked.
    «Check again» compares with the previous opinion. Not final until the teacher confirms it (@S8, the last
    paragraph). Research data — kept."""

    class Kind(models.TextChoices):
        DRAFT = "draft", _("The lesson project")
        TRIAL = "trial", _("After the trial")

    class Status(models.TextChoices):
        OK = "ok", _("Fits")
        NEEDS_MORE = "needs_more", _("Needs more work")
        REVISE = "revise", _("Needs revising")

    # guide @S8 III — the six dimensions of the opinion on the project
    DIMENSIONS = (
        ("accuracy", _("Scientific accuracy")),
        ("fit", _("Pedagogical fit")),
        ("sequence", _("Methodical consistency")),
        ("cognition", _("The student's cognitive activity")),
        ("assessment", _("Quality of assessment")),
        ("authorship", _("Authorial feature")),
    )
    # guide @S8 VI — the seven directions of the expert analysis after a trial
    TRIAL_DIRECTIONS = (
        ("content", _("Correctness of the scientific content")),
        ("aim", _("Reaching the lesson aim")),
        ("time", _("Organising the time effectively")),
        ("tasks", _("Pedagogical grounding of the tasks")),
        ("feedback", _("The feedback given to the students' answers")),
        ("method", _("Carrying out the authorial method")),
        ("reflection", _("The student's professional reflection")),
    )

    lesson = models.ForeignKey(
        "pedagogy.Lesson", on_delete=models.PROTECT, related_name="expert_reviews", verbose_name=_("lesson")
    )
    trial = models.ForeignKey(
        "pedagogy.Trial", on_delete=models.PROTECT, null=True, blank=True, related_name="expert_reviews",
        verbose_name=_("trial"),
    )  # fmt: skip
    kind = models.CharField(_("kind"), max_length=8, choices=Kind.choices, default=Kind.DRAFT)
    snapshot = models.JSONField(_("the lesson as reviewed"), default=dict)
    items = models.JSONField(
        _("opinion by dimension"), default=dict, help_text=_('{"accuracy": {"status", "text"}, …}')
    )
    status = models.CharField(_("status"), max_length=12, choices=Status.choices)
    focus = models.CharField(_("direction checked"), max_length=255, blank=True)
    summary = models.TextField(_("expert conclusion"), blank=True)
    strengths = models.JSONField(_("strengths"), default=list, blank=True)
    suggestions = models.JSONField(_("suggestions"), default=list, blank=True)
    change = models.TextField(_("what has changed since the previous opinion"), blank=True)
    previous = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("compared with")
    )
    message_id = models.PositiveIntegerField(_("AI message"), null=True, blank=True)
    teacher_status = models.CharField(
        _("status confirmed by the teacher"), max_length=12, choices=Status.choices, blank=True
    )
    teacher_comment = models.TextField(_("teacher's comment"), blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name=_("confirmed by"),
    )  # fmt: skip
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = _("«Айгерім» opinion")
        verbose_name_plural = _("«Айгерім» opinions")

    def __str__(self):
        return f"{self.lesson} · {self.get_status_display()}"

    @property
    def final_status(self) -> str:
        """The teacher's status once confirmed; until then the expert's opinion is not final."""
        return self.teacher_status or ""
