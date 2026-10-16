from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProgressConfig(AppConfig):
    name = "apps.progress"
    label = "progress"
    verbose_name = _("Progress")
