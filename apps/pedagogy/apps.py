from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PedagogyConfig(AppConfig):
    name = "apps.pedagogy"
    label = "pedagogy"
    verbose_name = _("Pedagogical design")
