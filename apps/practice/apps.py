from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PracticeConfig(AppConfig):
    name = "apps.practice"
    label = "practice"
    verbose_name = _("Practice work")
