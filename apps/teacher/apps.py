from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TeacherConfig(AppConfig):
    name = "apps.teacher"
    label = "teacher"
    verbose_name = _("Teacher cabinet")
