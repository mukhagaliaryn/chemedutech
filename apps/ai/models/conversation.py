from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Mode(models.TextChoices):
    """The roles of the AI in the ICPAI programme (docs/icpai/SPEC.md §0): it helps, checks or judges — it never
    writes a lesson stage, a reflection or a portfolio for the student."""

    ASSISTANT = "assistant", _("AI assistant")
    STUDENT_SIM = "student_sim", _("AI student")
    CHECKER = "checker", _("AI checker")
    EXPERT = "expert", _("«Айгерім» expert")


class AIConversation(models.Model):
    """One thread with the AI about one thing (a section, a lesson stage, a trial …). Research data — kept."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ai_conversations", verbose_name=_("user")
    )
    mode = models.CharField(_("mode"), max_length=16, choices=Mode.choices)
    context_type = models.CharField(_("about"), max_length=32, help_text=_("section, lesson_stage, trial …"))
    context_id = models.PositiveIntegerField(_("object id"))
    prompt_version = models.CharField(_("prompt version"), max_length=32)
    model = models.CharField(_("model"), max_length=64)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("AI conversation")
        verbose_name_plural = _("AI conversations")
        indexes = [models.Index(fields=("user", "mode", "context_type", "context_id"))]

    def __str__(self):
        return f"{self.user} · {self.get_mode_display()} · {self.context_type} {self.context_id}"


class AIMessage(models.Model):
    """A turn of the conversation: what the student sent and what the AI answered (with its cost). Kept."""

    class Role(models.TextChoices):
        USER = "user", _("Student")
        ASSISTANT = "assistant", _("AI")

    conversation = models.ForeignKey(
        AIConversation, on_delete=models.PROTECT, related_name="messages", verbose_name=_("conversation")
    )
    role = models.CharField(_("role"), max_length=16, choices=Role.choices)
    intent = models.CharField(_("request"), max_length=32, blank=True, help_text=_("A quick action, empty for chat"))
    content = models.TextField(_("text"), blank=True)
    structured = models.JSONField(_("structured answer"), default=dict, blank=True)
    input_tokens = models.PositiveIntegerField(_("input tokens"), default=0)
    output_tokens = models.PositiveIntegerField(_("output tokens"), default=0)
    latency_ms = models.PositiveIntegerField(_("latency, ms"), default=0)
    error = models.TextField(_("error"), blank=True)
    created_at = models.DateTimeField(_("at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = _("AI message")
        verbose_name_plural = _("AI messages")

    def __str__(self):
        return f"{self.conversation} · {self.get_role_display()}"


class AIUsage(models.Model):
    """Requests and tokens per student per day — for the daily limit."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_usage", verbose_name=_("user")
    )
    date = models.DateField(_("date"))
    requests = models.PositiveIntegerField(_("requests"), default=0)
    input_tokens = models.PositiveIntegerField(_("input tokens"), default=0)
    output_tokens = models.PositiveIntegerField(_("output tokens"), default=0)

    class Meta:
        ordering = ("-date",)
        verbose_name = _("AI usage")
        verbose_name_plural = _("AI usage")
        constraints = [models.UniqueConstraint(fields=("user", "date"), name="ai_usage_unique")]

    def __str__(self):
        return f"{self.user} · {self.date} · {self.requests}"
