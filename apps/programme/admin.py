from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from . import services
from .models import (
    DiagnosticResult,
    DiagnosticTest,
    Programme,
    ProgrammeEnrollment,
    Section,
    SectionEvent,
    SectionProgress,
    SectionSchedule,
    SectionVideo,
)


class SectionInline(TabularInline):
    model = Section
    extra = 0
    fields = ("number", "kind", "title", "pass_percent", "guide_anchor")
    ordering = ("number",)
    show_change_link = True


@admin.register(Programme)
class ProgrammeAdmin(ModelAdmin):
    list_display = ("title", "slug", "course", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SectionInline]


class DiagnosticTestInline(TabularInline):
    model = DiagnosticTest
    extra = 0
    fields = ("phase", "stage_name", "quiz")
    ordering = ("phase",)
    show_change_link = True


class SectionVideoInline(TabularInline):
    model = SectionVideo
    extra = 1
    max_num = 1
    fields = ("url",)


@admin.register(Section)
class SectionAdmin(ModelAdmin):
    list_display = ("number", "title", "kind", "pass_percent", "guide_anchor", "programme")
    list_display_links = ("number", "title")
    list_filter = ("programme", "kind")
    ordering = ("programme", "number")
    inlines = [SectionVideoInline, DiagnosticTestInline]


@admin.register(DiagnosticTest)
class DiagnosticTestAdmin(ModelAdmin):
    list_display = ("phase", "stage_name", "quiz", "section")
    list_filter = ("section__programme",)
    ordering = ("section", "phase")


class ReadOnlyAdmin(ModelAdmin):
    """Section progress is derived by programme.services — never edited by hand."""

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SectionProgressInline(TabularInline):
    model = SectionProgress
    extra = 0
    fields = ("section", "status", "percent", "opened_at", "passed_at", "unlocked_by")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProgrammeEnrollment)
class ProgrammeEnrollmentAdmin(ReadOnlyAdmin):
    list_display = ("student", "programme", "group", "research_cohort", "created_at", "completed_at")
    list_filter = ("programme", "research_cohort")
    search_fields = ("student__username", "student__last_name", "student__email")
    list_select_related = ("student", "programme", "group")
    inlines = [SectionProgressInline]
    actions = ["recalculate"]

    @admin.action(description=_("Recalculate"))
    def recalculate(self, request, queryset):
        for enrollment in queryset:
            services.recalculate(enrollment)
        self.message_user(request, _("Recalculated."), messages.SUCCESS)


@admin.register(SectionProgress)
class SectionProgressAdmin(ReadOnlyAdmin):
    list_display = ("enrollment", "section", "status", "percent", "opened_at", "passed_at", "unlocked_by")
    list_filter = ("section__programme", "status", "section__number")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name")
    list_select_related = ("enrollment__student", "enrollment__programme", "section")
    actions = ["open_for_student"]

    @admin.action(description=_("Open the selected sections for the student"))
    def open_for_student(self, request, queryset):
        for row in queryset.select_related("enrollment", "section"):
            services.unlock_section(row.enrollment, row.section, request.user)
        self.message_user(request, _("Opened: %(n)d") % {"n": queryset.count()}, messages.SUCCESS)


@admin.register(SectionEvent)
class SectionEventAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "enrollment", "section", "action", "percent", "actor")
    list_filter = ("action", "section__programme", "section__number")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name")
    list_select_related = ("enrollment__student", "section", "actor")


@admin.register(DiagnosticResult)
class DiagnosticResultAdmin(ReadOnlyAdmin):
    list_display = ("enrollment", "phase", "component", "earned", "maximum", "percent", "level", "created_at")
    list_filter = ("enrollment__programme", "phase", "component", "level", "enrollment__research_cohort")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name")
    list_select_related = ("enrollment__student", "enrollment__programme")


@admin.register(SectionSchedule)
class SectionScheduleAdmin(ModelAdmin):
    list_display = ("section", "group", "hand_in_on", "trial_on", "set_by")
    list_filter = ("section__programme",)
    list_select_related = ("section", "group", "set_by")
    autocomplete_fields = ("group",)
    readonly_fields = ("set_by",)

    def save_model(self, request, obj, form, change):
        obj.set_by = request.user
        super().save_model(request, obj, form, change)
