from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UiConfig(AppConfig):
    """Presentation layer: templates, components, design tokens and static assets."""

    name = "ui"
    verbose_name = _("User interface")
