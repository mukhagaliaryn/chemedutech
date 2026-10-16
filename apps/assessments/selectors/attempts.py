from ..models import Quiz, QuizAttempt


def counted_attempt(user, quiz: Quiz) -> QuizAttempt | None:
    """The finished attempt that counts for the grade: best (highest %, earliest on ties), last or first."""
    finished = QuizAttempt.objects.filter(user=user, quiz=quiz).exclude(finished_at=None)
    if quiz.grading == Quiz.Grading.LAST:
        return finished.order_by("-finished_at", "-pk").first()
    if quiz.grading == Quiz.Grading.FIRST:
        return finished.order_by("finished_at", "pk").first()
    return finished.order_by("-percent", "finished_at", "pk").first()


def last_attempt(user, quiz: Quiz) -> QuizAttempt | None:
    return QuizAttempt.objects.filter(user=user, quiz=quiz).order_by("-attempt_no").first()


def stage_of_quiz(quiz: Quiz):
    """The course stage a quiz belongs to, or None. Uses reverse relations only — no courses import."""
    stage = getattr(quiz, "checkpoint_for", None)
    if stage is None:
        content = quiz.test_contents.select_related("stage__topic__module__course").first()
        stage = content.stage if content else None
    return stage


def course_of_quiz(quiz: Quiz):
    stage = stage_of_quiz(quiz)
    return stage.topic.module.course if stage else None


def enrollment_for(user, quiz: Quiz):
    course = course_of_quiz(quiz)
    if course is None or not user.is_authenticated:
        return None
    return user.enrollments.filter(course=course, status="active").first()


def review_rows(attempt: QuizAttempt) -> list[dict]:
    """Questions of a finished attempt in the order shown, with the answer given and the options."""
    questions = attempt.quiz.questions.filter(pk__in=attempt.question_ids).prefetch_related("choices").in_bulk()
    answers = {a.question_id: a for a in attempt.answers.prefetch_related("choices")}
    rows = []
    for qid in attempt.question_ids:
        question = questions.get(qid)
        if question is None:
            continue
        answer = answers.get(qid)
        chosen = {c.pk for c in answer.choices.all()} if answer else set()
        order = attempt.choice_order.get(str(qid)) or [c.pk for c in question.choices.all()]
        by_id = {c.pk: c for c in question.choices.all()}
        rows.append(
            {
                "question": question,
                "answer": answer,
                "choices": [{"choice": by_id[i], "chosen": i in chosen} for i in order if i in by_id],
            }
        )
    return rows
