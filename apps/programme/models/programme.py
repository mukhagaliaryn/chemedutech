from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Programme(TimeStampedModel):
    """The ICPAI programme (docs/icpai/SPEC.md §0): sections that open one after another at 80%.
    Section 1 is an existing course; the programme only collects the sections' percents and opens them."""

    title = models.CharField(_("title"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=64, unique=True)
    is_active = models.BooleanField(_("active"), default=True)
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.PROTECT,
        related_name="programmes",
        verbose_name=_("course"),
        help_text=_("The course of section 1; its students take part in the programme"),
    )

    class Meta:
        ordering = ("title",)
        verbose_name = _("programme")
        verbose_name_plural = _("programmes")

    def __str__(self):
        return self.title


class Section(TimeStampedModel):
    """One numbered section of the programme. What it contains and how its percent is counted depends on
    ``kind`` (programme/providers/<kind>.py); the order of sections is ``number``."""

    class Kind(models.TextChoices):
        COURSE = "course", _("Course")
        DIAGNOSTIC = "diagnostic", _("Diagnostics")
        VIDEO = "video", _("Video")
        DESIGNER = "designer", _("Lesson design constructor")
        RESEARCH_PRACTICE = "research_practice", _("Digital research practice")
        MICROLESSON = "microlesson", _("Microlesson")
        PORTFOLIO = "portfolio", _("Portfolio")
        INDEPENDENT = "independent", _("Independent lesson")

    programme = models.ForeignKey(
        Programme, on_delete=models.CASCADE, related_name="sections", verbose_name=_("programme")
    )
    number = models.PositiveSmallIntegerField(_("number"), help_text=_("The order of the sections"))
    kind = models.CharField(_("kind"), max_length=24, choices=Kind.choices)
    title = models.CharField(_("title"), max_length=255)
    purpose = models.TextField(_("purpose"), blank=True, help_text=_("«What it does» — the text of the author's guide"))
    pass_percent = models.PositiveSmallIntegerField(
        _("pass mark, %"),
        default=80,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text=_("The next section opens when this one reaches it"),
    )
    config = models.JSONField(_("settings"), default=dict, blank=True, help_text=_("Settings of the section kind"))
    guide_anchor = models.CharField(
        _("guide anchor"), max_length=32, blank=True, help_text=_("Tag in docs/icpai/source/guide.md, e.g. @S4")
    )

    class Meta:
        ordering = ("programme", "number")
        verbose_name = _("section")
        verbose_name_plural = _("sections")
        constraints = [models.UniqueConstraint(fields=("programme", "number"), name="section_number_unique")]

    def __str__(self):
        return f"{self.number}. {self.title}"
