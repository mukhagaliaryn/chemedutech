from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import AIConversation, AIMessage, AIUsage


class ReadOnly:
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AIMessageInline(ReadOnly, TabularInline):
    model = AIMessage
    extra = 0
    fields = ("created_at", "role", "intent", "content", "input_tokens", "output_tokens", "latency_ms", "error")
    can_delete = False


@admin.register(AIConversation)
class AIConversationAdmin(ReadOnly, ModelAdmin):
    list_display = ("created_at", "user", "mode", "context_type", "context_id", "model", "prompt_version")
    list_filter = ("mode", "context_type", "model")
    search_fields = ("user__username", "user__last_name")
    inlines = [AIMessageInline]


@admin.register(AIUsage)
class AIUsageAdmin(ReadOnly, ModelAdmin):
    list_display = ("date", "user", "requests", "input_tokens", "output_tokens")
    list_filter = ("date",)
    search_fields = ("user__username",)
