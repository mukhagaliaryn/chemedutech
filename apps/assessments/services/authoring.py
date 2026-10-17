"""Quiz authoring (teacher cabinet). Answered questions and options are never deleted — they are retired."""

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from ..models import Choice, Question, Quiz


class AuthoringError(Exception):
    """Shown to the teacher as is (already translated)."""


def create_quiz(title: str, kind: str = Quiz.Kind.CHECKPOINT) -> Quiz:
    if kind == Quiz.Kind.BENCHMARK:
        # Pre/post: a single attempt per phase, nothing revealed, so the post-test stays a fair measure.
        return Quiz.objects.create(
            title=title[:255], kind=kind, max_attempts=1, show_answers_after=False, instant_feedback=False
        )
    return Quiz.objects.create(title=title[:255], kind=kind)


def question_in_use(question: Question) -> bool:
    return question.pk is not None and question.answers.exists()


def choice_in_use(choice: Choice) -> bool:
    return choice.pk is not None and choice.attemptanswerchoice_set.exists()


@transaction.atomic
def save_question(quiz: Quiz, question: Question, choices: list[dict]) -> Question:
    """``question`` — a validated (unsaved changes) instance; choices — [{"choice": Choice|None, "text", "is_correct",
    "delete"}] in display order. Kind rules: one correct option for «single», at least one for «multiple»."""
    if question.pk is None:
        question.quiz = quiz
        question.order = (quiz.questions.aggregate(m=Max("order"))["m"] or 0) + 1
    keep = [c for c in choices if not c["delete"] and c["text"].strip()]
    if question.kind in (Question.Kind.SINGLE, Question.Kind.MULTIPLE):
        correct = sum(1 for c in keep if c["is_correct"])
        if len(keep) < 2:
            raise AuthoringError(_("Give at least two options."))
        if question.kind == Question.Kind.SINGLE and correct != 1:
            raise AuthoringError(_("Mark exactly one correct option."))
        if question.kind == Question.Kind.MULTIPLE and correct < 1:
            raise AuthoringError(_("Mark at least one correct option."))
    for c in choices:
        if c["delete"] and c["choice"] is not None and choice_in_use(c["choice"]):
            raise AuthoringError(_("An option students have chosen cannot be deleted. Retire the question instead."))
    question.save()
    if question.kind in (Question.Kind.SINGLE, Question.Kind.MULTIPLE):
        for c in choices:
            if c["delete"] and c["choice"] is not None:
                c["choice"].delete()
        for order, c in enumerate(keep, start=1):
            choice = c["choice"] or Choice(question=question)
            choice.order, choice.text, choice.is_correct = order, c["text"].strip(), c["is_correct"]
            choice.save()
    return question


@transaction.atomic
def delete_question(question: Question) -> bool:
    """Delete an unused question; retire (is_active=False) one that students answered. True when deleted."""
    if question_in_use(question):
        question.is_active = False
        question.save(update_fields=["is_active", "updated_at"])
        return False
    question.delete()
    return True


@transaction.atomic
def reorder_questions(quiz: Quiz, ids: list[int]) -> None:
    questions = {q.pk: q for q in quiz.questions.all()}
    if sorted(questions) != sorted(ids):
        raise AuthoringError(_("The list has changed. Reload the page and try again."))
    for order, pk in enumerate(ids, start=1):
        Question.objects.filter(pk=pk).update(order=order)
