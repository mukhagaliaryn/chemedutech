from ..models import Quiz, QuizAttempt


def counted_attempt(user, quiz: Quiz) -> QuizAttempt | None:
    """The finished attempt that counts for the grade: best (highest %, earliest on ties), last or first."""
    finished = QuizAttempt.objects.filter(user=user, quiz=quiz, phase="").exclude(finished_at=None)
    if quiz.grading == Quiz.Grading.LAST:
        return finished.order_by("-finished_at", "-pk").first()
    if quiz.grading == Quiz.Grading.FIRST:
        return finished.order_by("finished_at", "pk").first()
    return finished.order_by("-percent", "finished_at", "pk").first()


def last_attempt(user, quiz: Quiz) -> QuizAttempt | None:
    return QuizAttempt.objects.filter(user=user, quiz=quiz, phase="").order_by("-attempt_no").first()


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


def finished_attempts(enrollment):
    """Finished quiz attempts of one enrolment, newest first (the pre/post test is not part of the course)."""
    return (
        QuizAttempt.objects.filter(enrollment=enrollment, phase="")
        .exclude(finished_at=None)
        .select_related("quiz")
        .order_by("-finished_at", "-pk")
    )


def attempt_counts(enrollment) -> dict[int, int]:
    """{quiz_id: finished attempts} of one enrolment."""
    counts = {}
    for quiz_id in finished_attempts(enrollment).values_list("quiz_id", flat=True):
        counts[quiz_id] = counts.get(quiz_id, 0) + 1
    return counts


def repeated_failures(enrollment_ids, min_failures=3) -> list[dict]:
    """[{enrollment_id, quiz_id, quiz__title, n}] — quizzes failed at least ``min_failures`` times and never passed."""
    from django.db.models import Count, Q

    rows = (
        QuizAttempt.objects.filter(enrollment_id__in=enrollment_ids, phase="")
        .exclude(finished_at=None)
        .values("enrollment_id", "quiz_id", "quiz__title")
        .annotate(n=Count("id", filter=Q(passed=False)), passed=Count("id", filter=Q(passed=True)))
        .filter(n__gte=min_failures, passed=0)
    )
    return list(rows)


def last_attempt_times(enrollment_ids) -> dict[int, object]:
    from django.db.models import Max

    rows = (
        QuizAttempt.objects.filter(enrollment_id__in=enrollment_ids)
        .values("enrollment_id")
        .annotate(at=Max("started_at"))
    )
    return {r["enrollment_id"]: r["at"] for r in rows}
