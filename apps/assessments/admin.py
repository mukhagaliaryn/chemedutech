from django.contrib import admin
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from .models import AttemptAnswer, Choice, Question, Quiz, QuizAttempt


class QuestionInline(TabularInline):
    """Overview of the quiz's questions; the text and options are edited on the question page."""

    model = Question
    extra = 0
    fields = ("order", "excerpt", "kind", "points", "is_active")
    readonly_fields = ("excerpt",)
    ordering_field = "order"
    hide_ordering_field = True
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False  # «Add question» on the question page (it needs the rich-text editor)

    @admin.display(description=_("question"))
    def excerpt(self, obj):
        return Truncator(strip_tags(obj.text)).chars(90)


@admin.register(Quiz)
class QuizAdmin(ModelAdmin):
    list_display = ("title", "kind", "question_count", "pass_percent", "max_attempts", "time_limit_min")
    list_filter = ("kind",)
    search_fields = ("title",)
    inlines = [QuestionInline]
    fieldsets = (
        (None, {"fields": ("title", "kind", "pass_percent")}),
        (
            _("Attempts"),
            {
                "fields": (
                    "max_attempts",
                    "time_limit_min",
                    "grading",
                    "questions_per_attempt",
                    "shuffle_questions",
                    "shuffle_choices",
                    "show_answers_after",
                )
            },  # fmt: skip
        ),
    )

    @admin.display(description=_("questions"))
    def question_count(self, obj):
        return obj.questions.filter(is_active=True).count()


class ChoiceInline(TabularInline):
    model = Choice
    extra = 2
    fields = ("order", "text", "is_correct")
    ordering_field = "order"
    hide_ordering_field = True


@admin.register(Question)
class QuestionAdmin(ModelAdmin):
    list_display = ("__str__", "excerpt", "kind", "points", "is_active")
    list_filter = ("quiz", "kind", "is_active")
    search_fields = ("text", "quiz__title")
    autocomplete_fields = ("quiz",)
    inlines = [ChoiceInline]
    fieldsets = (
        (None, {"fields": ("quiz", "order", "kind", "text", "points", "is_active")}),
        (_("Number answer"), {"fields": ("numeric_answer", "numeric_tolerance")}),
        (_("Short text answer"), {"fields": ("accepted_answers",)}),
        (None, {"fields": ("explanation",)}),
    )

    @admin.display(description=_("question"))
    def excerpt(self, obj):
        return Truncator(strip_tags(obj.text)).chars(90)

    def get_changeform_initial_data(self, request):
        return {**super().get_changeform_initial_data(request), "accepted_answers": []}


class AttemptAnswerInline(TabularInline):
    model = AttemptAnswer
    extra = 0
    can_delete = False
    fields = ("question", "chosen", "text_value", "is_correct", "points")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("chosen options"))
    def chosen(self, obj):
        return ", ".join(strip_tags(c.text) for c in obj.choices.all()) or "—"


@admin.register(QuizAttempt)
class QuizAttemptAdmin(ModelAdmin):
    """Research data: read-only, never deleted."""

    list_display = ("user", "quiz", "attempt_no", "percent", "passed", "started_at", "finished_at")
    list_filter = ("quiz", "passed", "enrollment__research_cohort")
    search_fields = ("user__username", "user__last_name", "quiz__title")
    list_select_related = ("user", "quiz")
    inlines = [AttemptAnswerInline]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
