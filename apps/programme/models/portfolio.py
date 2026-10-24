from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

# guide @S7 IV — the student's professional reflection, seven questions (verbatim in the kk translation)
QUESTIONS = (
    ("1", _("What professional knowledge and skills have I gained?")),
    ("2", _("What pedagogical decisions did I make on my own while developing the authorial lesson?")),
    ("3", _("What difficulties did I meet in the digital research practice?")),
    ("4", _("What changes did I notice when conducting the microlesson the first time and again?")),
    ("5", _("Which of the teacher's suggestions did I take into account?")),
    ("6", _("Which professional skills do I still need to improve?")),
    ("7", _("What is my next professional goal as a future chemistry teacher?")),
)

# guide @S7 V — the personal development map, five directions
DIRECTIONS = (
    ("chemistry", _("Chemistry subject knowledge")),
    ("digital", _("Using digital technologies")),
    ("design", _("Pedagogical design")),
    ("micro", _("Conducting a microlesson")),
    ("reflection", _("Professional reflection")),
)

# guide @S7 III — the teacher's professional feedback, four directions (name, what is looked at)
FEEDBACK_DIRECTIONS = (
    ("chemistry", _("Chemistry subject knowledge"),
     _("The student's correct use of chemical concepts, laws, reaction equations and scientific explanations.")),
    ("design", _("Pedagogical design"),
     _("The student's skills of defining the lesson aim, organising tasks, choosing teaching methods and developing "
       "assessment criteria.")),
    ("digital", _("Using digital technologies"),
     _("The student's use of virtual labs, digital models and interactive tools in line with the learning aim.")),
    ("practice", _("Professional activity and reflection"),
     _("The student's skills of conducting a microlesson, answering students' questions, making pedagogical "
       "decisions and improving their own work.")),
)  # fmt: skip


# guide @S7 VI — the ten parts of the final portfolio
PARTS = (
    _("Basic details of the student"),
    _("Professional readiness results by the ICPAI model"),
    _("The register of theoretical, practical and lab works"),
    _("The collection of authorial lessons"),
    _("Results of the digital research practice"),
    _("Microlessons and the protocols of the professional trial"),
    _("The teacher's expert feedback"),
    _("The student's professional reflection"),
    _("The personal professional development map"),
    _("The final professional portfolio"),
)


class Portfolio(TimeStampedModel):
    """Section 7 — «ICPAI PROFESSIONAL PORTFOLIO» (guide @S7): the student's works of the earlier sections gathered,
    the ICPAI dynamics, the teacher's feedback, the reflection and the development map; assembled into versions and
    submitted to the teacher. One per programme enrolment. Research data — kept."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Being prepared")
        SUBMITTED = "submitted", _("Submitted to the teacher")
        ACCEPTED = "accepted", _("Accepted")
        NEEDS_MORE = "needs_more", _("Needs more work")
        REVISE = "revise", _("Needs revising")

    enrollment = models.OneToOneField(
        "programme.ProgrammeEnrollment", on_delete=models.PROTECT, related_name="portfolio", verbose_name=_("enrolment")
    )
    programme_name = models.CharField(_("education programme"), max_length=255, blank=True)
    study_year = models.CharField(_("study year"), max_length=64, blank=True)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    ai_check = models.JSONField(_("AI completeness check"), default=dict, blank=True)

    class Meta:
        verbose_name = _("portfolio")
        verbose_name_plural = _("portfolios")

    def __str__(self):
        return str(self.enrollment)

    @property
    def editable(self) -> bool:
        return self.status in (self.Status.DRAFT, self.Status.NEEDS_MORE, self.Status.REVISE)


class PortfolioVersion(models.Model):
    """«Assemble the portfolio» (@S7 VI): the ten parts frozen as they were. Never changed."""

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.PROTECT, related_name="versions", verbose_name=_("portfolio")
    )
    number = models.PositiveSmallIntegerField(_("number"))
    snapshot = models.JSONField(_("snapshot"))
    created_at = models.DateTimeField(_("assembled at"), auto_now_add=True)

    class Meta:
        ordering = ("portfolio", "-number")
        verbose_name = _("portfolio version")
        verbose_name_plural = _("portfolio versions")
        constraints = [models.UniqueConstraint(fields=("portfolio", "number"), name="portfolio_version_unique")]

    def __str__(self):
        return f"{self.portfolio} · v{self.number}"


class PortfolioFeedback(models.Model):
    """The teacher's professional feedback on a submitted portfolio (@S7 III): four directions, strengths, parts to
    improve, recommendations and the status. Shown in the student's cabinet and kept in the portfolio."""

    class Status(models.TextChoices):
        ACCEPTED = "accepted", _("Accepted")
        NEEDS_MORE = "needs_more", _("Needs more work")
        REVISE = "revise", _("Needs revising")

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.PROTECT, related_name="feedbacks", verbose_name=_("portfolio")
    )
    version = models.ForeignKey(
        PortfolioVersion, on_delete=models.PROTECT, related_name="feedbacks", verbose_name=_("version")
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="portfolio_feedbacks",
        verbose_name=_("teacher"),
    )
    chemistry = models.TextField(_("chemistry subject knowledge"), blank=True)
    design = models.TextField(_("pedagogical design"), blank=True)
    digital = models.TextField(_("using digital technologies"), blank=True)
    practice = models.TextField(_("professional activity and reflection"), blank=True)
    strengths = models.TextField(_("strengths of the work"), blank=True)
    improvements = models.TextField(_("parts that need improving"), blank=True)
    recommendations = models.TextField(_("professional recommendations"), blank=True)
    status = models.CharField(_("status of the work"), max_length=12, choices=Status.choices)
    created_at = models.DateTimeField(_("given at"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = _("teacher's feedback on a portfolio")
        verbose_name_plural = _("teachers' feedback on portfolios")

    def __str__(self):
        return f"{self.portfolio} · {self.get_status_display()}"


class Reflection(models.Model):
    """«My professional reflection» (@S7 IV): the student's answers to the seven questions — the AI writes none."""

    enrollment = models.OneToOneField(
        "programme.ProgrammeEnrollment",
        on_delete=models.PROTECT,
        related_name="reflection",
        verbose_name=_("enrolment"),
    )
    answers = models.JSONField(_("answers"), default=dict, help_text=_('{"1": "…", … "7": "…"}'))
    saved_at = models.DateTimeField(_("saved at"), auto_now=True)

    class Meta:
        verbose_name = _("professional reflection")
        verbose_name_plural = _("professional reflections")

    def __str__(self):
        return str(self.enrollment)


class DevelopmentPlanItem(models.Model):
    """«My professional development trajectory» (@S7 V): one direction of the personal development map — the
    planned action, the expected result, and (after «Update the development result») what was done."""

    enrollment = models.ForeignKey(
        "programme.ProgrammeEnrollment",
        on_delete=models.PROTECT,
        related_name="plan_items",
        verbose_name=_("enrolment"),
    )
    direction = models.CharField(_("direction"), max_length=16, choices=DIRECTIONS)
    action = models.TextField(_("planned action"), blank=True)
    expected = models.TextField(_("expected result"), blank=True)
    done = models.BooleanField(_("done"), default=False)
    result = models.TextField(_("result"), blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ("enrollment", "pk")
        verbose_name = _("development plan item")
        verbose_name_plural = _("development plan items")
        constraints = [models.UniqueConstraint(fields=("enrollment", "direction"), name="plan_item_unique")]

    def __str__(self):
        return f"{self.enrollment} · {self.get_direction_display()}"


class PortfolioEvent(models.Model):
    """The research log of section 7: reflection and plan saves, assembling, submitting, the teacher's feedback."""

    class Action(models.TextChoices):
        REFLECTION = "reflection", _("Reflection saved")
        PLAN = "plan", _("Development goals set")
        RESULTS = "results", _("Development results updated")
        ASSEMBLED = "assembled", _("Portfolio assembled")
        SUBMITTED = "submitted", _("Submitted to the teacher")
        FEEDBACK = "feedback", _("Teacher's feedback")
        CHECKED = "checked", _("AI completeness check")

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.PROTECT, related_name="events", verbose_name=_("portfolio")
    )
    action = models.CharField(_("action"), max_length=12, choices=Action.choices)
    data = models.JSONField(_("data"), default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("by"),
    )
    created_at = models.DateTimeField(_("at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = _("portfolio event")
        verbose_name_plural = _("portfolio events")

    def __str__(self):
        return f"{self.portfolio} · {self.get_action_display()}"
