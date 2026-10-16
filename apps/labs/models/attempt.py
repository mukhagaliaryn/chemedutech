from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class LabAttempt(models.Model):
    """One run of one experiment by one student — the unit of research data."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In progress")
        FINISHED = "finished", _("Finished")
        ANALYSED = "analysed", _("Analysis submitted")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lab_attempts", verbose_name=_("student")
    )
    lab_key = models.CharField(_("lab"), max_length=32)
    experiment_key = models.CharField(_("experiment"), max_length=32)
    cohort = models.CharField(_("research group"), max_length=16, blank=True, help_text=_("Snapshot at start"))
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)
    duration_s = models.PositiveIntegerField(_("duration, s"), null=True, blank=True)

    # process metrics (recomputed from the event log when the attempt finishes)
    order_errors = models.PositiveIntegerField(_("order errors"), default=0)
    safety_warnings = models.PositiveIntegerField(_("safety warnings"), default=0)
    wrong_items = models.PositiveIntegerField(_("wrong equipment or reagent"), default=0)
    wrong_choices = models.PositiveIntegerField(_("wrong choices"), default=0)
    hints_used = models.PositiveIntegerField(_("hints used"), default=0)
    step_times = models.JSONField(_("time per step, ms"), default=dict, blank=True)

    journal = models.JSONField(_("lab journal"), default=dict, blank=True)
    journal_correct = models.PositiveSmallIntegerField(_("journal: correct choices"), default=0)
    journal_total = models.PositiveSmallIntegerField(_("journal: choice fields"), default=0)
    analysis = models.JSONField(_("analysis answers"), default=dict, blank=True)
    analysis_correct = models.PositiveSmallIntegerField(_("analysis: correct"), default=0)
    analysis_total = models.PositiveSmallIntegerField(_("analysis: closed questions"), default=0)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("lab_key", "experiment_key", "cohort"))]
        verbose_name = _("lab attempt")
        verbose_name_plural = _("lab attempts")

    def __str__(self):
        return f"{self.user} · {self.lab_key}/{self.experiment_key} · {self.started_at:%Y-%m-%d %H:%M}"


class LabEvent(models.Model):
    """Fine-grained action log for the research layer."""

    class Type(models.TextChoices):
        START = "start", _("Start")
        ITEM_PLACED = "item_placed", _("Item placed")
        WRONG_ITEM = "wrong_item", _("Wrong item")
        COMMAND = "command", _("Command")
        STEP_DONE = "step_done", _("Step done")
        ORDER_ERROR = "order_error", _("Order error")
        SAFETY_WARNING = "safety_warning", _("Safety warning")
        WRONG_CHOICE = "wrong_choice", _("Wrong choice")
        HINT = "hint", _("Hint")
        JOURNAL_SAVED = "journal_saved", _("Journal saved")
        FINISH = "finish", _("Finish")
        RESTART = "restart", _("Restart")

    attempt = models.ForeignKey(LabAttempt, on_delete=models.CASCADE, related_name="events", verbose_name=_("attempt"))
    seq = models.PositiveIntegerField(_("sequence"))
    t_ms = models.PositiveIntegerField(_("time from start, ms"))
    type = models.CharField(_("type"), max_length=24, choices=Type.choices)
    step = models.CharField(_("step"), max_length=48, blank=True)
    payload = models.JSONField(_("payload"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("attempt", "seq")
        constraints = [models.UniqueConstraint(fields=("attempt", "seq"), name="uniq_event_seq")]
        verbose_name = _("lab event")
        verbose_name_plural = _("lab events")

    def __str__(self):
        return f"#{self.seq} {self.type} {self.step}"
