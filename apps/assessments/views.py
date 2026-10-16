"""Taking a quiz: player, submit, result. STEP-07 embeds the same templates in the stage player."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.permissions import ADMIN, TEACHER, has_role

from . import selectors, services
from .models import Question, Quiz, QuizAttempt


def _access(request, quiz):
    """(enrollment, allowed). Students need an active enrolment in the quiz's course; staff may preview."""
    enrollment = selectors.enrollment_for(request.user, quiz)
    if enrollment is None and not has_role(request.user, TEACHER, ADMIN):
        raise Http404
    return enrollment


def _own_attempt(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt.objects.select_related("quiz"), pk=attempt_id)
    if attempt.user_id != request.user.pk:
        raise Http404
    return attempt


@login_required
def take(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    enrollment = _access(request, quiz)
    last = selectors.last_attempt(request.user, quiz)
    if last and last.is_finished:
        return redirect("assessments:result", last.pk)
    try:
        attempt = services.start_attempt(request.user, quiz, enrollment)
    except services.AttemptError as exc:
        messages.error(request, str(exc))
        return redirect(_back_url(quiz))
    end = services.deadline(attempt)
    return render(
        request,
        "assessments/take.html",
        {
            "quiz": quiz,
            "attempt": attempt,
            "rows": selectors.review_rows(attempt),
            "deadline": end.isoformat() if end else "",
            "stage": selectors.stage_of_quiz(quiz),
            "attempts_left": services.attempts_left(request.user, quiz),
        },
    )


@require_POST
@login_required
def retry(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    enrollment = _access(request, quiz)
    try:
        services.start_attempt(request.user, quiz, enrollment)
    except services.AttemptError as exc:
        messages.error(request, str(exc))
        last = selectors.last_attempt(request.user, quiz)
        return redirect("assessments:result", last.pk) if last else redirect(_back_url(quiz))
    return redirect("assessments:take", quiz.pk)


@require_POST
@login_required
def submit(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    kinds = dict(Question.objects.filter(pk__in=attempt.question_ids).values_list("pk", "kind"))
    answers = {}
    for qid in attempt.question_ids:
        name = f"q{qid}"
        answers[qid] = (
            request.POST.getlist(name) if kinds.get(qid) == Question.Kind.MULTIPLE else request.POST.get(name)
        )
    try:
        services.submit_attempt(attempt, answers)
    except services.AttemptError as exc:
        messages.info(request, str(exc))
    return redirect("assessments:result", attempt.pk)


@login_required
def result(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if not attempt.is_finished:
        return redirect("assessments:take", attempt.quiz_id)
    quiz = attempt.quiz
    left = services.attempts_left(request.user, quiz)
    return render(
        request,
        "assessments/result.html",
        {
            "quiz": quiz,
            "attempt": attempt,
            "rows": selectors.review_rows(attempt),
            "counted": selectors.counted_attempt(request.user, quiz),
            "history": QuizAttempt.objects.filter(user=request.user, quiz=quiz).order_by("attempt_no"),
            "attempts_left": left,
            "can_retry": left != 0,
            "stage": selectors.stage_of_quiz(quiz),
        },
    )


def _back_url(quiz):
    stage = selectors.stage_of_quiz(quiz)
    return stage.topic.get_absolute_url() if stage else "core:home"
