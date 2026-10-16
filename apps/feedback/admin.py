from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("user", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("user__username", "user__last_name", "title")
    list_select_related = ("user",)
    readonly_fields = ("user", "kind", "title", "url", "created_at")

    def has_add_permission(self, request):
        return False
