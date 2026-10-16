from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CertificatesConfig(AppConfig):
    name = "apps.certificates"
    label = "certificates"
    verbose_name = _("Certificates")
