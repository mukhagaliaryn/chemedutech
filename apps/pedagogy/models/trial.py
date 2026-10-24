from django.db import models
from django.utils.translation import gettext_lazy as _


class Trial(models.Model):
    """«Try it out with the AI student» (guide @S4-ASSEMBLE 2): the assembled version of a lesson, an AI student of one
    readiness level, the stages it has done. A simulation, not a real student's result. Research data — kept."""

    class Level(models.TextChoices):
        HIGH = "high", _("High level")
        MEDIUM = "medium", _("Medium level")
        LOW = "low", _("Low level")

    lesson = models.ForeignKey(
        "pedagogy.Lesson", on_delete=models.PROTECT, related_name="trials", verbose_name=_("lesson")
    )
    version = models.ForeignKey(
        "pedagogy.LessonVersion", on_delete=models.PROTECT, related_name="trials", verbose_name=_("version")
    )

    class Mode(models.TextChoices):
        ASSEMBLED = "assembled", _("The assembled lesson, stage by stage on demand")
        STEPWISE = "stepwise", _("Conducting the lesson stage by stage")

    mode = models.CharField(_("mode"), max_length=12, choices=Mode.choices, default=Mode.ASSEMBLED)
    grade = models.CharField(_("grade"), max_length=8, blank=True, help_text=_("Section 5: the class, 7–11"))
    level = models.CharField(_("AI student's level"), max_length=8, choices=Level.choices)
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    class Meta:
        ordering = ("-started_at", "-pk")
        verbose_name = _("trial with the AI student")
        verbose_name_plural = _("trials with the AI student")

    def __str__(self):
        return f"{self.lesson} · {self.get_level_display()}"


class TrialTurn(models.Model):
    """The AI student on one stage of a trial — the window «See the AI student's answer» (@S4-ASSEMBLE 4): the task
    (the stage as assembled), the AI student's answer, the possible error, the difficulty, the AI assistant's
    methodical suggestion."""

    class AnswerType(models.TextChoices):
        CORRECT = "correct", _("Correct")
        PARTIAL = "partial", _("Partly correct")
        WRONG = "wrong", _("Wrong")

    trial = models.ForeignKey(Trial, on_delete=models.PROTECT, related_name="turns", verbose_name=_("trial"))
    stage_order = models.PositiveSmallIntegerField(_("stage"))
    stage_title = models.CharField(_("stage title"), max_length=255)
    task = models.TextField(_("task"), help_text=_("HTML, the stage as assembled"))
    answer = models.TextField(_("AI student's answer"))
    answer_type = models.CharField(_("answer type"), max_length=8, choices=AnswerType.choices)
    possible_error = models.TextField(_("possible error"), blank=True)
    difficulty = models.TextField(_("difficulty"), blank=True)
    suggestion = models.TextField(_("methodical suggestion"), blank=True)
    message_id = models.PositiveIntegerField(_("AI message"), null=True, blank=True)
    # section 5, the stepwise trial (@S5 IV) and the analysis sheet after the trial (@S5 VI)
    teacher_explanation = models.TextField(_("teacher's explanation"), blank=True)
    time_minutes = models.PositiveSmallIntegerField(_("time set, minutes"), null=True, blank=True)
    student_analysis = models.TextField(_("the student's explanation"), blank=True)
    follow_up_question = models.TextField(_("follow-up question"), blank=True)
    correction = models.TextField(_("pedagogical correction made"), blank=True)
    improved_task = models.TextField(_("improved task"), blank=True)
    duration_s = models.PositiveIntegerField(_("time spent, s"), null=True, blank=True)
    analysed_at = models.DateTimeField(_("analysed at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ("trial", "stage_order")
        verbose_name = _("AI student's answer")
        verbose_name_plural = _("AI student's answers")
        constraints = [models.UniqueConstraint(fields=("trial", "stage_order"), name="trial_turn_stage_unique")]

    def __str__(self):
        return f"{self.trial} · {self.stage_order}"
