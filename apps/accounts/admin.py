from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "cohort", "study_group", "is_active")
    list_filter = ("role", "cohort", "study_group", "is_staff")
    list_editable = ("cohort",)
    fieldsets = BaseUserAdmin.fieldsets + ((_("Platform"), {"fields": ("role", "cohort", "study_group")}),)
