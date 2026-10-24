"""Student cabinet: my courses, course map, topic page and the stage player (ARCHITECTURE §8, STEP-07).

Thin views: access and progress go through progress.services, quizzes through assessments.services.
Teachers and admins see the same pages in preview mode (everything open, nothing recorded).
"""

import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts import services as account_services
from apps.accounts.forms import ProfileForm
from apps.assessments import selectors as quiz_selectors
from apps.assessments import services as quiz_services
from apps.assessments.forms import collect_answers
from apps.assessments.models import QuizAttempt
from apps.assessments.views import result_context, take_context
from apps.core.permissions import ADMIN, STUDENT, TEACHER, has_role, home_url_for, role_required
from apps.courses import selectors as course_selectors
from apps.courses import services as course_services
from apps.courses.models import Course, Stage
from apps.feedback import selectors as feedback_selectors
from apps.feedback import services as feedback
from apps.labs import services as lab_services
from apps.labs.engine import get_lab
from apps.labs.models import LabAttempt
from apps.labs.views import analysis_payload, lab_page
from apps.practice import forms as practice_forms
from apps.practice import services as practice
from apps.practice.models import PracticeSubmission
from apps.programme import services as programme
from apps.progress import selectors as progress_selectors
from apps.progress import services as progress
from apps.progress.grading import grade_for
from apps.progress.services import benchmark

from . import cabinet, learning, sections
from .learning import S

LEARN = "layouts/learn.html"


# --- cabinet: dashboard, gradebook, certificates, profile ---------------------------


def _student_enrollments(request):
    course_services.sync_student_enrollments(request.user)
    enrollments = cabinet.enrollments_of(request.user)
    enrollment = cabinet.pick(enrollments, request.GET.get("course"))
    if enrollment:
        progress.recalculate(enrollment)
    return enrollments, enrollment


@login_required
def dashboard(request):
    if not has_role(request.user, STUDENT):
        return redirect(home_url_for(request.user))
    enrollments, enrollment = _student_enrollments(request)
    programme_enrollment = programme.refresh(request.user)
    if programme_enrollment:  # the ICPAI home: the guide and the sections instead of the key figures (@S0-RULES)
        return render(request, "student/home.html", sections.home_context(request.user, programme_enrollment))
    context = {"enrollments": enrollments}
    if enrollment:
        context.update(cabinet.dashboard(request.user, enrollment))
    return render(request, "student/dashboard.html", context)


@role_required(STUDENT)
def search(request):
    q = request.GET.get("q", "").strip()[:100]
    rows = cabinet.search(cabinet.enrollments_of(request.user), q) if q else []
    return render(request, "student/search.html", {"search_q": q, "rows": rows})


@role_required(STUDENT)
def results(request):
    enrollments, enrollment = _student_enrollments(request)
    context = {"enrollments": enrollments}
    if enrollment:
        context.update(cabinet.gradebook(enrollment))
    return render(request, "student/results.html", context)


@role_required(STUDENT)
def certificates(request):
    course_services.sync_student_enrollments(request.user)
    enrollments = cabinet.enrollments_of(request.user)
    for e in enrollments:
        progress.recalculate(e)
    return render(request, "student/certificates.html", {"rows": cabinet.certificate_rows(enrollments)})


@login_required
def profile(request):
    """Personal data, interface language and password — for every role (the layout follows the role)."""
    user = request.user
    which = request.POST.get("form") if request.method == "POST" else None
    profile_form = ProfileForm(user, request.POST if which == "profile" else None)
    password_form = PasswordChangeForm(user, request.POST if which == "password" else None)
    password_form.fields["old_password"].widget.attrs.pop("autofocus", None)
    if which == "profile" and profile_form.is_valid():
        changed = account_services.update_profile(user, profile_form.cleaned_data)
        response = redirect("student:profile")
        if "language" in changed:
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, user.language, max_age=settings.LANGUAGE_COOKIE_AGE)
        with translation.override(user.language):
            messages.success(request, _("Profile saved."))
        return response
    if which == "password" and password_form.is_valid():
        password_form.save()
        update_session_auth_hash(request, user)
        messages.success(request, _("Password changed."))
        return redirect("student:profile")
    return render(
        request,
        "student/profile.html",
        {
            "layout": "layouts/teacher.html" if has_role(user, TEACHER, ADMIN) else "layouts/student.html",
            "profile_form": profile_form,
            "password_form": password_form,
            "student_profile": getattr(user, "student_profile", None),
        },
    )


# --- courses ------------------------------------------------------------------------


@login_required
def courses(request):
    user = request.user
    course_services.sync_student_enrollments(user)
    rows = []
    for course in course_selectors.courses_for(user).order_by("title"):
        place = learning.resolve(request, course.slug)
        result = None
        if place.enrollment:
            progress.recalculate(place.enrollment)
            result = progress_selectors.course_result(place.enrollment)
            place.progress = progress_selectors.stage_progress_map(place.enrollment)
        rows.append(
            {"course": course, "result": result, "next": learning.continue_target(place), "preview": place.preview}
        )
    open_courses = course_selectors.open_courses().exclude(pk__in=[r["course"].pk for r in rows])
    return render(
        request,
        "student/courses.html",
        {"rows": rows, "open_courses": open_courses if has_role(user, STUDENT) else []},
    )


@require_POST
@role_required(STUDENT)
def enroll(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    try:
        course_services.self_enroll(request.user, course)
    except course_services.EnrollmentError as exc:
        messages.error(request, str(exc))
        return redirect("student:courses")
    return redirect("student:course", course.slug)


@login_required
def course(request, course_slug):
    place = learning.resolve(request, course_slug)
    result = None
    if place.enrollment:
        progress.recalculate(place.enrollment)
        place.progress = progress_selectors.stage_progress_map(place.enrollment)
        result = progress_selectors.course_result(place.enrollment)
    modules = learning.course_map(place)
    total = sum(t["required"] for m in modules for t in m["topics"])
    passed = sum(t["passed"] for m in modules for t in m["topics"])
    nxt = learning.continue_target(place)
    counts = learning.map_filters(modules, nxt.topic if nxt else None)
    return render(
        request,
        "student/course_map.html",
        {
            "place": place,
            "course": place.course,
            "modules": modules,
            "result": result,
            "grade": grade_for(result.current_percent) if result and result.current_percent is not None else None,
            "stages_total": total,
            "stages_passed": passed,
            "next": nxt,
            "counts": counts,
            "teachers": place.course.teachers.all(),
            "benchmark": benchmark.summary(place.enrollment) if place.enrollment else {},
        },
    )


# --- the course's pre/post knowledge test (research, STEP-22) ----------------------------------


def _benchmark_place(request, course_slug, phase):
    if phase not in benchmark.PHASES:
        raise Http404
    place = learning.resolve(request, course_slug)
    if place.preview or benchmark.benchmark_quiz(place.course) is None:
        raise Http404
    return place


def _benchmark_url(place, phase):
    return reverse("student:benchmark", args=[place.course.slug, phase])


@login_required
def benchmark_page(request, course_slug, phase):
    """Intro → the single attempt (the usual test page, no answers shown) → «done» with the overall percent."""
    place = _benchmark_place(request, course_slug, phase)
    enrollment = place.enrollment
    quiz = benchmark.benchmark_quiz(place.course)
    attempt = benchmark.phase_attempt(enrollment, phase, quiz)
    if attempt and not attempt.is_finished and quiz_services.is_expired(attempt):
        attempt = quiz_services.submit_attempt(attempt, {}, allow_late=True)
    course_url = reverse("student:course", args=[place.course.slug])
    if attempt and not attempt.is_finished:
        submit_url = reverse("student:benchmark_submit", args=[place.course.slug, phase, attempt.pk])
        return render(
            request, "assessments/take.html", take_context(quiz, attempt, submit_url, course_url, place.course.title)
        )
    return render(
        request,
        "student/benchmark.html",
        {
            "place": place,
            "course": place.course,
            "course_url": course_url,
            "quiz": quiz,
            "phase": phase,
            "state": benchmark.phase_state(enrollment, phase),
            "attempt": attempt,
            "question_count": quiz.questions_per_attempt or quiz.questions.filter(is_active=True).count(),
        },
    )


@require_POST
@login_required
def benchmark_start(request, course_slug, phase):
    place = _benchmark_place(request, course_slug, phase)
    try:
        benchmark.start(place.enrollment, phase)
    except quiz_services.AttemptError as exc:
        messages.error(request, str(exc))
    return redirect(_benchmark_url(place, phase))


@require_POST
@login_required
def benchmark_submit(request, course_slug, phase, attempt_id):
    place = _benchmark_place(request, course_slug, phase)
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user, phase=phase)
    try:
        quiz_services.submit_attempt(attempt, collect_answers(attempt, request.POST))
    except quiz_services.AttemptError as exc:
        messages.info(request, str(exc))
    return redirect(_benchmark_url(place, phase))


# --- topic and stage ----------------------------------------------------------------


def _learn_context(place, stages, current=None):
    passed = sum(1 for s in stages if s.is_required and learning.stage_status(place, s) == S.PASSED)
    return {
        "place": place,
        "course": place.course,
        "topic": place.topic,
        "stepper": learning.stepper(place, place.topic, stages, current),
        "topic_passed": passed,
        "topic_required": sum(1 for s in stages if s.is_required),
        "course_url": reverse("student:course", args=[place.course.slug]),
    }


@login_required
def topic(request, course_slug, topic_number):
    place = learning.resolve(request, course_slug, topic_number)
    if place.enrollment:
        progress.recalculate(place.enrollment)
        place.progress = progress_selectors.stage_progress_map(place.enrollment)
    stages = learning.ordered_stages(place.topic)
    target = next((s for s in stages if learning.stage_status(place, s) in (S.AVAILABLE, S.IN_PROGRESS)), None)
    result = progress_selectors.topic_results_map(place.enrollment).get(place.topic.pk) if place.enrollment else None
    if result and result.status == "locked" and not any(learning.stage_status(place, s) != S.LOCKED for s in stages):
        return _locked(request, place, stages[0] if stages else None, stages)
    context = _learn_context(place, stages)
    context.update(
        {
            "rows": [
                {
                    "stage": s,
                    "status": learning.stage_status(place, s),
                    "sp": place.progress.get(s.pk),
                    "url": learning.stage_url(s),
                }
                for s in stages
            ],
            "target": target,
            "result": result,
        }
    )
    return render(request, "student/topic.html", context)


def _locked(request, place, stage, stages):
    blocking = progress.blocking_stage(place.enrollment, stage) if stage is not None else None
    context = _learn_context(place, stages, stage)
    context.update(
        {
            "stage": stage,
            "blocking": blocking,
            "blocking_url": learning.stage_url(blocking) if blocking else context["course_url"],
            "blocking_status": learning.stage_status(place, blocking) if blocking else None,
        }
    )
    return render(request, "student/locked.html", context, status=200)


def _open_stage(request, course_slug, topic_number, stage_pk):
    """(place, stages) for an open stage, or a response (the «finish … first» page)."""
    place = learning.resolve(request, course_slug, topic_number, stage_pk)
    stages = learning.ordered_stages(place.topic)
    if not place.preview and benchmark.pretest_required(place.enrollment):
        messages.info(request, _("Before the first stage, take the short entry knowledge test."))
        return place, stages, redirect(_benchmark_url(place, benchmark.PRE))
    if not place.preview and not progress.can_access(place.enrollment, place.stage):
        return place, stages, _locked(request, place, place.stage, stages)
    return place, stages, None


@login_required
def stage(request, course_slug, topic_number, stage_pk):
    place, stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    stage = place.stage
    if not place.preview:
        progress.start_stage(place.enrollment, stage)
        place.progress = progress_selectors.stage_progress_map(place.enrollment)
    sp = place.progress.get(stage.pk)
    quiz = progress.stage_quiz(stage)
    context = _learn_context(place, stages, stage)
    context.update(
        {
            "stage": stage,
            "sp": sp,
            "status": learning.stage_status(place, stage),
            "content": stage.content,
            "quiz": quiz,
            "next": learning.next_place(place, stage),
            "urls": {
                name: learning.stage_url(stage, f"student:{name}")
                for name in ("material_done", "watch", "ping", "quiz_take", "quiz_retry")
            },
        }
    )
    if quiz:
        context.update(_quiz_panel(request, place, stage, quiz, sp))
    if stage.kind == Stage.Kind.PRACTICE and stage.content:
        context.update(_practice_context(place, stage))
        if context["latest"] and not place.preview:
            feedback.mark_thread_read(request.user, context["latest"])
    if stage.kind == Stage.Kind.LAB and stage.content:
        rows = progress.lab_experiments(place.enrollment, stage)
        if not place.preview and rows and all(r["done"] for r in rows) and context["status"] != S.PASSED:
            progress.record_lab_result(place.enrollment, stage)  # e.g. the analysis was sent from another tab
            place.progress = progress_selectors.stage_progress_map(place.enrollment)
            context.update(sp=place.progress.get(stage.pk), status=learning.stage_status(place, stage))
        for row in rows:
            row["url"] = reverse(
                "student:lab_run", args=[place.course.slug, place.topic.number, stage.pk, row["spec"].key]
            )
        context["experiments"] = rows
        if not place.preview:
            context["lab_threads"] = _lab_threads(request, place, stage)
    return render(request, "student/stage.html", context)


def _lab_threads(request, place, stage) -> list[dict]:
    """Teacher comments on the student's attempts in this lab stage (read on display)."""
    attempts = list(LabAttempt.objects.filter(enrollment=place.enrollment, stage=stage).order_by("-started_at"))
    counts = feedback_selectors.comment_counts(attempts)
    lab = get_lab(stage.content.lab_key)
    threads = []
    for attempt in attempts:
        if not counts.get(attempt.pk):
            continue
        spec = lab.experiment(attempt.experiment_key) if lab else None
        threads.append(
            {
                "attempt": attempt,
                "title": f"{spec.number}. {spec.title}" if spec else attempt.experiment_key,
                "thread": feedback_selectors.thread(attempt),
                "target": {"kind": "lab", "id": attempt.pk},
            }
        )
        feedback.mark_thread_read(request.user, attempt)
    return threads


@require_POST
@login_required
def comment(request, course_slug, topic_number, stage_pk):
    """A student's comment or reply on their own work in this stage."""
    place, _stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied or place.preview:
        raise Http404
    kind, pk = request.POST.get("kind"), request.POST.get("id")
    if kind == "practice":
        target = get_object_or_404(PracticeSubmission, pk=pk, enrollment=place.enrollment, stage=place.stage)
        teacher_url = reverse("teacher:grading_detail", args=[target.pk])
    elif kind == "lab":
        target = get_object_or_404(LabAttempt, pk=pk, enrollment=place.enrollment, stage=place.stage)
        teacher_url = reverse("teacher:lab_log", args=[request.user.pk, target.pk])
    else:
        raise Http404
    stage_page = learning.stage_url(place.stage)
    try:
        feedback.add_comment(
            request.user,
            target,
            request.POST.get("body", ""),
            parent=feedback_selectors.thread_comment(target, request.POST.get("parent")),
            student_url=stage_page + "#comments",
            teacher_url=teacher_url,
        )
    except feedback.CommentError as exc:
        messages.error(request, str(exc))
    return redirect(stage_page + "#comments")


def _practice_context(place, stage):
    task = stage.content
    submissions = (
        list(PracticeSubmission.objects.filter(enrollment=place.enrollment, stage=stage).order_by("-attempt_no"))
        if place.enrollment
        else []
    )
    latest = submissions[0] if submissions else None
    left = practice.attempts_left(place.enrollment, task) if place.enrollment else task.max_attempts
    grading = latest is not None and latest.status == PracticeSubmission.Status.GRADING
    answers = list(latest.answers.select_related("item", "ai_grade").order_by("item__order")) if latest else []
    rows = practice_forms.widget_rows(task, latest)
    by_item = {a.item_id: a for a in answers}
    for row in rows:
        row["answer"] = by_item.get(row["item"].pk)
        if row["answer"] is not None and row["item"].kind == "open":
            row["criteria"] = _criteria_rows(row["answer"])
    return {
        "task": task,
        "rows": rows,
        "max_points": sum(r["item"].points for r in rows),
        "latest": latest,
        "latest_answers": answers,
        "practice_left": left,
        "grading": grading,
        "can_submit": not place.preview and not grading and left > 0,
        "counted": practice.counted_submission(place.enrollment, task) if place.enrollment else None,
        "thread": feedback_selectors.thread(latest) if latest else [],
        "comment_target": {"kind": "practice", "id": latest.pk} if latest else None,
        "practice_urls": {
            "submit": learning.stage_url(stage, "student:practice_submit"),
            "status": reverse(
                "student:practice_status",
                args=[place.course.slug, place.topic.number, stage.pk, latest.pk],
            )
            if latest
            else "",
        },
    }


def _criteria_rows(answer) -> list[dict]:
    """The AI's points per rubric criterion of an open answer, with the criterion text and its maximum."""
    grade = getattr(answer, "ai_grade", None)
    rubric = getattr(answer.item, "rubric", None)
    if grade is None or rubric is None:
        return []
    criteria = {c.pk: c for c in rubric.criteria.all()}
    rows = []
    for score in grade.criteria_scores:
        criterion = criteria.get(score.get("criterion_id"))
        if criterion is None:
            continue
        points = Decimal(str(score.get("points") or 0))
        rows.append(
            {
                "text": criterion.text,
                "reason": score.get("reason", ""),
                "points": points,
                "max": criterion.points,
                "tone": "ok" if points >= criterion.points else ("part" if points > 0 else "no"),
            }
        )
    return rows


@require_POST
@login_required
def practice_submit(request, course_slug, topic_number, stage_pk):
    place, _stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    task = place.stage.content
    if place.stage.kind != Stage.Kind.PRACTICE or task is None:
        raise Http404
    stage_page = learning.stage_url(place.stage)
    if place.preview:
        messages.info(request, _("Preview: answers are not saved."))
        return redirect(stage_page)
    try:
        practice.submit(
            place.enrollment, task, practice_forms.collect_answers(task, request.POST), request.FILES.get("file")
        )
    except practice.SubmissionError as exc:
        messages.error(request, str(exc))
    return redirect(f"{stage_page}#result")


@login_required
def practice_status(request, course_slug, topic_number, stage_pk, submission_id):
    """HTMX polling while the AI grades: the «grading» note again, or a page refresh when it is done."""
    place, _stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    submission = get_object_or_404(PracticeSubmission, pk=submission_id, enrollment=place.enrollment, stage=place.stage)
    if submission.status == PracticeSubmission.Status.GRADING:
        return render(request, "student/partials/practice_grading.html", {"status_url": request.path})
    response = render(request, "student/partials/practice_grading.html", {"status_url": "", "done": True})
    response["HX-Refresh"] = "true"
    return response


def _quiz_panel(request, place, stage, quiz, sp):
    user = request.user
    last = quiz_selectors.last_attempt(user, quiz)
    open_attempt = last if last and not last.is_finished else None
    last_attempt = last if last and last.is_finished else None
    context = {
        "quiz_open": place.preview or progress.quiz_is_open(place.enrollment, stage, sp),
        "open_attempt": open_attempt,
        "last_attempt": last_attempt,
        "counted": quiz_selectors.counted_attempt(user, quiz),
        "attempts_left": quiz_services.attempts_left(user, quiz),
        "question_count": quiz.questions_per_attempt or quiz.questions.filter(is_active=True).count(),
    }
    if quiz.instant_feedback and open_attempt and not quiz_services.is_expired(open_attempt):
        rows = _inline_rows(place, open_attempt)
        context.update(
            inline_rows=rows,
            inline_current=next((i for i, r in enumerate(rows) if r["answer"] is None), len(rows) - 1),
            submit_url=_quiz_submit_url(place, open_attempt),
        )
    if last_attempt and request.GET.get("result") == str(last_attempt.pk):
        rows = quiz_selectors.review_rows(last_attempt)
        context["result_dialog"] = {
            "attempt": last_attempt,
            "correct": sum(1 for r in rows if r["answer"] and r["answer"].is_correct),
            "total": len(rows),
        }
    return context


@require_POST
@login_required
def material_done(request, course_slug, topic_number, stage_pk):
    place, _stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    stage = place.stage
    allowed = stage.kind == Stage.Kind.THEORY or (
        stage.kind == Stage.Kind.VIDEO and not (stage.content and stage.content.has_source)
    )
    if not allowed:
        raise Http404  # a video with a source is completed by watching it
    if not place.preview:
        progress.complete_material(place.enrollment, stage)
    return redirect(f"{learning.stage_url(stage)}#quiz")


@require_POST
@login_required
def watch(request, course_slug, topic_number, stage_pk):
    place, _stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied or place.stage.kind != Stage.Kind.VIDEO or not place.stage.content:
        return JsonResponse({"error": "not_available"}, status=403)
    try:
        percent = int(json.loads(request.body or b"{}").get("percent", 0))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    if place.preview:
        return JsonResponse({"percent": percent, "done": False, "preview": True})
    sp = progress.record_watch(place.enrollment, place.stage, percent, place.stage.content.min_watch_percent)
    return JsonResponse({"percent": sp.material_percent, "done": sp.material_done_at is not None})


@require_POST
@login_required
def ping(request, course_slug, topic_number, stage_pk):
    """Time on a stage: the page sends a beat every 30 s while it is visible."""
    place, _stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if not denied and not place.preview:
        progress.add_time(place.enrollment, place.stage, 30)
    return JsonResponse({"ok": True})


# --- lab inside a stage -------------------------------------------------------------


def _lab_stage(request, course_slug, topic_number, stage_pk, experiment_key):
    place, _stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return place, None, None, denied
    content = place.stage.content
    if place.stage.kind != Stage.Kind.LAB or content is None:
        raise Http404
    rows = progress.lab_experiments(place.enrollment, place.stage)
    row = next((r for r in rows if r["spec"].key == experiment_key), None)
    if row is None:
        raise Http404
    if not row["open"]:
        messages.info(request, _("Experiments open one after another: finish the previous one and send its analysis."))
        return place, rows, row, redirect(learning.stage_url(place.stage))
    return place, rows, row, None


@login_required
def lab_run(request, course_slug, topic_number, stage_pk, experiment_key):
    place, rows, row, denied = _lab_stage(request, course_slug, topic_number, stage_pk, experiment_key)
    if denied:
        return denied
    stage, lab = place.stage, get_lab(place.stage.content.lab_key)
    experiment = row["spec"]
    if not place.preview:
        progress.start_stage(place.enrollment, stage)
    attempt = lab_services.start_attempt(request.user, lab.key, experiment, place.enrollment, stage)
    args = [place.course.slug, place.topic.number, stage.pk]
    index = [r["spec"].key for r in rows].index(experiment.key)
    following = rows[index + 1] if index + 1 < len(rows) else None
    nav = [
        {
            "number": i + 1,
            "title": r["spec"].title,
            "url": reverse("student:lab_run", args=[*args, r["spec"].key]) if r["open"] else None,
            "current": r is row,
            "done": r["done"],
        }
        for i, r in enumerate(rows)
    ]
    urls = {
        "analysis": reverse("student:lab_analysis", args=[*args, experiment.key, attempt.pk]),
        "topic": learning.stage_url(stage),
        # the next experiment opens once this analysis is sent, which is when the runner shows the link
        "next": reverse("student:lab_run", args=[*args, following["spec"].key]) if following else "",
    }
    if not place.preview:
        urls["ping"] = learning.stage_url(stage, "student:ping")  # time on the lab → StudyDay
    return lab_page(
        request, lab=lab, experiment=experiment, attempt=attempt, urls=urls, nav=nav, topic=place.topic,
        back_url=learning.stage_url(stage),
    )  # fmt: skip


@require_POST
@login_required
def lab_analysis(request, course_slug, topic_number, stage_pk, experiment_key, attempt_id):
    """The runner sends the analysis here inside a stage: stored by labs, then the stage result is recorded."""
    place, _rows, row, denied = _lab_stage(request, course_slug, topic_number, stage_pk, experiment_key)
    if denied:
        return JsonResponse({"error": "locked"}, status=403)
    attempt = get_object_or_404(
        LabAttempt, pk=attempt_id, user=request.user, stage=place.stage, experiment_key=experiment_key
    )
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return JsonResponse({"error": "object expected"}, status=400)
    attempt = lab_services.submit_analysis(attempt, row["spec"], data)
    if not place.preview:
        progress.record_lab_result(place.enrollment, place.stage)
    return JsonResponse(analysis_payload(attempt))


# --- quizzes inside a stage ---------------------------------------------------------


def _quiz_stage(request, course_slug, topic_number, stage_pk):
    place, stages, denied = _open_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return place, None, denied
    quiz = progress.stage_quiz(place.stage)
    if quiz is None:
        raise Http404
    if not place.preview:
        sp = place.progress.get(place.stage.pk)
        if not progress.quiz_is_open(place.enrollment, place.stage, sp):
            messages.info(request, _("Finish the material first — the test opens after it."))
            return place, quiz, redirect(learning.stage_url(place.stage))
    return place, quiz, None


@login_required
def quiz_take(request, course_slug, topic_number, stage_pk):
    place, quiz, denied = _quiz_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    stage_page = learning.stage_url(place.stage)
    last = quiz_selectors.last_attempt(request.user, quiz)
    if last and last.is_finished:
        return redirect(f"{stage_page}#quiz")
    try:
        attempt = quiz_services.start_attempt(request.user, quiz, place.enrollment)
    except quiz_services.AttemptError as exc:
        messages.error(request, str(exc))
        return redirect(stage_page)
    if quiz.instant_feedback:
        return redirect(f"{stage_page}#quiz")  # played inline, question by question
    submit_url = reverse(
        "student:quiz_submit", args=[place.course.slug, place.topic.number, place.stage.pk, attempt.pk]
    )
    context = take_context(quiz, attempt, submit_url, stage_page, place.stage.title, LEARN)
    context.update(_learn_context(place, learning.ordered_stages(place.topic), place.stage))
    return render(request, "assessments/take.html", context)


@require_POST
@login_required
def quiz_retry(request, course_slug, topic_number, stage_pk):
    place, quiz, denied = _quiz_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    try:
        quiz_services.start_attempt(request.user, quiz, place.enrollment)
    except quiz_services.AttemptError as exc:
        messages.error(request, str(exc))
        return redirect(learning.stage_url(place.stage))
    return redirect(learning.stage_url(place.stage, "student:quiz_take"))


def _stage_attempt(request, quiz, attempt_id):
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, quiz=quiz)
    if attempt.user_id != request.user.pk:
        raise Http404
    return attempt


@require_POST
@login_required
def quiz_submit(request, course_slug, topic_number, stage_pk, attempt_id):
    place, quiz, denied = _quiz_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    attempt = _stage_attempt(request, quiz, attempt_id)
    try:
        quiz_services.submit_attempt(attempt, collect_answers(attempt, request.POST))
    except quiz_services.AttemptError as exc:
        messages.info(request, str(exc))
    if not place.preview:
        progress.record_quiz_result(place.enrollment, place.stage, quiz)
    if quiz.instant_feedback:
        return redirect(f"{learning.stage_url(place.stage)}?result={attempt.pk}#quiz")
    return redirect("student:quiz_review", place.course.slug, place.topic.number, place.stage.pk, attempt.pk)


@require_POST
@login_required
def quiz_check(request, course_slug, topic_number, stage_pk, attempt_id, question_id):
    """Instant feedback (HTMX): grade one answer, store it and show the question in its checked state."""
    place, quiz, denied = _quiz_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    attempt = _stage_attempt(request, quiz, attempt_id)
    error = ""
    try:
        quiz_services.check_answer(attempt, question_id, collect_answers(attempt, request.POST).get(question_id))
    except quiz_services.AttemptError as exc:
        error = str(exc)
    rows = _inline_rows(place, attempt)
    index = next((i for i, r in enumerate(rows) if r["question"].pk == question_id), None)
    if index is None:
        raise Http404
    return render(
        request,
        "student/partials/quiz_question.html",
        {"row": rows[index], "index": index, "total": len(rows), "attempt": attempt, "quiz": quiz, "error": error,
         "submit_url": _quiz_submit_url(place, attempt)},
    )  # fmt: skip


def _quiz_submit_url(place, attempt):
    return reverse("student:quiz_submit", args=[place.course.slug, place.topic.number, place.stage.pk, attempt.pk])


def _inline_rows(place, attempt):
    """Questions of an instant-feedback attempt with the URL that checks each one."""
    rows = quiz_selectors.review_rows(attempt)
    args = [place.course.slug, place.topic.number, place.stage.pk, attempt.pk]
    for row in rows:
        row["check_url"] = reverse("student:quiz_check", args=[*args, row["question"].pk])
    return rows


@login_required
def quiz_review(request, course_slug, topic_number, stage_pk, attempt_id):
    place, quiz, denied = _quiz_stage(request, course_slug, topic_number, stage_pk)
    if denied:
        return denied
    attempt = _stage_attempt(request, quiz, attempt_id)
    if not attempt.is_finished:
        return redirect(learning.stage_url(place.stage, "student:quiz_take"))
    stage_page = learning.stage_url(place.stage)
    retry_url = learning.stage_url(place.stage, "student:quiz_retry")
    context = result_context(request.user, attempt, retry_url, stage_page, place.stage.title, LEARN)
    context.update(_learn_context(place, learning.ordered_stages(place.topic), place.stage))
    sp = progress_selectors.stage_progress_map(place.enrollment).get(place.stage.pk) if place.enrollment else None
    nxt = learning.next_place(place, place.stage)
    if sp and sp.status == S.PASSED and nxt:
        context.update({"back_url": nxt[0], "back_button": _("Go to the next stage")})
    else:
        context["back_button"] = _("Back to the stage")
    return render(request, "assessments/result.html", context)
