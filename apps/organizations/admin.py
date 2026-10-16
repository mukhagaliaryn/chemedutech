from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from unfold.admin import ModelAdmin, TabularInline

from .models import AcademicGroup, Department, Faculty, Specialty, StudentProfile, TeacherProfile, University
from .services import regenerate_join_code


class FacultyInline(TabularInline):
    model = Faculty
    extra = 0
    fields = ("name", "short_name")
    show_change_link = True


class DepartmentInline(TabularInline):
    model = Department
    extra = 0
    fields = ("name", "short_name")
    show_change_link = True


class SpecialtyInline(TabularInline):
    model = Specialty
    extra = 0
    fields = ("code", "name")


class GroupInline(TabularInline):
    model = AcademicGroup
    extra = 0
    fields = ("name", "specialty", "admission_year", "study_year", "curator", "research_cohort", "is_active")
    autocomplete_fields = ("curator",)
    show_change_link = True


class GroupStudentInline(TabularInline):
    model = StudentProfile
    extra = 0
    fields = ("user", "student_id", "study_year", "research_consent")
    readonly_fields = ("user", "research_consent")
    can_delete = False
    verbose_name_plural = _("students")

    def has_add_permission(self, request, obj=None):
        return False  # students join a group by signing up or are moved from the user page


@admin.register(University)
class UniversityAdmin(ModelAdmin):
    list_display = ("name", "short_name", "city", "is_active")
    list_filter = ("is_active", "city")
    search_fields = ("name", "short_name")
    inlines = [FacultyInline]


@admin.register(Faculty)
class FacultyAdmin(ModelAdmin):
    list_display = ("name", "short_name", "university")
    list_filter = ("university",)
    search_fields = ("name", "short_name", "university__name")
    autocomplete_fields = ("university",)
    inlines = [DepartmentInline]


@admin.register(Department)
class DepartmentAdmin(ModelAdmin):
    list_display = ("name", "short_name", "faculty", "university")
    list_filter = ("faculty__university", "faculty")
    search_fields = ("name", "short_name", "faculty__name")
    autocomplete_fields = ("faculty",)
    list_select_related = ("faculty__university",)
    inlines = [SpecialtyInline, GroupInline]

    @admin.display(description=_("university"), ordering="faculty__university__name")
    def university(self, obj):
        return obj.faculty.university


@admin.register(Specialty)
class SpecialtyAdmin(ModelAdmin):
    list_display = ("code", "name", "department")
    list_filter = ("department__faculty__university",)
    search_fields = ("code", "name")
    autocomplete_fields = ("department",)


@admin.register(AcademicGroup)
class AcademicGroupAdmin(ModelAdmin):
    list_display = (
        "name", "department", "study_year", "admission_year", "curator", "research_cohort", "join_code", "is_active",
    )  # fmt: skip
    list_filter = (
        "department__faculty__university", "department", "research_cohort", "study_year", "is_active",
    )  # fmt: skip
    search_fields = ("name", "join_code", "department__name")
    autocomplete_fields = ("department", "specialty", "curator")
    readonly_fields = ("join_code",)
    list_select_related = ("department", "curator")
    inlines = [GroupStudentInline]
    actions = ["regenerate_codes"]

    @admin.action(description=_("Generate new join codes"))
    def regenerate_codes(self, request, queryset):
        for group in queryset:
            regenerate_join_code(group)
        n = queryset.count()
        self.message_user(
            request, ngettext("%(n)d code regenerated.", "%(n)d codes regenerated.", n) % {"n": n}, messages.SUCCESS
        )


@admin.register(StudentProfile)
class StudentProfileAdmin(ModelAdmin):
    list_display = ("user", "group", "student_id", "study_year", "research_consent")
    list_filter = ("group__department", "group", "research_consent", "study_year")
    search_fields = ("user__username", "user__last_name", "user__first_name", "student_id")
    autocomplete_fields = ("user", "group")
    readonly_fields = ("research_consent_at",)


@admin.register(TeacherProfile)
class TeacherProfileAdmin(ModelAdmin):
    list_display = ("user", "department", "position", "academic_degree")
    list_filter = ("department",)
    search_fields = ("user__username", "user__last_name", "user__first_name")
    autocomplete_fields = ("user", "department")
