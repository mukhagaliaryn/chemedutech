"""Forms of the course content editor (teacher cabinet, STEP-11)."""

import json

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.assessments.models import Question, Quiz
from apps.courses.models import (
    DEFAULT_STAGE_KIND_WEIGHTS,
    Course,
    LabContent,
    Module,
    Stage,
    TestContent,
    TheoryContent,
    Topic,
    VideoContent,
)
from apps.labs.engine import get_lab
from apps.practice import checkers
from apps.practice.models import PracticeItem, PracticeTask

KIND_LABELS = dict(Stage.Kind.choices)


class CourseForm(forms.ModelForm):
    """Course settings + the share of each stage kind in a topic score (§5.2)."""

    class Meta:
        model = Course
        fields = (
            "title", "short_description", "description", "cover", "status", "enrollment_mode", "enroll_code",
            "is_sequential", "passing_score", "certificate_enabled",
        )  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        weights = {**DEFAULT_STAGE_KIND_WEIGHTS, **(self.instance.stage_kind_weights or {})}
        for kind, label in Stage.Kind.choices:
            self.fields[f"weight_{kind}"] = forms.IntegerField(
                label=label, min_value=0, max_value=100, initial=weights.get(kind, 0)
            )

    @property
    def weight_fields(self):
        return [self[f"weight_{kind}"] for kind, _label in Stage.Kind.choices]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("enrollment_mode") == Course.EnrollmentMode.CODE and not cleaned.get("enroll_code"):
            self.add_error("enroll_code", _("Set a course code for enrolment by code."))
        cleaned["stage_kind_weights"] = {kind: cleaned.get(f"weight_{kind}") or 0 for kind, _l in Stage.Kind.choices}
        return cleaned


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ("title", "description", "weight")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ("module", "title", "summary", "cover", "estimated_minutes", "weight", "is_published")
        widgets = {"summary": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, course, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["module"].queryset = course.modules.order_by("order", "pk")
        self.fields["module"].empty_label = None

    def _post_clean(self):  # the number is managed by the service (course order)
        self._validate_unique = False
        super()._post_clean()


class StageForm(forms.ModelForm):
    class Meta:
        model = Stage
        fields = ("title", "is_required", "weight", "pass_percent")


class NewStageForm(StageForm):
    kind = forms.ChoiceField(label=_("Kind"), choices=Stage.Kind.choices)

    class Meta(StageForm.Meta):
        fields = ("kind", "title", "is_required", "weight", "pass_percent")


class TheoryForm(forms.ModelForm):
    class Meta:
        model = TheoryContent
        fields = ("body",)


class VideoForm(forms.ModelForm):
    class Meta:
        model = VideoContent
        fields = ("provider", "url", "file", "duration_s", "min_watch_percent")


class LabForm(forms.ModelForm):
    experiments = forms.MultipleChoiceField(
        label=_("Experiments"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("None ticked = every experiment of the lab, in its order."),
    )

    class Meta:
        model = LabContent
        fields = ("lab_key",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        key = self.data.get(self.add_prefix("lab_key")) if self.is_bound else self.instance.lab_key
        lab = get_lab(key) if key else None
        self.fields["experiments"].choices = [(e.key, f"{e.number}. {e.title}") for e in lab.experiments] if lab else []
        if not self.is_bound:
            self.initial["experiments"] = self.instance.experiments or []

    def save(self, commit=True):
        chosen = set(self.cleaned_data.get("experiments") or [])
        order = [key for key, _label in self.fields["experiments"].choices]  # the lab's own order
        self.instance.experiments = [key for key in order if key in chosen]
        return super().save(commit)


class TestForm(forms.ModelForm):
    class Meta:
        model = TestContent
        fields = ("instructions",)
        widgets = {"instructions": forms.Textarea(attrs={"rows": 3})}


class PracticeTaskForm(forms.ModelForm):
    class Meta:
        model = PracticeTask
        fields = ("title", "instructions", "max_attempts", "grading", "allow_file")


CONTENT_FORMS = {
    "theory": TheoryForm,
    "video": VideoForm,
    "lab": LabForm,
    "test": TestForm,
    "practice": PracticeTaskForm,
}


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = (
            "title", "pass_percent", "time_limit_min", "max_attempts", "questions_per_attempt", "shuffle_questions",
            "shuffle_choices", "grading", "show_answers_after",
        )  # fmt: skip


class LinesField(forms.CharField):
    """A JSON list edited as one item per line."""

    widget = forms.Textarea(attrs={"rows": 3})

    def prepare_value(self, value):
        return "\n".join(value) if isinstance(value, list) else value

    def to_python(self, value):
        return [line.strip() for line in (value or "").splitlines() if line.strip()]


class QuestionForm(forms.ModelForm):
    accepted_answers = LinesField(
        label=_("Accepted answers"),
        required=False,
        help_text=_("One per line. Short text: accepted spellings; formula or equation: correct answers."),
    )

    class Meta:
        model = Question
        fields = (
            "kind",
            "text",
            "points",
            "explanation",
            "numeric_answer",
            "numeric_tolerance",
            "accepted_answers",
            "is_active",
        )
        widgets = {"explanation": forms.Textarea(attrs={"rows": 2})}


class PracticeItemForm(forms.ModelForm):
    answer_spec = forms.CharField(
        label=_("Correct answer (JSON)"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "font-mono"}),
        help_text=_(
            'e.g. {"value": 2.24, "unit": "L"} · {"formula": "ZnCl2"} · {"equation": "Zn + 2HCl -> ZnCl2 + H2"}'
        ),
    )

    class Meta:
        model = PracticeItem
        fields = ("label", "prompt", "kind", "points", "answer_spec", "hint")
        widgets = {"prompt": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["answer_spec"] = json.dumps(self.instance.answer_spec or {}, ensure_ascii=False, indent=1)

    def clean_answer_spec(self):
        raw = self.cleaned_data.get("answer_spec") or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(_("This is not valid JSON: %(error)s") % {"error": exc.msg}) from exc

    def clean(self):
        cleaned = super().clean()
        kind, spec = cleaned.get("kind"), cleaned.get("answer_spec")
        if kind and kind != PracticeItem.Kind.OPEN and spec is not None:
            try:
                checkers.validate_spec(kind, spec)
            except checkers.SpecError as exc:
                self.add_error("answer_spec", str(exc))
        return cleaned
