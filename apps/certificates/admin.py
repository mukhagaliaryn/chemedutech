from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from . import services
from .models import Certificate, CertificateTemplate


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(ModelAdmin):
    list_display = ("course", "title_text", "signatory_name")


@admin.register(Certificate)
class CertificateAdmin(ModelAdmin):
    """Issued documents: read-only, never deleted; the PDF can be made again (e.g. after a new template)."""

    list_display = ("number", "holder_name", "course_title", "score_percent", "letter", "issued_at")
    search_fields = ("number", "holder_name", "enrollment__student__username")
    list_filter = ("enrollment__course",)
    actions = ["render_again"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description=_("Make the PDF again"))
    def render_again(self, request, queryset):
        for certificate in queryset:
            services.render_pdf(certificate)
        self.message_user(request, _("PDF made: %(n)d") % {"n": queryset.count()}, messages.SUCCESS)
