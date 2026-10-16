"""Teacher: the practice grading queue, the grading page and comments on works (STEP-11)."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.courses import selectors as course_selectors
from apps.feedback import selectors as feedback_selectors
from apps.feedback import services as feedback
from apps.labs.models import LabAttempt
from apps.practice import selectors as practice_selectors
from apps.practice import services as practice
from apps.practice.models import PracticeSubmission

from .views import teacher_only

S = PracticeSubmission.Status
TABS = (
    (S.NEEDS_REVIEW, gettext_lazy("To check")),
    (practice_selectors.SAMPLE, gettext_lazy("Spot-check")),
    (S.GRADED, gettext_lazy("Graded by AI")),
    (S.RETURNED, gettext_lazy("Returned")),
)


def _enrollment_ids(request, course=None):
    return list(course_selectors.teacher_enrollments(request.user, course).values_list("pk", flat=True))


@teacher_only
def queue(request):
    status = request.GET.get("status") or S.NEEDS_REVIEW
    if status not in dict(TABS):
        raise Http404
    courses = list(course_selectors.teacher_courses(request.user))
    course = next((c for c in courses if c.slug == request.GET.get("course")), None)
    ids = _enrollment_ids(request, course)
    tabs = [
        {"status": value, "label": label, "count": practice_selectors.grading_queue(ids, value).count()}
        for value, label in TABS
    ]
    return render(
        request,
        "teacher/grading.html",
        {
            "tabs": tabs,
            "status": status,
            "courses": courses,
            "course": course,
            "submissions": practice_selectors.grading_queue(ids, status)[:200],
        },
    )


def _submission(request, pk):
    return get_object_or_404(
        PracticeSubmission.objects.select_related(
            "enrollment__student", "enrollment__group", "stage__topic__module__course"
        ),
        pk=pk,
        enrollment__in=course_selectors.teacher_enrollments(request.user),
    )


def _decimal(value, top) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", ".").strip() or "0")
    except InvalidOperation:
        number = Decimal(0)
    return min(max(number, Decimal(0)), Decimal(top))


def _decisions(request, rows) -> dict:
    """Criterion points (or plain points for an answer without a rubric) from the grading form."""
    decisions = {}
    for row in rows:
        if not row["open"]:
            continue
        answer = row["answer"]
        if row["criteria"]:
            criteria = [
                {
                    "criterion_id": c["criterion"].pk,
                    "points": float(
                        _decimal(request.POST.get(f"c_{answer.pk}_{c['criterion'].pk}"), c["criterion"].points)
                    ),
                }
                for c in row["criteria"]
            ]
            points = sum(Decimal(str(c["points"])) for c in criteria)
        else:
            criteria, points = [], _decimal(request.POST.get(f"p_{answer.pk}"), answer.item.points)
        decisions[answer.pk] = {
            "points": min(points, answer.item.points),
            "criteria": criteria,
            "reason": request.POST.get(f"r_{answer.pk}", "").strip(),
        }
    return decisions


def _next_in_queue(request, submission):
    ids = _enrollment_ids(request)
    nxt = practice_selectors.grading_queue(ids, S.NEEDS_REVIEW).exclude(pk=submission.pk).first()
    return reverse("teacher:grading_detail", args=[nxt.pk]) if nxt else reverse("teacher:grading")


@teacher_only
def detail(request, pk):
    submission = _submission(request, pk)
    rows = practice_selectors.review_rows(submission)
    if request.method == "POST":
        if submission.status == S.GRADING:
            messages.error(request, _("The AI is still grading this work. Try again in a minute."))
            return redirect("teacher:grading_detail", submission.pk)
        comment = request.POST.get("teacher_comment", "").strip()
        if request.POST.get("action") == "return":
            practice.return_submission(submission, request.user, comment)
            messages.success(request, _("The work is returned to the student; the attempt is given back."))
        else:
            practice.teacher_grade(submission, request.user, _decisions(request, rows), comment)
            messages.success(request, _("The grade is confirmed."))
        return redirect(_next_in_queue(request, submission))
    feedback.mark_thread_read(request.user, submission)
    others = (
        PracticeSubmission.objects.filter(enrollment=submission.enrollment, stage=submission.stage)
        .exclude(pk=submission.pk)
        .order_by("-attempt_no")
    )
    return render(
        request,
        "teacher/grading_detail.html",
        {
            "submission": submission,
            "student": submission.enrollment.student,
            "rows": rows,
            "others": others,
            "thread": feedback_selectors.thread(submission),
            "comment_target": {"kind": "practice", "id": submission.pk},
        },
    )


# --- comments ------------------------------------------------------------------------------


def comment_target(kind, pk, enrollments):
    """A work the user may comment on, by kind and id, inside the given enrolments (or 404)."""
    if kind == "practice":
        return get_object_or_404(PracticeSubmission.objects.select_related("stage"), pk=pk, enrollment__in=enrollments)
    if kind == "lab":
        return get_object_or_404(LabAttempt.objects.select_related("stage"), pk=pk, enrollment__in=enrollments)
    raise Http404


def teacher_url_of(target) -> str:
    if isinstance(target, PracticeSubmission):
        return reverse("teacher:grading_detail", args=[target.pk])
    return reverse("teacher:lab_log", args=[target.user_id, target.pk])


@require_POST
@teacher_only
def comment(request):
    target = comment_target(
        request.POST.get("kind"), request.POST.get("id"), course_selectors.teacher_enrollments(request.user)
    )
    parent = feedback_selectors.thread_comment(target, request.POST.get("parent"))
    stage = target.stage
    try:
        feedback.add_comment(
            request.user,
            target,
            request.POST.get("body", ""),
            parent=parent,
            student_url=(course_selectors.stage_url(stage) + "#comments") if stage else "",
            teacher_url=teacher_url_of(target),
        )
    except feedback.CommentError as exc:
        messages.error(request, str(exc))
    nxt = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = teacher_url_of(target)
    return redirect(nxt + "#comments")
