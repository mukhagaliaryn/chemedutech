from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.assessments.models import Component
from apps.core.models import TimeStampedModel


class Phase(models.TextChoices):
    """The three stages of the section-2 diagnostics (guide @S2): taken in this order, one after another."""

    I = "I", _("I — initial diagnostics")  # noqa: E741 — the stage is called «I» in the guide
    II = "II", _("II — formative diagnostics")
    III = "III", _("III — final diagnostics")


class Level(models.TextChoices):
    """The guide's levels by the total score of a 10-question test: 0–4 low, 5–7 medium, 8–10 high."""

    LOW = "low", _("Low")
    MEDIUM = "medium", _("Medium")
    HIGH = "high", _("High")


class DiagnosticTest(TimeStampedModel):
    """One stage of the diagnostics in a section of kind «diagnostic»: the test (a Quiz with components on its
    questions) and the guide's texts around it. Content comes from seed_icpai (verbatim from the guide)."""

    section = models.ForeignKey(
        "programme.Section", on_delete=models.CASCADE, related_name="diagnostic_tests", verbose_name=_("section")
    )
    phase = models.CharField(_("stage"), max_length=4, choices=Phase.choices)
    quiz = models.ForeignKey(
        "assessments.Quiz", on_delete=models.PROTECT, related_name="diagnostic_tests", verbose_name=_("test")
    )
    stage_name = models.CharField(_("stage name"), max_length=255, blank=True)
    note = models.TextField(_("what the stage does"), blank=True)
    title = models.TextField(_("test title"), blank=True)
    aim = models.TextField(_("aim"), blank=True)
    levels = models.JSONField(
        _("level interpretations"), default=dict, blank=True, help_text=_('{"low": …, "medium": …, "high": …}')
    )

    class Meta:
        ordering = ("section", "phase")
        verbose_name = _("diagnostic test")
        verbose_name_plural = _("diagnostic tests")
        constraints = [models.UniqueConstraint(fields=("section", "phase"), name="diagnostic_test_phase_unique")]

    def __str__(self):
        return self.stage_name or self.get_phase_display()


class DiagnosticResult(models.Model):
    """A student's result in one ICPAI component at one stage (research data, never deleted):
    component % = earned / maximum × 100 (guide @S7 II); the level follows the stage's total score."""

    enrollment = models.ForeignKey(
        "programme.ProgrammeEnrollment",
        on_delete=models.PROTECT,
        related_name="diagnostic_results",
        verbose_name=_("enrolment"),
    )
    test = models.ForeignKey(DiagnosticTest, on_delete=models.PROTECT, related_name="results", verbose_name=_("test"))
    phase = models.CharField(_("stage"), max_length=4, choices=Phase.choices)
    component = models.CharField(_("component"), max_length=16, choices=Component.choices)
    earned = models.DecimalField(_("points"), max_digits=6, decimal_places=2)
    maximum = models.DecimalField(_("maximum"), max_digits=6, decimal_places=2)
    percent = models.DecimalField(_("percent"), max_digits=5, decimal_places=2)
    level = models.CharField(_("level of the stage"), max_length=8, choices=Level.choices)
    attempt = models.ForeignKey(
        "assessments.QuizAttempt", on_delete=models.PROTECT, related_name="+", verbose_name=_("attempt")
    )
    created_at = models.DateTimeField(_("at"), auto_now_add=True)

    class Meta:
        ordering = ("enrollment", "phase", "component")
        verbose_name = _("diagnostic result")
        verbose_name_plural = _("diagnostic results")
        constraints = [
            models.UniqueConstraint(fields=("enrollment", "phase", "component"), name="diagnostic_result_unique")
        ]

    def __str__(self):
        return f"{self.enrollment} · {self.phase} · {self.get_component_display()} {self.percent}%"
