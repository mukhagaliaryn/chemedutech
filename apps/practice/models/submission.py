from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

DECIMAL = {"max_digits": 7, "decimal_places": 2}


class PracticeSubmission(TimeStampedModel):
    """One attempt at a practice task. Research data — never deleted."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("Submitted")
        GRADING = "grading", _("Being graded")
        GRADED = "graded", _("Graded")
        NEEDS_REVIEW = "needs_review", _("Waiting for the teacher")
        RETURNED = "returned", _("Returned")

    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="practice_submissions", verbose_name=_("enrolment")
    )
    stage = models.ForeignKey(
        "courses.Stage", on_delete=models.PROTECT, related_name="practice_submissions", verbose_name=_("stage")
    )
    attempt_no = models.PositiveSmallIntegerField(_("attempt number"))
    submitted_at = models.DateTimeField(_("submitted at"), auto_now_add=True)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    score = models.DecimalField(_("score"), null=True, blank=True, **DECIMAL)
    max_score = models.DecimalField(_("max score"), null=True, blank=True, **DECIMAL)
    percent = models.DecimalField(_("percent"), max_digits=5, decimal_places=2, null=True, blank=True)
    file = models.FileField(_("attached file"), upload_to="practice/", blank=True)
    graded_at = models.DateTimeField(_("graded at"), null=True, blank=True)
    teacher_override = models.BooleanField(_("changed by the teacher"), default=False)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("checked by"),
    )
    teacher_comment = models.TextField(_("teacher's comment"), blank=True)

    class Meta:
        ordering = ("-submitted_at",)
        verbose_name = _("practice submission")
        verbose_name_plural = _("practice submissions")
        constraints = [
            models.UniqueConstraint(fields=("enrollment", "stage", "attempt_no"), name="practice_submission_unique_no")
        ]

    def __str__(self):
        return f"{self.enrollment} · {self.stage} #{self.attempt_no}"

    @property
    def is_final(self):
        return self.status in (self.Status.GRADED, self.Status.NEEDS_REVIEW)


class PracticeAnswer(TimeStampedModel):
    submission = models.ForeignKey(
        PracticeSubmission, on_delete=models.PROTECT, related_name="answers", verbose_name=_("submission")
    )
    item = models.ForeignKey(
        "practice.PracticeItem", on_delete=models.PROTECT, related_name="answers", verbose_name=_("answer field")
    )
    raw_value = models.TextField(_("answer as typed"), blank=True, help_text=_("Stored unchanged"))
    normalized = models.JSONField(_("normalised answer"), default=dict, blank=True)
    is_correct = models.BooleanField(_("correct"), null=True, blank=True, help_text=_("Empty until graded"))
    points = models.DecimalField(_("points"), default=0, **DECIMAL)
    feedback = models.TextField(_("feedback"), blank=True, help_text=_("Shown to the student"))

    class Meta:
        verbose_name = _("practice answer")
        verbose_name_plural = _("practice answers")
        constraints = [models.UniqueConstraint(fields=("submission", "item"), name="practice_answer_unique")]

    def __str__(self):
        return f"{self.submission} · {self.item.label}"


class AIGrade(models.Model):
    """The AI's grade of one open answer, kept forever for reproducibility (§5.6)."""

    class Confidence(models.TextChoices):
        HIGH = "high", _("High")
        LOW = "low", _("Low")

    answer = models.OneToOneField(
        PracticeAnswer, on_delete=models.PROTECT, related_name="ai_grade", verbose_name=_("answer")
    )
    model = models.CharField(_("model"), max_length=64)
    prompt_version = models.CharField(_("prompt version"), max_length=32)
    criteria_scores = models.JSONField(_("criteria"), default=list, help_text=_("[{criterion_id, points, reason}]"))
    feedback_kk = models.TextField(_("feedback for the student"), blank=True)
    confidence = models.CharField(_("confidence"), max_length=8, choices=Confidence.choices, default=Confidence.LOW)
    raw_response = models.JSONField(_("raw response"), default=dict, blank=True)
    input_tokens = models.PositiveIntegerField(_("input tokens"), default=0)
    output_tokens = models.PositiveIntegerField(_("output tokens"), default=0)
    latency_ms = models.PositiveIntegerField(_("latency, ms"), default=0)
    calls = models.PositiveSmallIntegerField(_("API calls"), default=1, help_text=_("Including retries"))
    error = models.TextField(_("error"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("AI grade")
        verbose_name_plural = _("AI grades")

    def __str__(self):
        return f"{self.answer} · {self.model}"

    @property
    def ok(self):
        return not self.error and self.confidence == self.Confidence.HIGH

    @property
    def points(self):
        return sum((c.get("points") or 0) for c in self.criteria_scores)


class TeacherReview(models.Model):
    """A teacher confirmed or changed the grade of an open answer — for AI ↔ teacher agreement (§5.6)."""

    answer = models.ForeignKey(
        PracticeAnswer, on_delete=models.PROTECT, related_name="teacher_reviews", verbose_name=_("answer")
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name=_("teacher")
    )
    ai_points = models.DecimalField(_("AI points"), null=True, blank=True, **DECIMAL)
    teacher_points = models.DecimalField(_("teacher's points"), **DECIMAL)
    criteria_scores = models.JSONField(_("criteria"), default=list, blank=True)
    reason = models.TextField(_("reason"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("teacher review")
        verbose_name_plural = _("teacher reviews")

    def __str__(self):
        return f"{self.answer} · {self.teacher}"
