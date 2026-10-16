"""Quiz preview for teachers and admins. Students take quizzes inside the stage player (apps.student),
which also records the stage result; these pages never touch progress."""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.permissions import ADMIN, TEACHER, role_required

from . import selectors, services
from .forms import collect_answers
from .models import Quiz, QuizAttempt


def _own_attempt(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt.objects.select_related("quiz"), pk=attempt_id)
    if attempt.user_id != request.user.pk:
        raise Http404
    return attempt


def _back(quiz):
    stage = selectors.stage_of_quiz(quiz)
    if stage:
        return stage.topic.get_absolute_url(), stage.topic.title
    return reverse("admin:assessments_quiz_change", args=[quiz.pk]), quiz.title


def take_context(quiz, attempt, submit_url, back_url, back_label, base_template="layouts/student.html"):
    end = services.deadline(attempt)
    return {
        "quiz": quiz,
        "attempt": attempt,
        "rows": selectors.review_rows(attempt),
        "deadline": end.isoformat() if end else "",
        "submit_url": submit_url,
        "back_url": back_url,
        "back_label": back_label,
        "base_template": base_template,
    }


def result_context(user, attempt, retry_url, back_url, back_label, base_template="layouts/student.html"):
    quiz = attempt.quiz
    left = services.attempts_left(user, quiz)
    return {
        "quiz": quiz,
        "attempt": attempt,
        "rows": selectors.review_rows(attempt),
        "counted": selectors.counted_attempt(user, quiz),
        "history": QuizAttempt.objects.filter(user=user, quiz=quiz).order_by("attempt_no"),
        "attempts_left": left,
        "can_retry": left != 0,
        "retry_url": retry_url,
        "back_url": back_url,
        "back_label": back_label,
        "base_template": base_template,
    }


@role_required(TEACHER, ADMIN)
def take(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    last = selectors.last_attempt(request.user, quiz)
    if last and last.is_finished:
        return redirect("assessments:result", last.pk)
    back_url, back_label = _back(quiz)
    try:
        attempt = services.start_attempt(request.user, quiz)
    except services.AttemptError as exc:
        messages.error(request, str(exc))
        return redirect(back_url)
    submit_url = reverse("assessments:submit", args=[attempt.pk])
    return render(request, "assessments/take.html", take_context(quiz, attempt, submit_url, back_url, back_label))


@require_POST
@role_required(TEACHER, ADMIN)
def retry(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    try:
        services.start_attempt(request.user, quiz)
    except services.AttemptError as exc:
        messages.error(request, str(exc))
    return redirect("assessments:take", quiz.pk)


@require_POST
@role_required(TEACHER, ADMIN)
def submit(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    try:
        services.submit_attempt(attempt, collect_answers(attempt, request.POST))
    except services.AttemptError as exc:
        messages.info(request, str(exc))
    return redirect("assessments:result", attempt.pk)


@role_required(TEACHER, ADMIN)
def result(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if not attempt.is_finished:
        return redirect("assessments:take", attempt.quiz_id)
    back_url, back_label = _back(attempt.quiz)
    retry_url = reverse("assessments:retry", args=[attempt.quiz_id])
    return render(
        request, "assessments/result.html", result_context(request.user, attempt, retry_url, back_url, back_label)
    )
