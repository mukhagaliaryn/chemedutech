from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.fields import CKEditor5Field

from apps.core.models import TimeStampedModel


class PracticeTask(TimeStampedModel):
    """Practice work of one stage (Stage.kind=practice): a problem statement and several answer fields."""

    class Grading(models.TextChoices):
        BEST = "best", _("Best attempt")
        LAST = "last", _("Last attempt")

    stage = models.OneToOneField(
        "courses.Stage",
        on_delete=models.CASCADE,
        related_name="practice_task",
        limit_choices_to={"kind": "practice"},
        verbose_name=_("stage"),
    )
    title = models.CharField(_("title"), max_length=255)
    instructions = CKEditor5Field(_("problem statement"), config_name="default")
    max_attempts = models.PositiveSmallIntegerField(_("attempts allowed"), default=2, validators=[MinValueValidator(1)])
    grading = models.CharField(_("attempt that counts"), max_length=8, choices=Grading.choices, default=Grading.BEST)
    allow_file = models.BooleanField(
        _("allow a file"), default=False, help_text=_("The student may attach a photo or file (not graded)")
    )

    class Meta:
        verbose_name = _("practice task")
        verbose_name_plural = _("practice tasks")

    def __str__(self):
        return self.title


class PracticeItem(TimeStampedModel):
    """One answer field. Exact kinds are checked by code, «open» answers by AI against a rubric (§3.6)."""

    class Kind(models.TextChoices):
        NUMERIC = "numeric", _("Number with a unit")
        FORMULA = "formula", _("Chemical formula")
        EQUATION = "equation", _("Reaction equation")
        TEXT_SHORT = "text_short", _("One or two words")
        CHOICE = "choice", _("Choice from a list")
        BLANK = "blank", _("Fill in the blank")
        MATCHING = "matching", _("Matching")
        ORDERING = "ordering", _("Ordering")
        OPEN = "open", _("Open answer (graded by AI)")

    task = models.ForeignKey(PracticeTask, on_delete=models.CASCADE, related_name="items", verbose_name=_("task"))
    order = models.PositiveSmallIntegerField(_("order"), default=1)
    label = models.CharField(_("label"), max_length=120, help_text=_("e.g. V(H₂) or «Reaction equation»"))
    prompt = CKEditor5Field(_("question"), blank=True, config_name="compact")
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    points = models.DecimalField(
        _("points"), max_digits=5, decimal_places=2, default=1, validators=[MinValueValidator(0)]
    )
    answer_spec = models.JSONField(
        _("correct answer"),
        default=dict,
        blank=True,
        help_text=_("Depends on the kind — see the examples in the documentation (ARCHITECTURE §3.6)"),
    )
    hint = CKEditor5Field(_("hint"), blank=True, config_name="compact")

    class Meta:
        ordering = ("task", "order", "pk")
        verbose_name = _("answer field")
        verbose_name_plural = _("answer fields")

    def __str__(self):
        return f"{self.task} · {self.label}"

    def clean(self):
        from ..checkers import SpecError, validate_spec

        if self.kind == self.Kind.OPEN:
            return
        try:
            validate_spec(self.kind, self.answer_spec)
        except SpecError as exc:
            raise ValidationError({"answer_spec": str(exc)}) from exc


class GradingRubric(TimeStampedModel):
    """How the AI (and the teacher) grade an open answer."""

    item = models.OneToOneField(
        PracticeItem,
        on_delete=models.CASCADE,
        related_name="rubric",
        limit_choices_to={"kind": "open"},
        verbose_name=_("answer field"),
    )
    model_answer = CKEditor5Field(
        _("model answer"), config_name="compact", help_text=_("A reference, not a word-for-word requirement")
    )
    notes = models.TextField(_("notes for the grader"), blank=True)

    class Meta:
        verbose_name = _("grading rubric")
        verbose_name_plural = _("grading rubrics")

    def __str__(self):
        return str(self.item)


class RubricCriterion(TimeStampedModel):
    rubric = models.ForeignKey(
        GradingRubric, on_delete=models.CASCADE, related_name="criteria", verbose_name=_("rubric")
    )
    order = models.PositiveSmallIntegerField(_("order"), default=1)
    text = models.CharField(_("criterion"), max_length=300)
    points = models.DecimalField(
        _("points"), max_digits=5, decimal_places=2, default=1, validators=[MinValueValidator(0)]
    )

    class Meta:
        ordering = ("rubric", "order", "pk")
        verbose_name = _("criterion")
        verbose_name_plural = _("criteria")

    def __str__(self):
        return self.text
