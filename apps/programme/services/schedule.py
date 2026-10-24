"""Section 8's deadlines and notifications (guide @S8 IV): the teacher sets a group's hand-in and trial dates; the
platform sends the five notifications of the guide — a new task, the hand-in deadline is near (two days before, by the
daily command ``icpai_reminders``), the trial date is set, a new expert opinion, trying it out again."""

from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.feedback import services as feedback
from apps.feedback.models import Notification
from apps.pedagogy.models import Lesson

from ..models import ProgrammeEnrollment, SectionSchedule

K = Notification.Kind
REMIND_DAYS = 2
# the notification texts of the guide (@S8 IV 1–5; verbatim in the kk translation)
TEXTS = {
    K.ICPAI_TASK: _("Dear student! The stage of developing an independent authorial lesson is open for you. Choose "
                    "the lesson topic and start the pedagogical design."),
    K.ICPAI_DEADLINE: _("The deadline for handing in the authorial lesson project is near. Check how far the work is "
                        "done and complete the parts needed."),
    K.ICPAI_TRIAL: _("The professional trial date of your authorial lesson is set. Check the lesson stages and get "
                     "ready for the trial."),
    K.ICPAI_EXPERT: _("Айгерім has left a new expert opinion on your lesson project. Read the remarks found."),
    K.ICPAI_RETRIAL: _("The stage of trying the corrected version of the authorial lesson out again is open."),
}  # fmt: skip


def _url():
    return reverse("student:independent_home")


def notify(student, kind):
    return feedback.notify(student, kind, str(TEXTS[kind]), _url())


def notify_task_once(student):
    """The first notification when the student comes to section 8."""
    if not Notification.objects.filter(user=student, kind=K.ICPAI_TASK).exists():
        notify(student, K.ICPAI_TASK)


def schedule_for(enrollment, section) -> SectionSchedule | None:
    if enrollment.group_id is None:
        return None
    return SectionSchedule.objects.filter(section=section, group_id=enrollment.group_id).first()


def _students(section, group):
    return [e.student for e in ProgrammeEnrollment.objects.filter(programme=section.programme, group=group)
            .select_related("student")]  # fmt: skip


@transaction.atomic
def set_schedule(section, group, teacher, *, hand_in_on=None, trial_on=None) -> SectionSchedule:
    """The teacher's dates for a group; a new or changed trial date is announced to the group's students."""
    schedule = SectionSchedule.objects.filter(section=section, group=group).first()
    old_trial = schedule.trial_on if schedule else None
    schedule, _created = SectionSchedule.objects.update_or_create(
        section=section, group=group, defaults={"hand_in_on": hand_in_on, "trial_on": trial_on, "set_by": teacher}
    )
    if trial_on and trial_on != old_trial:
        for student in _students(section, group):
            transaction.on_commit(lambda s=student: notify(s, K.ICPAI_TRIAL))
    return schedule


def remind(today=None) -> int:
    """Daily: two days before the hand-in date, students whose lesson is not submitted yet get the reminder (once a
    day at most). Returns the number of notifications sent."""
    today = today or timezone.localdate()
    sent = 0
    for schedule in SectionSchedule.objects.filter(hand_in_on=today + timedelta(days=REMIND_DAYS)):
        for student in _students(schedule.section, schedule.group):
            lesson = Lesson.objects.filter(owner=student, kind=Lesson.Kind.INDEPENDENT).order_by("-cycle").first()
            if lesson and lesson.status != Lesson.Status.DRAFT:
                continue
            if Notification.objects.filter(user=student, kind=K.ICPAI_DEADLINE, created_at__date=today).exists():
                continue
            notify(student, K.ICPAI_DEADLINE)
            sent += 1
    return sent


def countdown(schedule, today=None) -> dict | None:
    """The nearest date ahead (hand-in or trial) for «Pay attention to the deadline!»."""
    if schedule is None:
        return None
    today = today or timezone.localdate()
    dates = [(d, k) for d, k in ((schedule.hand_in_on, "hand_in"), (schedule.trial_on, "trial")) if d and d >= today]
    if not dates:
        return None
    date, kind = min(dates)
    return {"date": date, "kind": kind, "days": (date - today).days}
