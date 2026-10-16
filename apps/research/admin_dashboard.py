"""Admin dashboard (UNFOLD["DASHBOARD_CALLBACK"]): platform-wide numbers for the administrator."""

from datetime import timedelta

from django.db.models import Min
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import User
from apps.certificates.models import Certificate
from apps.courses.models import Course, Enrollment
from apps.labs.models import LabAttempt
from apps.practice.models import PracticeSubmission
from apps.progress.models import StageProgress


def _card(title, value, note="", url=""):
    return {"title": title, "value": value, "note": note, "url": url}


def dashboard_callback(request, context):
    week = timezone.now() - timedelta(days=7)
    active = (
        StageProgress.objects.filter(updated_at__gte=week, enrollment__status=Enrollment.Status.ACTIVE)
        .values("enrollment__student")
        .distinct()
        .count()
    )
    students = User.objects.filter(role=User.Role.STUDENT, is_active=True).count()
    awaiting = PracticeSubmission.objects.filter(status=PracticeSubmission.Status.NEEDS_REVIEW)
    oldest = awaiting.aggregate(m=Min("submitted_at"))["m"]
    context["kpis"] = [
        _card(_("Students"), students, _("%(n)s active in the last 7 days") % {"n": active},
              reverse("admin:accounts_user_changelist") + "?role__exact=student"),
        _card(_("Teachers"), User.objects.filter(role=User.Role.TEACHER, is_active=True).count(), "",
              reverse("admin:accounts_user_changelist") + "?role__exact=teacher"),
        _card(_("Courses"), Course.objects.filter(status=Course.Status.PUBLISHED).count(),
              _("published of %(n)s") % {"n": Course.objects.count()}, reverse("admin:courses_course_changelist")),
        _card(_("Active enrolments"), Enrollment.objects.filter(status=Enrollment.Status.ACTIVE).count(),
              _("%(n)s completed") % {"n": Enrollment.objects.filter(status=Enrollment.Status.COMPLETED).count()},
              reverse("admin:courses_enrollment_changelist")),
        _card(_("Lab attempts"), LabAttempt.objects.count(),
              _("%(n)s with the analysis sent") % {"n": LabAttempt.objects.filter(status=LabAttempt.Status.ANALYSED).count()},
              reverse("admin:labs_labattempt_changelist")),
        _card(_("Works awaiting a teacher"), awaiting.count(),
              _("the oldest sent %(date)s") % {"date": timezone.localtime(oldest).strftime("%d.%m.%Y")} if oldest else "",
              reverse("admin:practice_practicesubmission_changelist") + "?status__exact=needs_review"),
        _card(_("Certificates issued"), Certificate.objects.count(), "",
              reverse("admin:certificates_certificate_changelist")),
    ]  # fmt: skip
    context["quick_links"] = [
        (_("Teacher cabinet"), reverse("teacher:dashboard")),
        (_("Statistics"), reverse("research:analytics")),
        (_("Research data"), reverse("research:dashboard")),
    ]
    return context
