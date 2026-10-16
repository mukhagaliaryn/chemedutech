from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrganizationsConfig(AppConfig):
    name = "apps.organizations"
    label = "organizations"
    verbose_name = _("Organizations")
