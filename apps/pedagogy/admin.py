from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    ExpertReview,
    Lesson,
    LessonEvent,
    LessonStage,
    LessonTemplate,
    LessonVersion,
    TemplateStage,
    Trial,
    TrialTurn,
)


class ReadOnly:
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TemplateStageInline(TabularInline):
    model = TemplateStage
    extra = 0
    fields = ("order", "title", "minutes")
    readonly_fields = ("order", "title", "minutes")
    can_delete = False
    show_change_link = True


@admin.register(LessonTemplate)
class LessonTemplateAdmin(ModelAdmin):
    list_display = ("number", "name", "topic", "grade", "is_active")
    list_display_links = ("name",)
    list_editable = ("is_active",)
    inlines = [TemplateStageInline]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TemplateStage)
class TemplateStageAdmin(ModelAdmin):
    list_display = ("template", "order", "title", "minutes")
    list_filter = ("template",)


class LessonStageInline(ReadOnly, TabularInline):
    model = LessonStage
    extra = 0
    fields = ("order", "title", "minutes", "cleared_at", "edited", "updated_at")
    can_delete = False


@admin.register(Lesson)
class LessonAdmin(ReadOnly, ModelAdmin):
    list_display = ("updated_at", "owner", "title", "source_template", "status")
    list_filter = ("kind", "status", "source_template")
    search_fields = ("owner__username", "owner__last_name", "title")
    inlines = [LessonStageInline]


@admin.register(LessonVersion)
class LessonVersionAdmin(ReadOnly, ModelAdmin):
    list_display = ("created_at", "lesson", "number", "reason")
    list_filter = ("reason",)


@admin.register(LessonEvent)
class LessonEventAdmin(ReadOnly, ModelAdmin):
    list_display = ("created_at", "lesson", "stage", "action")
    list_filter = ("action",)
    search_fields = ("lesson__owner__username",)


class TrialTurnInline(ReadOnly, TabularInline):
    model = TrialTurn
    extra = 0
    fields = ("stage_order", "stage_title", "answer_type", "answer", "possible_error", "difficulty", "suggestion")
    can_delete = False


@admin.register(Trial)
class TrialAdmin(ReadOnly, ModelAdmin):
    list_display = ("started_at", "lesson", "level", "finished_at")
    list_filter = ("level",)
    search_fields = ("lesson__owner__username",)
    inlines = [TrialTurnInline]


@admin.register(ExpertReview)
class ExpertReviewAdmin(ReadOnly, ModelAdmin):
    list_display = ("created_at", "lesson", "kind", "status", "teacher_status", "confirmed_by")
    list_filter = ("kind", "status", "teacher_status")
    search_fields = ("lesson__owner__username", "lesson__topic")
    list_select_related = ("lesson__owner", "confirmed_by")
