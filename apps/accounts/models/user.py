from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

# No "@": the login field accepts a username or an email and tells them apart by "@".
username_validator = RegexValidator(
    r"^[A-Za-z0-9._-]+\Z",
    _("Use Latin letters, digits and the characters . _ - only."),
)


class UserManager(BaseUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(TimeStampedModel, AbstractUser):
    """Platform account. Students sign up themselves; teachers are added by the admin.

    ``is_staff`` follows the role: only admins get into /admin/.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", _("Administrator")
        TEACHER = "teacher", _("Teacher")
        STUDENT = "student", _("Student")

    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        validators=[username_validator],
        help_text=_("Latin letters, digits and . _ - characters."),
        error_messages={"unique": _("A user with that username already exists.")},
    )
    email = models.EmailField(_("email address"))
    role = models.CharField(_("role"), max_length=16, choices=Role.choices, default=Role.STUDENT, db_index=True)
    middle_name = models.CharField(_("middle name"), max_length=150, blank=True, help_text=_("Patronymic"))
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    avatar = models.ImageField(_("avatar"), upload_to="avatars/", blank=True)
    language = models.CharField(
        _("interface language"), max_length=8, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE
    )

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="user_email_ci_unique",
                violation_error_message=_("A user with this email already exists."),
            ),
        ]

    def save(self, *args, **kwargs):
        self.is_staff = self.role == self.Role.ADMIN
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "role" in update_fields:
            kwargs["update_fields"] = {*update_fields, "is_staff"}
        super().save(*args, **kwargs)

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def full_name(self):
        """Official order used in gradebooks: last name, first name, patronymic."""
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p) or self.username

    def __str__(self):
        return self.get_full_name() or self.username
