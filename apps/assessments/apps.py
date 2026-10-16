from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AssessmentsConfig(AppConfig):
    name = "apps.assessments"
    label = "assessments"
    verbose_name = _("Assessments")
