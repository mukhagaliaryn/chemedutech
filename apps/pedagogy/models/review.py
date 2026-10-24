from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Review(models.Model):
    """The teacher's grade: a section 5 practice (guide @S5 VII) or one trial of the section 6 microlesson (@S6 VI) —
    five criteria × 2 points = 10, a comment. Kept apart from the ICPAI component percents (@S5 VII, @S7)."""

    CRITERIA = (
        (1, _("Organising the structure of the authorial lesson correctly from the scientific and methodical side")),
        (2, _("Designing research tasks and virtual experiments")),
        (3, _("Analysing the AI student's answers and correcting scientific errors")),
        (4, _("Managing the stages of conducting the lesson systematically")),
        (5, _("Improving the authorial lesson and reflection")),
    )
    MICRO_CRITERIA = (
        (1, _("Organising the lesson structure correctly")),
        (2, _("Explaining the chemistry content scientifically correctly")),
        (3, _("Asking the student effective questions")),
        (4, _("Acting pedagogically according to the student's answer")),
        (5, _("Keeping to the time and summing up the microlesson")),
    )
    MAX_POINTS = 2

    lesson = models.ForeignKey(
        "pedagogy.Lesson", on_delete=models.PROTECT, related_name="reviews", verbose_name=_("lesson")
    )
    trial = models.ForeignKey(
        "pedagogy.Trial",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviews",
        verbose_name=_("trial"),
        help_text=_("Section 6: the trial graded"),
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lesson_reviews", verbose_name=_("teacher")
    )
    scores = models.JSONField(_("points by criterion"), default=dict, help_text=_('{"1": 2, "2": 1, …}'))
    total = models.PositiveSmallIntegerField(_("total"), default=0, validators=[MaxValueValidator(10)])
    comment = models.TextField(_("comment"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("teacher's grade")
        verbose_name_plural = _("teachers' grades")
        constraints = [
            models.UniqueConstraint(fields=("lesson",), condition=Q(trial__isnull=True), name="review_one_per_lesson"),
            models.UniqueConstraint(fields=("trial",), condition=Q(trial__isnull=False), name="review_one_per_trial"),
        ]

    def __str__(self):
        return f"{self.lesson} · {self.total}/10"

    @classmethod
    def criteria_for(cls, lesson) -> tuple:
        return cls.MICRO_CRITERIA if lesson.kind == "microlesson" else cls.CRITERIA
