from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Comment, Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("user", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("user__username", "user__last_name", "title")
    list_select_related = ("user",)
    readonly_fields = ("user", "kind", "title", "url", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(Comment)
class CommentAdmin(ModelAdmin):
    """Kept for the research: read-only, never deleted."""

    list_display = ("author", "enrollment", "stage", "content_type", "object_id", "is_read", "created_at")
    list_filter = ("content_type", "is_read")
    search_fields = ("author__username", "enrollment__student__username", "body")
    list_select_related = ("author", "enrollment__student", "stage")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
