from django.contrib import admin

from .models import LabAttempt, LabEvent


class LabEventInline(admin.TabularInline):
    model = LabEvent
    extra = 0
    can_delete = False
    readonly_fields = ("seq", "t_ms", "type", "step", "payload")


@admin.register(LabAttempt)
class LabAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cohort",
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
    list_filter = ("lab_key", "experiment_key", "cohort", "status")
    search_fields = ("user__username", "user__last_name")
    inlines = [LabEventInline]
