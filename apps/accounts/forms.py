from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import User


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    study_group = forms.CharField(label=_("Study group"), max_length=64, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "study_group")
