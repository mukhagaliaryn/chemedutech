from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from . import services
from .models import (
    AIGrade,
    GradingRubric,
    PracticeAnswer,
    PracticeItem,
    PracticeSubmission,
    PracticeTask,
    RubricCriterion,
    TeacherReview,
)
from .services import authoring


class ReadOnlyMixin:
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PracticeItemInline(StackedInline):
    model = PracticeItem
    extra = 0
    fields = ("order", "label", "prompt", "kind", "points", "answer_spec", "hint")
    ordering_field = "order"
    hide_ordering_field = True
    show_change_link = True


@admin.register(PracticeTask)
class PracticeTaskAdmin(ModelAdmin):
    list_display = ("title", "stage", "max_attempts", "grading", "item_count")
    search_fields = ("title", "stage__title", "stage__topic__title")
    autocomplete_fields = ("stage",)
    inlines = [PracticeItemInline]

    @admin.display(description=_("answer fields"))
    def item_count(self, obj):
        return obj.items.count()


class GradingRubricInline(StackedInline):
    model = GradingRubric
    can_delete = False
    max_num = 1
    show_change_link = True


@admin.register(PracticeItem)
class PracticeItemAdmin(ModelAdmin):
    list_display = ("label", "task", "kind", "points", "try_link")
    list_filter = ("kind", "task")
    search_fields = ("label", "task__title")
    autocomplete_fields = ("task",)
    fields = ("task", "order", "label", "prompt", "kind", "points", "answer_spec", "hint")

    def get_inlines(self, request, obj):
        return [GradingRubricInline] if obj and obj.kind == PracticeItem.Kind.OPEN else []

    @admin.display(description=_("check"))
    def try_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>', reverse("admin:practice_practiceitem_try", args=[obj.pk]), _("Try it")
        )

    def get_urls(self):
        return [
            path("<int:object_id>/try/", self.admin_site.admin_view(self.try_view), name="practice_practiceitem_try"),
            *super().get_urls(),
        ]

    def try_view(self, request, object_id):
        """«Try it»: the author types an answer and sees how it is graded (nothing is saved)."""
        item = get_object_or_404(PracticeItem.objects.select_related("task"), pk=object_id)
        answer, result, ai, error = request.POST.get("answer", ""), None, None, ""
        if request.method == "POST":
            outcome = authoring.try_answer(item, answer)
            result, ai, error = outcome["result"], outcome["ai"], outcome["error"]
        context = {
            **self.admin_site.each_context(request),
            "title": _("Try it: %(label)s") % {"label": item.label},
            "item": item,
            "answer": answer,
            "result": result,
            "ai": ai,
            "error": error,
            "opts": self.model._meta,
        }
        return render(request, "admin/practice/practiceitem/try.html", context)


class RubricCriterionInline(TabularInline):
    model = RubricCriterion
    extra = 1
    fields = ("order", "text", "points")
    ordering_field = "order"
    hide_ordering_field = True


@admin.register(GradingRubric)
class GradingRubricAdmin(ModelAdmin):
    list_display = ("item", "criteria_total")
    search_fields = ("item__label", "item__task__title")
    autocomplete_fields = ("item",)
    inlines = [RubricCriterionInline]

    @admin.display(description=_("points"))
    def criteria_total(self, obj):
        return sum(c.points for c in obj.criteria.all())


class PracticeAnswerInline(ReadOnlyMixin, TabularInline):
    model = PracticeAnswer
    extra = 0
    can_delete = False
    fields = ("item", "raw_value", "is_correct", "points", "feedback")


@admin.register(PracticeSubmission)
class PracticeSubmissionAdmin(ReadOnlyMixin, ModelAdmin):
    """Research data: read-only and never deleted. Teachers confirm or return work (full queue in STEP-11)."""

    list_display = ("enrollment", "stage", "attempt_no", "status", "percent", "submitted_at", "graded_by")
    list_filter = ("status", "stage__topic__module__course", "enrollment__research_cohort")
    search_fields = ("enrollment__student__username", "enrollment__student__last_name", "stage__title")
    list_select_related = ("enrollment__student", "stage")
    inlines = [PracticeAnswerInline]
    actions = ["confirm", "return_to_student"]

    @admin.action(description=_("Confirm the grades"))
    def confirm(self, request, queryset):
        done = 0
        for submission in queryset.exclude(status=PracticeSubmission.Status.GRADING):
            services.confirm_submission(submission, request.user)
            done += 1
        self.message_user(request, _("Confirmed: %(n)d") % {"n": done}, messages.SUCCESS)

    @admin.action(description=_("Return to the student"))
    def return_to_student(self, request, queryset):
        done = 0
        for submission in queryset.exclude(
            status__in=(PracticeSubmission.Status.GRADING, PracticeSubmission.Status.RETURNED)
        ):
            services.return_submission(submission, request.user)
            done += 1
        self.message_user(request, _("Returned: %(n)d") % {"n": done}, messages.SUCCESS)


@admin.register(AIGrade)
class AIGradeAdmin(ReadOnlyMixin, ModelAdmin):
    list_display = (
        "answer",
        "model",
        "prompt_version",
        "confidence",
        "points_total",
        "calls",
        "latency_ms",
        "created_at",
    )
    list_filter = ("model", "prompt_version", "confidence")
    search_fields = ("answer__submission__enrollment__student__username",)

    @admin.display(description=_("points"))
    def points_total(self, obj):
        return obj.points


@admin.register(TeacherReview)
class TeacherReviewAdmin(ReadOnlyMixin, ModelAdmin):
    list_display = ("answer", "teacher", "ai_points", "teacher_points", "created_at")
    search_fields = ("answer__submission__enrollment__student__username", "teacher__username")
