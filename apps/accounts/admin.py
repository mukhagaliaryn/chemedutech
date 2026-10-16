from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.organizations.models import StudentProfile, TeacherProfile

from .models import User

admin.site.unregister(Group)  # roles live in User.role; Django groups are not used


class TeacherCreationForm(UserCreationForm):
    """The admin adds teachers (students sign up themselves), so the add form defaults to role=teacher."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "role", "last_name", "first_name", "middle_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].initial = User.Role.TEACHER
        for name in ("email", "last_name", "first_name"):
            self.fields[name].required = True


class TeacherProfileInline(StackedInline):
    model = TeacherProfile
    can_delete = False
    extra = 1
    max_num = 1
    autocomplete_fields = ("department",)


class StudentProfileInline(StackedInline):
    model = StudentProfile
    can_delete = False
    extra = 1
    max_num = 1
    autocomplete_fields = ("group",)
    readonly_fields = ("research_consent_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = TeacherCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ("username", "full_name", "email", "role", "group_name", "is_active", "last_login")
    list_filter = ("role", "is_active", "student_profile__group__department", "student_profile__group")
    search_fields = ("username", "first_name", "last_name", "middle_name", "email")
    ordering = ("last_name", "first_name")
    list_select_related = ("student_profile__group",)

    fieldsets = (
        (None, {"fields": ("username", "password", "role")}),
        (
            _("Personal info"),
            {"fields": ("last_name", "first_name", "middle_name", "email", "phone", "avatar", "language")},
        ),
        (_("Permissions"), {"fields": ("is_active", "is_superuser", "user_permissions"), "classes": ["tab"]}),
        (_("Important dates"), {"fields": ("last_login", "date_joined"), "classes": ["tab"]}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "role",
                    "last_name",
                    "first_name",
                    "middle_name",
                    "password1",
                    "password2",
                ),  # fmt: skip
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined")

    def get_inlines(self, request, obj):
        if obj is None or obj.role == User.Role.TEACHER:
            return [TeacherProfileInline]
        if obj.role == User.Role.STUDENT:
            return [StudentProfileInline]
        return []

    @admin.display(description=_("full name"), ordering="last_name")
    def full_name(self, obj):
        return obj.full_name

    @admin.display(description=_("group"), ordering="student_profile__group__name")
    def group_name(self, obj):
        profile = getattr(obj, "student_profile", None)
        return profile.group if profile and profile.group else "—"
