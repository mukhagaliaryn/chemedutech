"""Quiz helpers of the seed. Questions are written only into a quiz nobody has attempted: a quiz with attempts
(research data, ARCHITECTURE §3.4, D22) is never touched."""

from apps.assessments.models import Choice, Question, Quiz

CHECKPOINT_DEFAULTS = {"pass_percent": 75, "max_attempts": 3, "show_answers_after": True, "instant_feedback": True}
TOPIC_TEST_DEFAULTS = {"pass_percent": 60, "max_attempts": 2, "time_limit_min": 15, "shuffle_questions": True}


def write_questions(quiz: Quiz, questions) -> None:
    """questions: [(kind, text, spec, explanation)]; spec — [(option, is_correct)] | (number, tolerance) | [answers]."""
    for order, (kind, text, spec, explanation) in enumerate(questions, start=1):
        q = Question.objects.create(quiz=quiz, order=order, kind=kind, text=text, explanation=explanation)
        if kind in ("single", "multiple"):
            Choice.objects.bulk_create(
                Choice(question=q, order=i, text=t, is_correct=ok) for i, (t, ok) in enumerate(spec, start=1)
            )
        elif kind == "numeric":
            q.numeric_answer, q.numeric_tolerance = spec
            q.save(update_fields=["numeric_answer", "numeric_tolerance"])
        else:
            q.accepted_answers = spec
            q.save(update_fields=["accepted_answers"])


def sync_quiz(quiz: Quiz | None, kind, title, questions, settings=None, replace=False) -> tuple[Quiz, str]:
    """Create the quiz, or fill an empty one; with ``replace`` rewrite an unattempted quiz (title, settings,
    questions). Returns the quiz and what happened: created | filled | replaced | kept | attempted."""
    defaults = {**(CHECKPOINT_DEFAULTS if kind == Quiz.Kind.CHECKPOINT else TOPIC_TEST_DEFAULTS), **(settings or {})}
    if quiz is None:
        quiz = Quiz.objects.create(title=title, kind=kind, **defaults)
        write_questions(quiz, questions)
        return quiz, "created"
    if not quiz.questions.exists():
        write_questions(quiz, questions)
        return quiz, "filled"
    if not replace:
        return quiz, "kept"
    if quiz.attempts.exists():
        return quiz, "attempted"
    quiz.title = title
    for field, value in defaults.items():
        setattr(quiz, field, value)
    quiz.save()
    quiz.questions.all().delete()
    write_questions(quiz, questions)
    return quiz, "replaced"
