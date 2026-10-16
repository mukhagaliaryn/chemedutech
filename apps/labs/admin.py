from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import LabAttempt, LabEvent


class LabEventInline(TabularInline):
    model = LabEvent
    extra = 0
    can_delete = False
    readonly_fields = ("seq", "t_ms", "type", "step", "payload")


@admin.register(LabAttempt)
class LabAttemptAdmin(ModelAdmin):
    list_display = (
        "user",
        "research_cohort",
        "stage",
        "score_percent",
        "lab_key",
        "experiment_key",
        "status",
        "duration_s",
        "order_errors",
        "safety_warnings",
        "wrong_items",
        "analysis_correct",
        "analysis_total",
        "started_at",
    )
    list_filter = ("lab_key", "experiment_key", "research_cohort", "status", "enrollment__course")
    search_fields = ("user__username", "user__last_name")
    inlines = [LabEventInline]

    def has_delete_permission(self, request, obj=None):
        return False  # research data is never deleted (ARCHITECTURE §9.6)
