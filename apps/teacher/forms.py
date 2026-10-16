from django import forms
from django.utils.translation import gettext_lazy as _

from apps.courses import selectors as course_selectors
from apps.organizations.models import AcademicGroup, ResearchCohort


class GroupForm(forms.ModelForm):
    """Create / edit a group. Departments are limited to the teacher's university."""

    class Meta:
        model = AcademicGroup
        fields = ("name", "department", "specialty", "admission_year", "study_year", "research_cohort", "is_active")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = course_selectors.departments_for(user)
        self.fields["specialty"].queryset = course_selectors.specialties_for(user)
        profile = getattr(user, "teacher_profile", None)
        if not self.instance.pk and profile is not None:
            self.fields["department"].initial = profile.department_id
        self.fields["research_cohort"].help_text = _(
            "New enrolments copy it; enrolments without a research group get it now. "
            "An enrolment that already has one keeps it."
        )


class CohortForm(forms.Form):
    research_cohort = forms.ChoiceField(label=_("Research group"), choices=ResearchCohort.choices, required=False)


class AddStudentForm(forms.Form):
    query = forms.CharField(
        label=_("Username or email"),
        max_length=254,
        help_text=_("The student signs up first; then add the account here."),
    )


class AttachCourseForm(forms.Form):
    course = forms.ModelChoiceField(queryset=None, label=_("Course"))
    starts_on = forms.DateField(label=_("Starts on"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    ends_on = forms.DateField(label=_("Ends on"), required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, user, group, *args, **kwargs):
        super().__init__(*args, **kwargs)
        attached = course_selectors.group_courses(group).values_list("course_id", flat=True)
        self.fields["course"].queryset = course_selectors.teacher_courses(user).exclude(pk__in=attached)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("starts_on") and cleaned.get("ends_on") and cleaned["ends_on"] < cleaned["starts_on"]:
            self.add_error("ends_on", _("The end is before the start."))
        return cleaned
