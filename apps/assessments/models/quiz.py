from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.fields import CKEditor5Field

from apps.core.models import TimeStampedModel


class Quiz(TimeStampedModel):
    class Kind(models.TextChoices):
        CHECKPOINT = "checkpoint", _("Checkpoint quiz")
        TOPIC_TEST = "topic_test", _("Topic test")
        MODULE_TEST = "module_test", _("Module test")
        FINAL = "final", _("Final test")

    class Grading(models.TextChoices):
        BEST = "best", _("Best attempt")
        LAST = "last", _("Last attempt")
        FIRST = "first", _("First attempt")

    title = models.CharField(_("title"), max_length=255)
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices, default=Kind.CHECKPOINT)
    pass_percent = models.PositiveSmallIntegerField(
        _("pass mark, %"), default=60, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    time_limit_min = models.PositiveSmallIntegerField(
        _("time limit, min"), null=True, blank=True, help_text=_("Empty = no limit")
    )
    max_attempts = models.PositiveSmallIntegerField(
        _("attempts allowed"), null=True, blank=True, help_text=_("Empty = unlimited")
    )
    questions_per_attempt = models.PositiveSmallIntegerField(
        _("questions per attempt"),
        null=True,
        blank=True,
        help_text=_("Empty = all questions; otherwise a random selection from the pool"),
    )
    shuffle_questions = models.BooleanField(_("shuffle questions"), default=False)
    shuffle_choices = models.BooleanField(_("shuffle answer options"), default=True)
    grading = models.CharField(_("attempt that counts"), max_length=8, choices=Grading.choices, default=Grading.BEST)
    show_answers_after = models.BooleanField(
        _("show correct answers"), default=False, help_text=_("Show correct answers and explanations after an attempt")
    )

    class Meta:
        verbose_name = _("quiz")
        verbose_name_plural = _("quizzes")

    def __str__(self):
        return self.title


class Question(TimeStampedModel):
    class Kind(models.TextChoices):
        SINGLE = "single", _("One correct option")
        MULTIPLE = "multiple", _("Several correct options")
        NUMERIC = "numeric", _("Number")
        SHORT_TEXT = "short_text", _("Short text")
        FORMULA = "formula", _("Chemical formula")
        EQUATION = "equation", _("Reaction equation")

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions", verbose_name=_("quiz"))
    order = models.PositiveSmallIntegerField(_("order"), default=1)
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices, default=Kind.SINGLE)
    text = CKEditor5Field(_("question"), config_name="compact")
    points = models.DecimalField(
        _("points"), max_digits=5, decimal_places=2, default=1, validators=[MinValueValidator(0)]
    )
    explanation = models.TextField(_("explanation"), blank=True, help_text=_("Shown after the attempt"))
    numeric_answer = models.DecimalField(_("correct number"), max_digits=14, decimal_places=4, null=True, blank=True)
    numeric_tolerance = models.DecimalField(
        _("allowed deviation"),
        max_digits=14,
        decimal_places=4,
        default=0,
        help_text=_("Absolute, in the units of the answer (0 = exact)"),
    )
    accepted_answers = models.JSONField(
        _("accepted answers"),
        default=list,
        blank=True,
        help_text=_(
            'Short text: accepted spellings; formula or equation: correct answers, e.g. ["ZnCl2"] or '
            '["Zn + 2HCl -> ZnCl2 + H2"]'
        ),
    )
    is_active = models.BooleanField(
        _("in use"), default=True, help_text=_("Retired questions stay in old attempts but are not asked again")
    )

    class Meta:
        ordering = ("quiz", "order", "pk")
        verbose_name = _("question")
        verbose_name_plural = _("questions")

    def __str__(self):
        return f"{self.quiz} · {self.order}"

    def clean(self):
        from ..chem import ChemError, parse_equation, parse_formula

        if self.kind == self.Kind.NUMERIC and self.numeric_answer is None:
            raise ValidationError({"numeric_answer": _("Enter the correct number.")})
        if self.kind not in (self.Kind.SHORT_TEXT, self.Kind.FORMULA, self.Kind.EQUATION):
            return
        answers = self.accepted_answers
        if not isinstance(answers, list) or not answers or not all(isinstance(a, str) and a.strip() for a in answers):
            raise ValidationError({"accepted_answers": _('Enter a list of correct answers, e.g. ["H2O"].')})
        for answer in answers:
            try:
                if self.kind == self.Kind.FORMULA:
                    parse_formula(answer)
                elif self.kind == self.Kind.EQUATION and not parse_equation(answer).is_balanced:
                    raise ValidationError(
                        {"accepted_answers": _("The equation %(eq)s is not balanced.") % {"eq": answer}}
                    )
            except ChemError as exc:
                raise ValidationError(
                    {"accepted_answers": _("Cannot read %(answer)s: %(error)s") % {"answer": answer, "error": exc}}
                ) from exc


class Choice(TimeStampedModel):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices", verbose_name=_("question"))
    order = models.PositiveSmallIntegerField(_("order"), default=1)
    text = models.CharField(_("text"), max_length=500, help_text=_("<sub> and <sup> are allowed: H<sub>2</sub>O"))
    is_correct = models.BooleanField(_("correct"), default=False)

    class Meta:
        ordering = ("question", "order", "pk")
        verbose_name = _("answer option")
        verbose_name_plural = _("answer options")

    def __str__(self):
        return self.text
