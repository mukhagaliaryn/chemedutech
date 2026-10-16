from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class QuizAttempt(TimeStampedModel):
    """One sitting of a quiz. Research data — never deleted (ARCHITECTURE §9.6)."""

    enrollment = models.ForeignKey(
        "courses.Enrollment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quiz_attempts",
        verbose_name=_("enrolment"),
        help_text=_("Empty for a teacher's preview"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quiz_attempts", verbose_name=_("user")
    )
    quiz = models.ForeignKey(
        "assessments.Quiz", on_delete=models.PROTECT, related_name="attempts", verbose_name=_("quiz")
    )
    attempt_no = models.PositiveSmallIntegerField(_("attempt number"))
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)
    question_ids = models.JSONField(_("questions asked"), default=list, help_text=_("In the order shown"))
    choice_order = models.JSONField(_("option order"), default=dict, blank=True)
    score = models.DecimalField(_("score"), max_digits=7, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(_("max score"), max_digits=7, decimal_places=2, null=True, blank=True)
    percent = models.DecimalField(_("percent"), max_digits=5, decimal_places=2, null=True, blank=True)
    passed = models.BooleanField(_("passed"), default=False)

    class Meta:
        ordering = ("-started_at",)
        verbose_name = _("quiz attempt")
        verbose_name_plural = _("quiz attempts")
        constraints = [models.UniqueConstraint(fields=("user", "quiz", "attempt_no"), name="quiz_attempt_unique_no")]
        indexes = [models.Index(fields=("user", "quiz"))]

    def __str__(self):
        return f"{self.user} · {self.quiz} #{self.attempt_no}"

    @property
    def is_finished(self):
        return self.finished_at is not None


class AttemptAnswer(TimeStampedModel):
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.PROTECT, related_name="answers", verbose_name=_("attempt")
    )
    question = models.ForeignKey(
        "assessments.Question", on_delete=models.PROTECT, related_name="answers", verbose_name=_("question")
    )
    choices = models.ManyToManyField(
        "assessments.Choice", through="AttemptAnswerChoice", blank=True, verbose_name=_("chosen options")
    )
    text_value = models.TextField(_("text answer"), blank=True)
    numeric_value = models.DecimalField(_("number answer"), max_digits=14, decimal_places=4, null=True, blank=True)
    is_correct = models.BooleanField(_("correct"), default=False)
    points = models.DecimalField(_("points"), max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("answer")
        verbose_name_plural = _("answers")
        constraints = [models.UniqueConstraint(fields=("attempt", "question"), name="attempt_answer_unique")]

    def __str__(self):
        return f"{self.attempt} · {self.question_id}"


class AttemptAnswerChoice(models.Model):
    """Chosen options; PROTECT keeps logged answers intact if an author tries to delete an option."""

    answer = models.ForeignKey(AttemptAnswer, on_delete=models.CASCADE)
    choice = models.ForeignKey("assessments.Choice", on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("answer", "choice"), name="attempt_answer_choice_unique")]

    def __str__(self):
        return f"{self.answer_id} → {self.choice_id}"
