from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Course(models.Model):
    title = models.CharField(_("title"), max_length=255)
    slug = models.SlugField(_("slug"), unique=True)
    description = models.TextField(_("description"), blank=True)
    is_published = models.BooleanField(_("published"), default=True)

    class Meta:
        verbose_name = _("course")
        verbose_name_plural = _("courses")

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules", verbose_name=_("course"))
    number = models.PositiveSmallIntegerField(_("number"))
    title = models.CharField(_("title"), max_length=255)

    class Meta:
        ordering = ("course", "number")
        unique_together = ("course", "number")
        verbose_name = _("module")
        verbose_name_plural = _("modules")

    def __str__(self):
        return f"{self.number}. {self.title}"


class Topic(models.Model):
    """A course topic. Each topic has its own lab work.

    ``lab_key`` points to a code-defined lab in ``apps.labs.experiments``
    (lab logic lives in code, not in the database).
    """

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="topics", verbose_name=_("module"))
    number = models.PositiveSmallIntegerField(_("number"), help_text=_("Number within the whole course (1–15)"))
    title = models.CharField(_("title"), max_length=255)
    summary = models.TextField(_("summary"), blank=True)
    theory = models.TextField(_("theory"), blank=True, help_text=_("HTML content of the theory section"))
    lab_key = models.CharField(_("lab key"), max_length=32, blank=True)
    is_published = models.BooleanField(_("published"), default=False)

    class Meta:
        ordering = ("module__course", "number")
        verbose_name = _("topic")
        verbose_name_plural = _("topics")

    def __str__(self):
        return f"{self.number}. {self.title}"

    def get_absolute_url(self):
        return reverse("courses:topic", args=[self.module.course.slug, self.number])
