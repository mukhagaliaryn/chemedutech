from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.fields import CKEditor5Field

from apps.core.models import TimeStampedModel

# Share of each stage kind in a topic score (ARCHITECTURE §5.2). Split equally between stages of
# the same kind; kinds missing from a topic are normalised away.
DEFAULT_STAGE_KIND_WEIGHTS = {"theory": 10, "video": 10, "lab": 40, "practice": 20, "test": 20}


def default_stage_kind_weights():
    return dict(DEFAULT_STAGE_KIND_WEIGHTS)


class Course(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    class EnrollmentMode(models.TextChoices):
        OPEN = "open", _("Open: any student can enrol")
        GROUP = "group", _("Assigned groups only")
        CODE = "code", _("By course code")

    title = models.CharField(_("title"), max_length=255)
    slug = models.SlugField(_("slug"), unique=True)
    short_description = models.CharField(_("short description"), max_length=300, blank=True)
    description = CKEditor5Field(_("description"), blank=True, config_name="default")
    cover = models.ImageField(_("cover"), upload_to="courses/", blank=True)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    enrollment_mode = models.CharField(
        _("enrolment"), max_length=16, choices=EnrollmentMode.choices, default=EnrollmentMode.GROUP
    )
    enroll_code = models.CharField(
        _("course code"), max_length=16, blank=True, help_text=_("Used when enrolment is by course code")
    )
    is_sequential = models.BooleanField(
        _("sequential"), default=True, help_text=_("Stages and topics open one after another")
    )
    passing_score = models.PositiveSmallIntegerField(_("passing score, %"), default=50)
    certificate_enabled = models.BooleanField(_("certificate"), default=True)
    stage_kind_weights = models.JSONField(
        _("stage kind weights"),
        default=default_stage_kind_weights,
        help_text=_('Share of each stage kind in a topic score, e.g. {"lab": 40, "practice": 20, …}'),
    )
    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="courses.CourseTeacher",
        related_name="taught_courses",
        blank=True,
        verbose_name=_("teachers"),
    )

    class Meta:
        ordering = ("title",)
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        constraints = [
            models.UniqueConstraint(fields=("enroll_code",), condition=~Q(enroll_code=""), name="course_unique_code"),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("courses:dashboard")

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED


class CourseTeacher(TimeStampedModel):
    class Role(models.TextChoices):
        AUTHOR = "author", _("Author")
        ASSISTANT = "assistant", _("Assistant")

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="course_teachers", verbose_name=_("course")
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_roles",
        limit_choices_to={"role": "teacher"},
        verbose_name=_("teacher"),
    )
    role = models.CharField(_("role"), max_length=16, choices=Role.choices, default=Role.AUTHOR)

    class Meta:
        verbose_name = _("course teacher")
        verbose_name_plural = _("course teachers")
        constraints = [models.UniqueConstraint(fields=("course", "teacher"), name="course_teacher_unique")]

    def __str__(self):
        return f"{self.teacher} · {self.course}"


class CourseGroup(TimeStampedModel):
    """An academic group assigned to a course (a stream). Its students are enrolled automatically."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="course_groups", verbose_name=_("course"))
    group = models.ForeignKey(
        "organizations.AcademicGroup", on_delete=models.PROTECT, related_name="course_links", verbose_name=_("group")
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_groups",
        limit_choices_to={"role": "teacher"},
        verbose_name=_("teacher"),
    )
    starts_on = models.DateField(_("starts on"), null=True, blank=True)
    ends_on = models.DateField(_("ends on"), null=True, blank=True)

    class Meta:
        verbose_name = _("course group")
        verbose_name_plural = _("course groups")
        constraints = [models.UniqueConstraint(fields=("course", "group"), name="course_group_unique")]

    def __str__(self):
        return f"{self.group} · {self.course}"
