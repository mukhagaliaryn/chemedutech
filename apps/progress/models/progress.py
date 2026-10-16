from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

PERCENT = {"max_digits": 5, "decimal_places": 2, "null": True, "blank": True}


class StageProgress(TimeStampedModel):
    """A student's state on one stage. Facts (in progress, awaiting check, passed) come from services;
    locked/available is derived by progress.services.recalculate from the course order."""

    class Status(models.TextChoices):
        LOCKED = "locked", _("Locked")
        AVAILABLE = "available", _("Available")
        IN_PROGRESS = "in_progress", _("In progress")
        AWAITING_CHECK = "awaiting_check", _("Awaiting check")
        PASSED = "passed", _("Passed")

    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="stage_progress", verbose_name=_("enrolment")
    )
    stage = models.ForeignKey(
        "courses.Stage", on_delete=models.CASCADE, related_name="progress", verbose_name=_("stage")
    )
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.LOCKED)
    score_percent = models.DecimalField(_("score, %"), **PERCENT)
    needs_attention = models.BooleanField(
        _("needs the teacher's attention"), default=False, help_text=_("Passed only because the attempts ran out")
    )
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    time_spent_s = models.PositiveIntegerField(_("time spent, s"), default=0)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("opened by"),
        help_text=_("A teacher who opened the stage by hand"),
    )
    unlocked_at = models.DateTimeField(_("opened at"), null=True, blank=True)

    class Meta:
        verbose_name = _("stage progress")
        verbose_name_plural = _("stage progress")
        constraints = [models.UniqueConstraint(fields=("enrollment", "stage"), name="stage_progress_unique")]

    def __str__(self):
        return f"{self.enrollment} · {self.stage} · {self.get_status_display()}"

    @property
    def is_open(self):
        return self.status != self.Status.LOCKED

    @property
    def counts_as_done(self):
        """Done for the order of stages: the next stage may open (awaiting check included, decision D3)."""
        return self.status in (self.Status.PASSED, self.Status.AWAITING_CHECK)


class TopicResult(TimeStampedModel):
    class Status(models.TextChoices):
        LOCKED = "locked", _("Locked")
        AVAILABLE = "available", _("Available")
        IN_PROGRESS = "in_progress", _("In progress")
        COMPLETED = "completed", _("Completed")

    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="topic_results", verbose_name=_("enrolment")
    )
    topic = models.ForeignKey(
        "courses.Topic", on_delete=models.CASCADE, related_name="results", verbose_name=_("topic")
    )
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.LOCKED)
    score_percent = models.DecimalField(
        _("score, %"), help_text=_("Weighted over the required stages; missing stages count as 0"), **PERCENT
    )
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("topic result")
        verbose_name_plural = _("topic results")
        constraints = [models.UniqueConstraint(fields=("enrollment", "topic"), name="topic_result_unique")]

    def __str__(self):
        return f"{self.enrollment} · {self.topic}"


class ModuleResult(TimeStampedModel):
    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="module_results", verbose_name=_("enrolment")
    )
    module = models.ForeignKey(
        "courses.Module", on_delete=models.CASCADE, related_name="results", verbose_name=_("module")
    )
    current_percent = models.DecimalField(_("current score, %"), help_text=_("Completed topics only"), **PERCENT)
    score_percent = models.DecimalField(_("final score, %"), help_text=_("When every topic is completed"), **PERCENT)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("module result")
        verbose_name_plural = _("module results")
        constraints = [models.UniqueConstraint(fields=("enrollment", "module"), name="module_result_unique")]

    def __str__(self):
        return f"{self.enrollment} · {self.module}"


class CourseResult(TimeStampedModel):
    enrollment = models.OneToOneField(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="course_result", verbose_name=_("enrolment")
    )
    current_percent = models.DecimalField(_("current score, %"), help_text=_("Completed topics only"), **PERCENT)
    score_percent = models.DecimalField(_("final score, %"), help_text=_("When every topic is completed"), **PERCENT)
    letter = models.CharField(_("letter grade"), max_length=2, blank=True)
    gpa_points = models.DecimalField(_("GPA points"), max_digits=3, decimal_places=2, null=True, blank=True)
    passed = models.BooleanField(_("passed"), default=False)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    topics_total = models.PositiveSmallIntegerField(_("topics"), default=0)
    topics_completed = models.PositiveSmallIntegerField(_("topics completed"), default=0)

    class Meta:
        verbose_name = _("course result")
        verbose_name_plural = _("course results")

    def __str__(self):
        return f"{self.enrollment} · {self.current_percent}"


class ProgressEvent(models.Model):
    """Audit trail of progress changes (teacher actions included) for the student timeline and research."""

    class Action(models.TextChoices):
        STARTED = "started", _("Started")
        PASSED = "passed", _("Passed")
        FAILED = "failed", _("Not passed")
        AWAITING_CHECK = "awaiting_check", _("Sent for checking")
        CONFIRMED = "confirmed", _("Confirmed by the teacher")
        RETURNED = "returned", _("Returned by the teacher")
        UNLOCKED = "unlocked", _("Opened by the teacher")
        TOPIC_COMPLETED = "topic_completed", _("Topic completed")
        COURSE_COMPLETED = "course_completed", _("Course completed")

    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="progress_events", verbose_name=_("enrolment")
    )
    stage = models.ForeignKey(
        "courses.Stage", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("stage")
    )
    topic = models.ForeignKey(
        "courses.Topic", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("topic")
    )
    action = models.CharField(_("action"), max_length=24, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("by"),
        help_text=_("Empty when the student did it"),
    )
    score_percent = models.DecimalField(_("score, %"), **PERCENT)
    created_at = models.DateTimeField(_("at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = _("progress event")
        verbose_name_plural = _("progress events")

    def __str__(self):
        return f"{self.enrollment} · {self.get_action_display()}"
