from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class LessonTemplate(TimeStampedModel):
    """An authorial lesson template of the guide (@S4-L1, @S4-L2, @S4-L3): seeded verbatim, read-only for students;
    a student designs a lesson of their own from it (``Lesson``)."""

    code = models.SlugField(_("code"), max_length=32, unique=True, help_text=_("chem_design, chem_detective …"))
    number = models.PositiveSmallIntegerField(_("number"), help_text=_("The order of the templates"))
    name = models.CharField(_("authorial model"), max_length=255)
    topic = models.CharField(_("lesson topic"), max_length=255)
    subject = models.CharField(_("subject"), max_length=64)
    grade = models.CharField(_("grade"), max_length=32)
    duration_min = models.PositiveSmallIntegerField(_("duration, min"), default=45)
    technology = models.CharField(_("authorial teaching technology"), max_length=255, blank=True)
    aim = models.TextField(_("lesson aim"))
    feature = models.TextField(_("authorial feature"), blank=True, help_text=_("HTML"))
    outcomes = models.TextField(_("expected results"), blank=True, help_text=_("HTML"))
    product = models.TextField(_("main pedagogical product"), blank=True)
    images = models.JSONField(_("guide pictures"), default=list, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ("number",)
        verbose_name = _("lesson template")
        verbose_name_plural = _("lesson templates")

    def __str__(self):
        return self.name


class TemplateStage(models.Model):
    """A stage of a template: «N-кезең. «Name» – X минут» and its labelled blocks in the guide's order
    (``blocks`` = [{label, field, html}]; ``field`` — the frame field the block belongs to, pedagogy/frames.py)."""

    template = models.ForeignKey(
        LessonTemplate, on_delete=models.CASCADE, related_name="stages", verbose_name=_("template")
    )
    order = models.PositiveSmallIntegerField(_("number"))
    title = models.CharField(_("title"), max_length=255)
    minutes = models.PositiveSmallIntegerField(_("minutes"))
    blocks = models.JSONField(_("blocks"), default=list)

    class Meta:
        ordering = ("template", "order")
        verbose_name = _("template stage")
        verbose_name_plural = _("template stages")
        constraints = [models.UniqueConstraint(fields=("template", "order"), name="template_stage_order_unique")]

    def __str__(self):
        return f"{self.order}. {self.title}"
