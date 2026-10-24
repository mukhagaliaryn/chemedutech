from django.db import models
from django.utils.translation import gettext_lazy as _


class Check(models.Model):
    """The AI assistant in the checker mode (guide @S6 III): for the microlesson as it was — each stage and each of the
    seven criteria marked only «correct» or «wrong», no explanation. ``fingerprint`` — the content checked; a change
    of the content makes the check out of date. Research data — kept."""

    CRITERIA = (
        ("aim", _("The lesson aim is placed correctly")),
        ("explanation", _("The explanation is put in the right stage")),
        ("chemistry", _("The chemical formulas and equations are correct")),
        ("task_aim", _("The task fits the stated learning aim")),
        ("assessment", _("The assessment criterion is connected with the task")),
        ("time", _("The lesson stages fit the time")),
        ("complete", _("The lesson structure is complete")),
    )

    lesson = models.ForeignKey(
        "pedagogy.Lesson", on_delete=models.PROTECT, related_name="checks", verbose_name=_("lesson")
    )
    fingerprint = models.CharField(_("content checked"), max_length=64)
    stages = models.JSONField(_("verdicts by stage"), default=dict, help_text=_('{"1": "ok", "2": "wrong", …}'))
    criteria = models.JSONField(_("verdicts by criterion"), default=dict)
    message_id = models.PositiveIntegerField(_("AI message"), null=True, blank=True)
    created_at = models.DateTimeField(_("checked at"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = _("AI check")
        verbose_name_plural = _("AI checks")

    def __str__(self):
        return f"{self.lesson} · {self.created_at:%d.%m %H:%M}"

    @property
    def passed(self) -> bool:
        return bool(self.stages) and all(v == "ok" for v in self.stages.values())
