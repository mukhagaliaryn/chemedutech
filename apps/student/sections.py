"""The ICPAI programme in the student cabinet (docs/icpai/SPEC.md §4.0, STEP-29): the home page with the guide
and the sections' state, and a page per section. Section 1 leads to the existing course pages."""

import json

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.assessments import services as quiz_services
from apps.assessments.forms import collect_answers
from apps.assessments.models import QuizAttempt
from apps.assessments.views import take_context
from apps.core.permissions import STUDENT, role_required
from apps.programme import selectors as programme_selectors
from apps.programme import services as programme
from apps.programme.models import DiagnosticTest, Level, Section, SectionProgress, SectionVideo, VideoWatch
from apps.programme.services import diagnostics
from apps.progress import selectors as progress_selectors
from apps.progress.services import benchmark

from . import cabinet

LOCKED = SectionProgress.Status.LOCKED


def _course_block(enrollment) -> dict | None:
    """Section 1: the course enrolment's stages done and where to continue."""
    course_enrollment = programme_selectors.course_enrollment(enrollment)
    if course_enrollment is None:
        return None
    done, total = progress_selectors.required_stages_done(course_enrollment)
    place = cabinet.place_of(course_enrollment)
    return {
        "enrollment": course_enrollment,
        "course": course_enrollment.course,
        "done": done,
        "total": total,
        "card": cabinet.continue_card(place),
        "course_url": reverse("student:course", args=[course_enrollment.course.slug]),
    }


def home_context(user, enrollment) -> dict:
    """The programme home: the guide (sections with «what it does»), their state and «Continue»."""
    rows = programme_selectors.section_rows(enrollment)
    current = programme_selectors.current_section(rows)
    course = _course_block(enrollment)
    return {
        "programme": enrollment.programme,
        "rows": rows,
        "current": current,
        "continue_url": continue_url(current, course) if current else None,
        "passed_count": sum(1 for r in rows if r["status"] == SectionProgress.Status.PASSED),
        "course_block": course,
        "comments": cabinet.teacher_comments(course["enrollment"]) if course else [],
        "benchmark": benchmark.summary(course["enrollment"]) if course else {},
    }


@role_required(STUDENT)
def section(request, number):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, number=number)
    rows = programme_selectors.section_rows(enrollment)
    row = next(r for r in rows if r["section"].pk == section.pk)
    context = {"programme": enrollment.programme, "section": section, "row": row, "rows": rows}
    if row["status"] == LOCKED:
        blocking = programme.blocking_section(enrollment, section)
        context["blocking"] = next((r for r in rows if blocking and r["section"].pk == blocking.pk), None)
        return render(request, "student/section_locked.html", context)
    if section.kind == Section.Kind.COURSE:
        context["course_block"] = _course_block(enrollment)
    elif section.kind == Section.Kind.DIAGNOSTIC:
        context["diagnostics"] = programme_selectors.diagnostic_rows(enrollment, section)
    elif section.kind == Section.Kind.VIDEO:
        video = SectionVideo.objects.filter(section=section).first()
        watch = VideoWatch.objects.filter(enrollment=enrollment, section=section).first()
        context["video"] = video if video and video.youtube_id else None
        context["watched"] = watch.percent if watch else 0
    return render(request, "student/section.html", context)


def continue_url(row, course_block) -> str:
    """Where «Continue» leads for a section row: the next course stage for section 1, else the section page."""
    if row["section"].kind == Section.Kind.COURSE and course_block and course_block["card"]:
        return course_block["card"]["url"]
    return row["url"]


# --- section 2: the diagnostics I → II → III (guide @S2; D71) ----------------------------------------------


def _diagnostic(request, number, phase):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, number=number, kind=Section.Kind.DIAGNOSTIC)
    test = get_object_or_404(DiagnosticTest.objects.select_related("quiz"), section=section, phase=phase)
    return enrollment, section, test


@role_required(STUDENT)
def diagnostic(request, number, phase):
    """Intro (the guide's stage name, title, aim) → the single attempt (the usual test page, no answers shown) →
    the result: the four component rings, the score, the level and the guide's interpretation."""
    enrollment, section, test = _diagnostic(request, number, phase)
    attempt = diagnostics.open_attempt(enrollment, test)
    if attempt and quiz_services.is_expired(attempt):
        diagnostics.record(enrollment, test, quiz_services.submit_attempt(attempt, {}, allow_late=True))
        attempt = None
    if attempt:
        submit_url = reverse("student:diagnostic_submit", args=[number, phase, attempt.pk])
        back_url = reverse("student:section", args=[number])
        return render(
            request, "assessments/take.html", take_context(test.quiz, attempt, submit_url, back_url, section.title)
        )
    rows = programme_selectors.diagnostic_rows(enrollment, section)
    row = next(r for r in rows if r["test"].pk == test.pk)
    following = next((r for r in rows if r["test"].phase > test.phase), None)
    summary = row["summary"]
    return render(
        request,
        "student/diagnostic.html",
        {
            "programme": enrollment.programme,
            "section": section,
            "test": test,
            "row": row,
            "rows": rows,
            "next_row": following,
            "interpretation": test.levels.get(summary["level"], "") if summary else "",
            "level_label": Level(summary["level"]).label if summary else "",
            "question_count": test.quiz.questions.filter(is_active=True).count(),
        },
    )


@require_POST
@role_required(STUDENT)
def diagnostic_start(request, number, phase):
    enrollment, _section, test = _diagnostic(request, number, phase)
    try:
        diagnostics.start(enrollment, test)
    except quiz_services.AttemptError as exc:
        messages.error(request, str(exc))
    return redirect("student:diagnostic", number, phase)


@require_POST
@role_required(STUDENT)
def diagnostic_submit(request, number, phase, attempt_id):
    enrollment, _section, test = _diagnostic(request, number, phase)
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user, quiz=test.quiz, phase=test.phase)
    try:
        attempt = quiz_services.submit_attempt(attempt, collect_answers(attempt, request.POST))
    except quiz_services.AttemptError as exc:
        messages.info(request, str(exc))
    diagnostics.record(enrollment, test, attempt)
    return redirect("student:diagnostic", number, phase)


# --- «Results» (guide @S7 II, SPEC §3.3): ICPAI components × stages -----------------------------------------


@role_required(STUDENT)
def results(request):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = programme_selectors.diagnostic_section(enrollment.programme)
    rows = programme_selectors.component_dynamics(enrollment)
    return render(
        request,
        "student/icpai_results.html",
        {
            "programme": enrollment.programme,
            "rows": rows,
            "phases": ("I", "II", "III"),
            "taken": any(v is not None for r in rows for v in r["phases"].values()),
            "section": section,
            "stages": programme_selectors.diagnostic_rows(enrollment, section) if section else [],
        },
    )


# --- section 3: the video (guide @S3; D72) ----------------------------------------------------------------


@require_POST
@role_required(STUDENT)
def section_watch(request, number):
    """The video player reports the share watched ({percent}); answers {percent, done}."""
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, number=number, kind=Section.Kind.VIDEO)
    if not programme.can_access(enrollment, section):
        return JsonResponse({"error": "not_available"}, status=403)
    try:
        percent = int(json.loads(request.body or b"{}").get("percent", 0))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    stored = programme.record_watch(enrollment, section, percent)
    row = SectionProgress.objects.get(enrollment=enrollment, section=section)
    return JsonResponse({"percent": stored, "done": row.status == SectionProgress.Status.PASSED})
