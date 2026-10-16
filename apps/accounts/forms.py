from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from apps.organizations.models import AcademicGroup, Department, Faculty, University
from apps.organizations.selectors import (
    active_universities,
    departments_of,
    faculties_of,
    group_by_join_code,
    open_groups_of,
)

from .models import User


class LoginForm(AuthenticationForm):
    """One field for a username or an email (see backends.UsernameOrEmailBackend)."""

    username = forms.CharField(
        label=_("Username or email"),
        max_length=254,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username", "autocapitalize": "none"}),
    )
    remember = forms.BooleanField(label=_("Remember me"), required=False, initial=True)

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("Wrong username, email or password."),
    }


class SignUpForm(UserCreationForm):
    """Student self sign-up: personal data + the academic group (picked from the cascade or by join code)."""

    class GroupMode:
        LIST = "list"
        CODE = "code"

    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    email = forms.EmailField(label=_("Email"))

    group_mode = forms.ChoiceField(
        choices=[(GroupMode.LIST, _("Choose from the list")), (GroupMode.CODE, _("I have a group code"))],
        initial=GroupMode.LIST,
        required=False,
        widget=forms.HiddenInput,
    )
    university = forms.ModelChoiceField(University.objects.none(), label=_("University"), required=False)
    faculty = forms.ModelChoiceField(Faculty.objects.none(), label=_("Faculty"), required=False)
    department = forms.ModelChoiceField(Department.objects.none(), label=_("Department"), required=False)
    group = forms.ModelChoiceField(
        AcademicGroup.objects.none(),
        label=_("Group"),
        required=False,
        help_text=_("Each list is loaded from the previous choice"),
    )
    join_code = forms.CharField(
        label=_("Group code"),
        max_length=16,
        required=False,
        help_text=_("Ask your teacher for the 8-character code"),
        widget=forms.TextInput(attrs={"autocapitalize": "characters", "autocomplete": "off"}),
    )
    research_consent = forms.BooleanField(
        label=_("I agree that anonymised data about my learning activity may be used in pedagogical research."),
        required=False,
    )

    CASCADE = ("university", "faculty", "department", "group")
    field_order = (
        "first_name", "last_name", "email", "username", "password1", "password2",
        "group_mode", *CASCADE, "join_code", "research_consent",
    )  # fmt: skip

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "username")
        help_texts = {"username": _("Latin letters, digits and . _ - characters")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["university"].queryset = active_universities()
        self._narrow_cascade()

    def _raw(self, name):
        source = self.data if self.is_bound else self.initial
        value = source.get(self.add_prefix(name) if self.is_bound else name)
        return value or None

    def _narrow_cascade(self):
        """Each select lists the children of the parent chosen above; a stale child is dropped."""
        parents = {"faculty": faculties_of, "department": departments_of, "group": open_groups_of}
        parent = None
        for name in self.CASCADE:
            field = self.fields[name]
            if name != "university":
                field.queryset = parents[name](parent) if parent else field.queryset.none()
            value = self._raw(name)
            parent = field.queryset.filter(pk=value).first() if value and str(value).isdigit() else None
            if parent is None and not self.is_bound:
                self.initial[name] = None

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("A user with this email already exists."))
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("group_mode") == self.GroupMode.CODE:
            group = group_by_join_code(cleaned.get("join_code"))
            if group is None:
                self.add_error("join_code", _("No active group has this code. Check it with your teacher."))
        else:
            group = cleaned.get("group")
            if group is None:
                self.add_error("group", _("Choose your group."))
        cleaned["resolved_group"] = group
        return cleaned
