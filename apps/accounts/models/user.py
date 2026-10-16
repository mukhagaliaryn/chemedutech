from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Platform account.

    ``role`` is the account type. ``cohort`` is the research group used in the
    pedagogical experiment (control vs experimental) and is set by a teacher or
    researcher, never by the student.
    """

    class Role(models.TextChoices):
        STUDENT = "student", _("Student")
        TEACHER = "teacher", _("Teacher")
        RESEARCHER = "researcher", _("Researcher")

    class Cohort(models.TextChoices):
        NONE = "", _("Not assigned")
        CONTROL = "control", _("Control group")
        EXPERIMENTAL = "experimental", _("Experimental group")

    role = models.CharField(_("role"), max_length=16, choices=Role.choices, default=Role.STUDENT)
    cohort = models.CharField(_("research group"), max_length=16, choices=Cohort.choices, blank=True, default="")
    study_group = models.CharField(
        _("study group"), max_length=64, blank=True, help_text=_("Academic group code, e.g. Chem-21-1")
    )

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    @property
    def is_teacher(self):
        return self.role in {self.Role.TEACHER, self.Role.RESEARCHER} or self.is_staff

    def __str__(self):
        return self.get_full_name() or self.username
