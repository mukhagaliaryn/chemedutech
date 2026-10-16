from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from . import services
from .models import (
    Course,
    CourseGroup,
    CourseTeacher,
    Enrollment,
    LabContent,
    Module,
    Stage,
    TestContent,
    TheoryAttachment,
    TheoryContent,
    Topic,
    VideoContent,
)

# --- Course ------------------------------------------------------------------


class ModuleInline(TabularInline):
    model = Module
    extra = 0
    fields = ("order", "title", "weight")
    ordering_field = "order"
    hide_ordering_field = True
    show_change_link = True


class CourseTeacherInline(TabularInline):
    model = CourseTeacher
    extra = 0
    autocomplete_fields = ("teacher",)


class CourseGroupInline(TabularInline):
    model = CourseGroup
    extra = 0
    fields = ("group", "teacher", "starts_on", "ends_on")
    autocomplete_fields = ("group", "teacher")


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    list_display = ("title", "status", "enrollment_mode", "enrollment_count")
    list_filter = ("status", "enrollment_mode")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ModuleInline, CourseTeacherInline, CourseGroupInline]
    fieldsets = (
        (None, {"fields": ("title", "slug", "short_description", "description", "cover", "status")}),
        (_("Enrolment"), {"fields": ("enrollment_mode", "enroll_code")}),
        (
            _("Learning and grading"),
            {"fields": ("is_sequential", "passing_score", "certificate_enabled", "stage_kind_weights")},
        ),
    )

    @admin.display(description=_("students"))
    def enrollment_count(self, obj):
        return obj.enrollments.count()

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is CourseGroup:
            added = sum(services.sync_group_enrollments(cg) for cg in formset.queryset)
            if added:
                self.message_user(
                    request,
                    ngettext("%(n)d student enrolled.", "%(n)d students enrolled.", added) % {"n": added},
                    messages.SUCCESS,
                )


# --- Module / Topic / Stage ---------------------------------------------------


class TopicInline(TabularInline):
    model = Topic
    extra = 0
    fields = ("order", "number", "title", "weight", "is_published")
    ordering_field = "order"
    hide_ordering_field = True
    show_change_link = True


@admin.register(Module)
class ModuleAdmin(ModelAdmin):
    list_display = ("title", "course", "order", "weight")
    list_filter = ("course",)
    search_fields = ("title",)
    inlines = [TopicInline]


class StageFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if not self.instance.is_published:
            return
        required = [
            f
            for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("is_required")
        ]
        if not required:
            raise ValidationError(_("A published topic needs at least one required stage."))


class StageInline(TabularInline):
    model = Stage
    formset = StageFormSet
    extra = 0
    fields = ("order", "kind", "title", "is_required", "weight", "pass_percent")
    ordering_field = "order"
    hide_ordering_field = True
    show_change_link = True


@admin.register(Topic)
class TopicAdmin(ModelAdmin):
    list_display = ("number", "title", "module", "stage_count", "is_published")
    list_display_links = ("number", "title")
    list_filter = ("module__course", "module", "is_published")
    list_editable = ("is_published",)
    search_fields = ("title",)
    inlines = [StageInline]
    fields = ("module", "order", "number", "title", "summary", "cover", "estimated_minutes", "weight", "is_published")

    @admin.display(description=_("stages"))
    def stage_count(self, obj):
        return obj.stages.count()

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is Stage:
            for stage in formset.queryset:
                services.ensure_stage_content(stage)


class TheoryContentInline(StackedInline):
    model = TheoryContent
    fields = ("body",)
    can_delete = False
    max_num = 1
    show_change_link = True  # attachments are edited on the theory page


class VideoContentInline(StackedInline):
    model = VideoContent
    can_delete = False
    max_num = 1


class LabContentInline(StackedInline):
    model = LabContent
    can_delete = False
    max_num = 1


class TestContentInline(StackedInline):
    model = TestContent
    can_delete = False
    max_num = 1


CONTENT_INLINES = {
    Stage.Kind.THEORY: TheoryContentInline,
    Stage.Kind.VIDEO: VideoContentInline,
    Stage.Kind.LAB: LabContentInline,
    Stage.Kind.TEST: TestContentInline,
}


@admin.register(Stage)
class StageAdmin(ModelAdmin):
    list_display = ("title", "topic", "kind", "order", "is_required", "pass_percent")
    list_filter = ("topic__module__course", "kind", "is_required")
    search_fields = ("title", "topic__title")
    fields = ("topic", "order", "kind", "title", "is_required", "weight", "pass_percent")

    def get_readonly_fields(self, request, obj=None):
        return ("kind",) if obj else ()  # content is tied to the kind

    def get_inlines(self, request, obj):
        inline = CONTENT_INLINES.get(obj.kind) if obj else None
        return [inline] if inline else []

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.ensure_stage_content(obj)


class TheoryAttachmentInline(TabularInline):
    model = TheoryAttachment
    extra = 0
    ordering_field = "order"
    hide_ordering_field = True


@admin.register(TheoryContent)
class TheoryContentAdmin(ModelAdmin):
    list_display = ("stage",)
    search_fields = ("stage__title", "stage__topic__title")
    readonly_fields = ("stage",)
    inlines = [TheoryAttachmentInline]

    def has_add_permission(self, request):
        return False  # created with its stage


# --- Enrolment ---------------------------------------------------------------


@admin.register(CourseGroup)
class CourseGroupAdmin(ModelAdmin):
    list_display = ("group", "course", "teacher", "starts_on", "ends_on")
    list_filter = ("course",)
    autocomplete_fields = ("course", "group", "teacher")
    actions = ["sync_enrollments"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.sync_group_enrollments(obj)

    @admin.action(description=_("Enrol all students of the selected groups"))
    def sync_enrollments(self, request, queryset):
        added = sum(services.sync_group_enrollments(cg) for cg in queryset)
        self.message_user(
            request, ngettext("%(n)d student enrolled.", "%(n)d students enrolled.", added) % {"n": added}
        )


class EnrollmentAddForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ("student", "course")

    def clean(self):
        cleaned = super().clean()
        student, course = cleaned.get("student"), cleaned.get("course")
        if student and not student.is_student:
            raise ValidationError(_("Only students can be enrolled in a course."))
        if student and course and Enrollment.objects.filter(student=student, course=course).exists():
            raise ValidationError(_("This student is already enrolled in the course."))
        return cleaned


@admin.register(Enrollment)
class EnrollmentAdmin(ModelAdmin):
    list_display = ("student", "course", "group", "research_cohort", "source", "status", "enrolled_at")
    list_filter = ("course", "status", "source", "research_cohort", "group")
    search_fields = ("student__username", "student__last_name", "student__first_name")
    autocomplete_fields = ("student", "course", "group")
    list_select_related = ("student", "course", "group")

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = EnrollmentAddForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("student", "course")
        return ("student", "course", "source", "group", "research_cohort", "status", "enrolled_at", "completed_at")

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("student", "course", "source", "group", "research_cohort", "enrolled_at")

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        enrollment = services.enroll(obj.student, obj.course, Enrollment.Source.ADMIN)  # validated by the form
        obj.pk = enrollment.pk  # the admin redirects to the saved object

    def has_delete_permission(self, request, obj=None):
        return False  # enrolments anchor research data; drop a student with status=dropped
