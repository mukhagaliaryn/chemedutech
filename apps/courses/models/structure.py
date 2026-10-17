from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

WEIGHT = {"max_digits": 6, "decimal_places": 2, "validators": [MinValueValidator(0)]}


class Module(TimeStampedModel):
    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="modules", verbose_name=_("course")
    )
    order = models.PositiveSmallIntegerField(_("order"), default=1)
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    weight = models.DecimalField(_("weight"), default=1, help_text=_("Weight in the course score"), **WEIGHT)

    class Meta:
        ordering = ("course", "order", "pk")
        verbose_name = _("module")
        verbose_name_plural = _("modules")

    def __str__(self):
        return self.title


class Topic(TimeStampedModel):
    """A lesson. Its content is an ordered list of stages of any kinds (ARCHITECTURE §3.3)."""

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="topics", verbose_name=_("module"))
    order = models.PositiveSmallIntegerField(_("order"), default=1, help_text=_("Order within the module"))
    number = models.PositiveSmallIntegerField(_("number"), help_text=_("Number within the whole course (1–15)"))
    title = models.CharField(_("title"), max_length=255)
    summary = models.TextField(_("summary"), blank=True)
    cover = models.ImageField(_("cover"), upload_to="topics/", blank=True)
    estimated_minutes = models.PositiveSmallIntegerField(_("estimated time, min"), null=True, blank=True)
    weight = models.DecimalField(_("weight"), default=1, help_text=_("Weight in the module score"), **WEIGHT)
    is_published = models.BooleanField(_("published"), default=False)

    class Meta:
        ordering = ("module__course", "number")
        verbose_name = _("topic")
        verbose_name_plural = _("topics")

    def __str__(self):
        return f"{self.number}. {self.title}"

    def clean(self):
        if self.module_id and self.number:
            clash = Topic.objects.filter(module__course_id=self.module.course_id, number=self.number).exclude(
                pk=self.pk
            )
            if clash.exists():
                raise ValidationError({"number": _("This course already has a topic with this number.")})

    def get_absolute_url(self):
        return reverse("student:topic", args=[self.module.course.slug, self.number])


class Stage(TimeStampedModel):
    """One step of a topic. A topic may have any number of stages of every kind, in any order."""

    class Kind(models.TextChoices):
        THEORY = "theory", _("Theory")
        VIDEO = "video", _("Video lesson")
        LAB = "lab", _("Lab work")
        PRACTICE = "practice", _("Practice work")
        TEST = "test", _("Topic test")

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="stages", verbose_name=_("topic"))
    order = models.PositiveSmallIntegerField(_("order"), default=1)
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    title = models.CharField(_("title"), max_length=255)
    is_required = models.BooleanField(_("required"), default=True)
    weight = models.DecimalField(
        _("weight"),
        default=1,
        help_text=_("Relative weight among the stages of the same kind: the course share of the kind is split in this proportion"),
        **WEIGHT,
    )
    pass_percent = models.PositiveSmallIntegerField(
        _("pass mark, %"),
        default=60,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Lab and practice stages; stages graded by a quiz use the quiz's pass mark"),
    )
    checkpoint_quiz = models.OneToOneField(
        "assessments.Quiz",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkpoint_for",
        limit_choices_to={"kind": "checkpoint"},
        verbose_name=_("checkpoint quiz"),
        help_text=_("3–4 questions after a theory or video stage"),
    )

    CONTENT_RELATIONS = {
        Kind.THEORY: "theory_content",
        Kind.VIDEO: "video_content",
        Kind.LAB: "lab_content",
        Kind.TEST: "test_content",
        Kind.PRACTICE: "practice_task",  # STEP-07a (apps.practice)
    }

    class Meta:
        ordering = ("topic", "order", "pk")
        verbose_name = _("stage")
        verbose_name_plural = _("stages")

    def __str__(self):
        return f"{self.topic.number}.{self.order} {self.title}"

    @property
    def content(self):
        """The content object of this stage's kind, or None when it has not been created yet."""
        return getattr(self, self.CONTENT_RELATIONS[self.kind], None)
