from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Course, Module, Topic


class ModuleInline(TabularInline):
    model = Module
    extra = 0


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    list_display = ("title", "slug", "is_published")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ModuleInline]


@admin.register(Topic)
class TopicAdmin(ModelAdmin):
    list_display = ("number", "title", "module", "lab_key", "is_published")
    list_filter = ("module__course", "module", "is_published")
    list_editable = ("is_published",)
