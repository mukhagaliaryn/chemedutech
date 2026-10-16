from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from . import services
from .models import CourseResult, ModuleResult, ProgressEvent, StageProgress, TopicResult


class ReadOnlyAdmin(ModelAdmin):
    """Progress is derived by progress.services — never edited by hand."""

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StageProgress)
class StageProgressAdmin(ReadOnlyAdmin):
    list_display = ("enrollment", "stage", "status", "score_percent", "needs_attention", "unlocked_by", "completed_at")
    list_filter = ("enrollment__course", "status", "needs_attention", "stage__kind")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name", "stage__title")
    list_select_related = ("enrollment__student", "enrollment__course", "stage__topic")
    actions = ["open_for_student"]

    @admin.action(description=_("Open the selected stages for the student"))
    def open_for_student(self, request, queryset):
        opened = 0
        for sp in queryset.select_related("enrollment", "stage__topic__module"):
            try:
                services.unlock_stage(sp.enrollment, sp.stage, request.user)
                opened += 1
            except services.StageLocked:
                continue
        self.message_user(request, _("Opened: %(n)d") % {"n": opened}, messages.SUCCESS)


@admin.register(TopicResult)
class TopicResultAdmin(ReadOnlyAdmin):
    list_display = ("enrollment", "topic", "status", "score_percent", "completed_at")
    list_filter = ("enrollment__course", "status")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name")


@admin.register(ModuleResult)
class ModuleResultAdmin(ReadOnlyAdmin):
    list_display = ("enrollment", "module", "current_percent", "score_percent", "completed_at")
    list_filter = ("enrollment__course",)


@admin.register(CourseResult)
class CourseResultAdmin(ReadOnlyAdmin):
    list_display = (
        "enrollment", "current_percent", "score_percent", "letter", "gpa_points", "passed", "topics_completed",
    )  # fmt: skip
    list_filter = ("enrollment__course", "passed", "letter")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name")
    actions = ["recalculate"]

    @admin.action(description=_("Recalculate"))
    def recalculate(self, request, queryset):
        for result in queryset.select_related("enrollment"):
            services.recalculate(result.enrollment)
        self.message_user(request, _("Recalculated."), messages.SUCCESS)


@admin.register(ProgressEvent)
class ProgressEventAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "enrollment", "action", "stage", "topic", "actor", "score_percent")
    list_filter = ("action", "enrollment__course")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name")
