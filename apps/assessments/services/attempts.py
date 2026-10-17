"""Quiz attempts: start (pool, shuffling, limits, resume) and submit (auto-grading)."""

import random
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from ..models import AttemptAnswer, AttemptAnswerChoice, Question, Quiz, QuizAttempt
from .grading import grade

# Seconds accepted after the deadline (network delay of the auto-submit).
GRACE_SECONDS = 30


class AttemptError(Exception):
    """Shown to the student as is (already translated)."""


def deadline(attempt: QuizAttempt):
    limit = attempt.quiz.time_limit_min
    return attempt.started_at + timedelta(minutes=limit) if limit else None


def is_expired(attempt: QuizAttempt, now=None) -> bool:
    end = deadline(attempt)
    return bool(end and (now or timezone.now()) > end + timedelta(seconds=GRACE_SECONDS))


def attempts_used(user, quiz: Quiz, phase: str = "") -> int:
    """Attempts of one phase: a pre/post test counts its pre and post sittings separately."""
    return QuizAttempt.objects.filter(user=user, quiz=quiz, phase=phase).count()


def attempts_left(user, quiz: Quiz, phase: str = "") -> int | None:
    """None = unlimited."""
    if quiz.max_attempts is None:
        return None
    return max(0, quiz.max_attempts - attempts_used(user, quiz, phase))


def pick_questions(quiz: Quiz, rng: random.Random) -> tuple[list[int], dict[str, list[int]]]:
    """Question ids for a new attempt (pool sample + shuffling) and the option order of each question."""
    questions = list(quiz.questions.filter(is_active=True).prefetch_related("choices"))
    if quiz.questions_per_attempt and quiz.questions_per_attempt < len(questions):
        questions = rng.sample(questions, quiz.questions_per_attempt)
        if not quiz.shuffle_questions:
            questions.sort(key=lambda q: (q.order, q.pk))
    elif quiz.shuffle_questions:
        rng.shuffle(questions)
    choice_order = {}
    for q in questions:
        ids = [c.pk for c in q.choices.all()]
        if quiz.shuffle_choices:
            rng.shuffle(ids)
        if ids:
            choice_order[str(q.pk)] = ids
    return [q.pk for q in questions], choice_order


@transaction.atomic
def start_attempt(user, quiz: Quiz, enrollment=None, rng: random.Random | None = None, phase: str = "") -> QuizAttempt:
    """Resume the unfinished attempt or start a new one within ``max_attempts`` (counted per ``phase``;
    the post-test of a pre/post quiz is its attempt 2).

    An unfinished attempt whose time is over is closed first (graded with the answers it has: none).
    """
    open_attempt = (
        QuizAttempt.objects.select_for_update().filter(user=user, quiz=quiz, phase=phase, finished_at=None).first()
    )
    if open_attempt:
        if not is_expired(open_attempt):
            return open_attempt
        submit_attempt(open_attempt, {}, allow_late=True)
    left = attempts_left(user, quiz, phase)
    if left == 0:
        raise AttemptError(_("You have used all attempts for this test."))
    question_ids, choice_order = pick_questions(quiz, rng or random.Random())
    if not question_ids:
        raise AttemptError(_("This test has no questions yet."))
    return QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        enrollment=enrollment,
        # numbered over all phases: the (user, quiz, attempt_no) constraint stays as it is
        attempt_no=QuizAttempt.objects.filter(user=user, quiz=quiz).count() + 1,
        question_ids=question_ids,
        choice_order=choice_order,
        phase=phase,
    )


def _save_answer(attempt: QuizAttempt, question: Question, raw) -> AttemptAnswer:
    graded = grade(question, raw)
    answer = AttemptAnswer.objects.create(
        attempt=attempt,
        question=question,
        text_value=graded.text_value,
        numeric_value=graded.numeric_value,
        is_correct=graded.is_correct,
        points=graded.points,
    )
    AttemptAnswerChoice.objects.bulk_create(
        [AttemptAnswerChoice(answer=answer, choice_id=cid) for cid in graded.choice_ids]
    )
    return answer


@transaction.atomic
def check_answer(attempt: QuizAttempt, question_id: int, raw) -> AttemptAnswer:
    """Instant feedback: grade and store one answer of an unfinished attempt. A checked answer is final —
    checking again returns the stored one. The attempt is closed later by submit_attempt as usual."""
    attempt = QuizAttempt.objects.select_for_update().select_related("quiz").get(pk=attempt.pk)
    if not attempt.quiz.instant_feedback:
        raise AttemptError(_("Answers of this test are checked at the end."))
    if attempt.is_finished:
        raise AttemptError(_("This attempt has already been submitted."))
    if is_expired(attempt):
        raise AttemptError(_("The time for this test is over."))
    if question_id not in attempt.question_ids:
        raise AttemptError(_("This question is not in your attempt."))
    existing = attempt.answers.filter(question_id=question_id).first()
    if existing:
        return existing
    question = Question.objects.prefetch_related("choices").get(pk=question_id)
    return _save_answer(attempt, question, raw)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def submit_attempt(attempt: QuizAttempt, answers: dict, allow_late: bool = False) -> QuizAttempt:
    """Grade and close an attempt. ``answers``: {question_id: raw} — raw is a choice id, a list of ids or text.

    Questions are graded from the attempt's own question list, so unknown ids in ``answers`` are ignored.
    Does not touch progress: the caller (stage player) records the stage result.
    """
    attempt = QuizAttempt.objects.select_for_update().get(pk=attempt.pk)
    if attempt.is_finished:
        raise AttemptError(_("This attempt has already been submitted."))
    if is_expired(attempt) and not allow_late:
        answers = {}  # time is over: whatever arrives this late is not counted
    questions = Question.objects.filter(pk__in=attempt.question_ids).prefetch_related("choices").in_bulk()
    checked = {a.question_id: a for a in attempt.answers.all()}  # instant feedback: answers saved one by one
    score = max_score = Decimal("0")
    for qid in attempt.question_ids:
        question = questions.get(qid)
        if question is None:
            continue
        answer = checked.get(qid)
        if answer is None:
            answer = _save_answer(attempt, question, answers.get(qid, answers.get(str(qid))))
        score += answer.points
        max_score += question.points
    attempt.score = _quantize(score)
    attempt.max_score = _quantize(max_score)
    attempt.percent = _quantize(score / max_score * 100) if max_score else Decimal("0.00")
    attempt.passed = attempt.percent >= attempt.quiz.pass_percent
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["score", "max_score", "percent", "passed", "finished_at", "updated_at"])
    return attempt
