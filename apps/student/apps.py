from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StudentConfig(AppConfig):
    name = "apps.student"
    label = "student"
    verbose_name = _("Student cabinet")
