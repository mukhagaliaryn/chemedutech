"""Stage content, one model per stage kind (Stage.kind ↔ O2O). Practice work lives in apps.practice."""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.fields import CKEditor5Field

from apps.core.models import TimeStampedModel
from apps.labs.engine import all_labs, get_lab


class TheoryContent(TimeStampedModel):
    stage = models.OneToOneField(
        "courses.Stage", on_delete=models.CASCADE, related_name="theory_content", verbose_name=_("stage")
    )
    body = CKEditor5Field(_("text"), blank=True, config_name="default")

    class Meta:
        verbose_name = _("theory")
        verbose_name_plural = _("theory")

    def __str__(self):
        return str(self.stage)


class TheoryAttachment(TimeStampedModel):
    content = models.ForeignKey(
        TheoryContent, on_delete=models.CASCADE, related_name="attachments", verbose_name=_("theory")
    )
    order = models.PositiveSmallIntegerField(_("order"), default=1)
    title = models.CharField(_("title"), max_length=255)
    file = models.FileField(_("file"), upload_to="theory/")

    class Meta:
        ordering = ("order", "pk")
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")

    def __str__(self):
        return self.title


class VideoContent(TimeStampedModel):
    class Provider(models.TextChoices):
        YOUTUBE = "youtube", "YouTube"
        VIMEO = "vimeo", "Vimeo"
        FILE = "file", _("Uploaded file")

    stage = models.OneToOneField(
        "courses.Stage", on_delete=models.CASCADE, related_name="video_content", verbose_name=_("stage")
    )
    provider = models.CharField(_("source"), max_length=16, choices=Provider.choices, default=Provider.YOUTUBE)
    url = models.URLField(_("link"), blank=True)
    file = models.FileField(_("video file"), upload_to="video/", blank=True)
    duration_s = models.PositiveIntegerField(_("duration, s"), null=True, blank=True)
    min_watch_percent = models.PositiveSmallIntegerField(
        _("must be watched, %"), default=80, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

    class Meta:
        verbose_name = _("video")
        verbose_name_plural = _("videos")

    def __str__(self):
        return str(self.stage)

    def clean(self):
        if self.provider == self.Provider.FILE and not self.file:
            raise ValidationError({"file": _("Upload the video file.")})
        if self.provider != self.Provider.FILE and not self.url:
            raise ValidationError({"url": _("Paste the video link.")})


def lab_choices():
    return [(key, f"{key} · {lab.title}") for key, lab in sorted(all_labs().items())]


class LabContent(TimeStampedModel):
    """Points at a code-defined lab (apps.labs.engine registry); the lab itself is not stored in the DB."""

    stage = models.OneToOneField(
        "courses.Stage", on_delete=models.CASCADE, related_name="lab_content", verbose_name=_("stage")
    )
    lab_key = models.CharField(_("lab"), max_length=32, choices=lab_choices)
    experiments = models.JSONField(
        _("experiments"),
        default=list,
        blank=True,
        help_text=_("Experiment keys in the order they open; empty = all experiments of the lab"),
    )

    class Meta:
        verbose_name = _("lab work")
        verbose_name_plural = _("lab works")

    def __str__(self):
        return str(self.stage)

    def clean(self):
        lab = get_lab(self.lab_key) if self.lab_key else None
        if lab is None:
            return
        known = {e.key for e in lab.experiments}
        if not isinstance(self.experiments, list) or not set(self.experiments) <= known:
            raise ValidationError(
                {"experiments": _("Use experiment keys of this lab: %(keys)s") % {"keys": ", ".join(sorted(known))}}
            )

    def experiment_specs(self):
        """ExperimentSpec objects in stage order."""
        lab = get_lab(self.lab_key)
        if lab is None:
            return []
        if not self.experiments:
            return list(lab.experiments)
        by_key = {e.key: e for e in lab.experiments}
        return [by_key[k] for k in self.experiments if k in by_key]


class TestContent(TimeStampedModel):
    """Topic test. The quiz link (assessments.Quiz) is added in STEP-05."""

    __test__ = False  # not a pytest test class

    stage = models.OneToOneField(
        "courses.Stage", on_delete=models.CASCADE, related_name="test_content", verbose_name=_("stage")
    )
    instructions = models.TextField(_("instructions"), blank=True)

    class Meta:
        verbose_name = _("topic test")
        verbose_name_plural = _("topic tests")

    def __str__(self):
        return str(self.stage)
