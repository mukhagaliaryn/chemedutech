"""Practice submissions: accept → check exact fields → AI for open fields (background) → stage result."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.courses.selectors import stage_url
from apps.feedback import services as feedback
from apps.progress import services as progress

from .. import checkers
from ..models import AIGrade, PracticeAnswer, PracticeItem, PracticeSubmission, PracticeTask, TeacherReview

S = PracticeSubmission.Status


class SubmissionError(Exception):
    """Shown to the student as is (already translated)."""


def q2(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def attempts_used(enrollment, stage) -> int:
    """Submissions the teacher returned do not count: the student gets that attempt back."""
    return PracticeSubmission.objects.filter(enrollment=enrollment, stage=stage).exclude(status=S.RETURNED).count()


def attempts_left(enrollment, task: PracticeTask) -> int:
    return max(0, task.max_attempts - attempts_used(enrollment, task.stage))


def _raw_text(raw) -> str:
    return raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)


@transaction.atomic
def submit(enrollment, task: PracticeTask, answers: dict, file=None) -> PracticeSubmission:
    """Store the answers as typed and grade the exact fields now; open fields go to the AI in the background."""
    stage = task.stage
    if not progress.can_access(enrollment, stage):
        raise progress.StageLocked(stage)
    if PracticeSubmission.objects.filter(enrollment=enrollment, stage=stage, status=S.GRADING).exists():
        raise SubmissionError(_("Your previous answer is still being graded."))
    if attempts_left(enrollment, task) == 0:
        raise SubmissionError(_("You have used all attempts for this work."))
    submission = PracticeSubmission.objects.create(
        enrollment=enrollment,
        stage=stage,
        attempt_no=PracticeSubmission.objects.filter(enrollment=enrollment, stage=stage).count() + 1,
        file=file if task.allow_file and file else "",
    )
    has_open = False
    for item in task.items.all():
        raw = answers.get(item.pk, answers.get(str(item.pk)))
        answer = PracticeAnswer(submission=submission, item=item, raw_value=_raw_text(raw or ""))
        if item.kind == PracticeItem.Kind.OPEN:
            has_open = True
            if not answer.raw_value.strip():  # nothing to grade
                answer.is_correct, answer.points, answer.feedback = False, Decimal(0), _("The answer is empty.")
        else:
            result = checkers.check(item.kind, item.answer_spec, raw)
            answer.is_correct = result.is_correct
            answer.points = q2(item.points * Decimal(str(result.fraction)))
            answer.normalized = result.normalized
            answer.feedback = result.feedback
        answer.save()
    progress.start_stage(enrollment, stage)
    if has_open:
        submission.status = S.GRADING
        submission.save(update_fields=["status", "updated_at"])
        from ..tasks import grade_submission  # tasks import this module

        transaction.on_commit(lambda: grade_submission.enqueue(submission.pk))
        return submission
    return finalize(submission)


def grade_open_answers(submission: PracticeSubmission, client=None) -> None:
    """Run the AI on every open answer that has text and no grade yet (called by the background task)."""
    from .ai_grading import grade_open_answer

    pending = submission.answers.filter(item__kind=PracticeItem.Kind.OPEN, is_correct__isnull=True).select_related(
        "item__rubric", "submission__stage__practice_task"
    )
    for answer in pending:
        if not hasattr(answer.item, "rubric"):
            continue  # no rubric → a teacher grades it
        grade = grade_open_answer(answer, client=client)
        if grade.ok:
            top = sum(c.points for c in answer.item.rubric.criteria.all())
            answer.points = q2(grade.points)
            answer.is_correct = top > 0 and answer.points >= top
            answer.feedback = grade.feedback_kk
            answer.save(update_fields=["points", "is_correct", "feedback", "updated_at"])
        elif grade.criteria_scores:  # low confidence: provisional points, the teacher decides
            answer.points = q2(grade.points)
            answer.feedback = grade.feedback_kk
            answer.save(update_fields=["points", "feedback", "updated_at"])
    submission = finalize(submission)
    if submission.status == S.GRADED:  # graded in the background: the student may have left the page
        _notify(submission, feedback.Kind.GRADED)


def _notify(submission: PracticeSubmission, kind) -> None:
    stage = submission.stage
    transaction.on_commit(
        lambda: feedback.notify(submission.enrollment.student, kind, stage.title, stage_url(stage))
    )


def _needs_review(submission) -> bool:
    open_answers = submission.answers.filter(item__kind=PracticeItem.Kind.OPEN).select_related("ai_grade")
    for answer in open_answers:
        if answer.is_correct is False and not answer.raw_value.strip():
            continue  # empty open answer: 0 points, nothing to review
        grade = getattr(answer, "ai_grade", None)
        if grade is None or not grade.ok:
            return True
    return False


def counted_submission(enrollment, task: PracticeTask) -> PracticeSubmission | None:
    finished = PracticeSubmission.objects.filter(
        enrollment=enrollment, stage=task.stage, status__in=(S.GRADED, S.NEEDS_REVIEW)
    )
    if task.grading == PracticeTask.Grading.LAST:
        return finished.order_by("-attempt_no").first()
    return finished.order_by("-percent", "attempt_no").first()


@transaction.atomic
def finalize(submission: PracticeSubmission) -> PracticeSubmission:
    """Total the points, decide graded / needs review and record the stage result (§4.3)."""
    submission = PracticeSubmission.objects.select_for_update().get(pk=submission.pk)
    answers = list(submission.answers.select_related("item"))
    submission.score = q2(sum((a.points for a in answers), Decimal(0)))
    submission.max_score = q2(sum((a.item.points for a in answers), Decimal(0)))
    submission.percent = q2(submission.score / submission.max_score * 100) if submission.max_score else Decimal(0)
    submission.status = S.NEEDS_REVIEW if _needs_review(submission) else S.GRADED
    submission.graded_at = timezone.now()
    submission.save()
    record_stage_result(submission.enrollment, submission.stage.practice_task)
    return submission


def record_stage_result(enrollment, task: PracticeTask) -> None:
    counted = counted_submission(enrollment, task)
    if counted is None:
        return
    stage = task.stage
    waiting = PracticeSubmission.objects.filter(enrollment=enrollment, stage=stage, status=S.NEEDS_REVIEW).exists()
    if counted.status == S.NEEDS_REVIEW or (waiting and counted.percent < stage.pass_percent):
        progress.complete_stage(enrollment, stage, counted.percent, passed=False, awaiting_check=True)
        return
    progress.complete_stage(
        enrollment,
        stage,
        counted.percent,
        attempts_exhausted=attempts_left(enrollment, task) == 0,
    )


# --- teacher actions (the full grading queue UI comes in STEP-11) ------------------------


@transaction.atomic
def review_answer(answer: PracticeAnswer, teacher, points, reason: str = "", criteria_scores=None) -> TeacherReview:
    """The teacher confirms or changes the points of an open answer; AI vs teacher is kept for research."""
    grade = AIGrade.objects.filter(answer=answer).first()
    points = q2(min(max(Decimal(str(points)), Decimal(0)), answer.item.points))
    review = TeacherReview.objects.create(
        answer=answer,
        teacher=teacher,
        ai_points=q2(grade.points) if grade and grade.criteria_scores else None,
        teacher_points=points,
        criteria_scores=criteria_scores or [],
        reason=reason,
    )
    answer.points, answer.is_correct = points, points >= answer.item.points
    answer.save(update_fields=["points", "is_correct", "updated_at"])
    return review


@transaction.atomic
def confirm_submission(submission: PracticeSubmission, teacher, comment: str = "") -> PracticeSubmission:
    """Accept the (reviewed) grades: the submission is graded and the stage result is final."""
    for answer in submission.answers.filter(item__kind=PracticeItem.Kind.OPEN, teacher_reviews__isnull=True):
        grade = AIGrade.objects.filter(answer=answer).first()
        review_answer(answer, teacher, answer.points, reason="confirmed" if grade else "graded by the teacher")
    answers = list(submission.answers.select_related("item"))
    submission.score = q2(sum((a.points for a in answers), Decimal(0)))
    submission.percent = q2(submission.score / submission.max_score * 100) if submission.max_score else Decimal(0)
    submission.status, submission.graded_by, submission.graded_at = S.GRADED, teacher, timezone.now()
    submission.teacher_override = True
    submission.teacher_comment = comment or submission.teacher_comment
    submission.save()
    task = submission.stage.practice_task
    counted = counted_submission(submission.enrollment, task)
    progress.confirm_stage(submission.enrollment, submission.stage, counted.percent, by=teacher)
    _notify(submission, feedback.Kind.GRADED)
    return submission


@transaction.atomic
def return_submission(submission: PracticeSubmission, teacher, comment: str = "") -> PracticeSubmission:
    """Send the work back: the stage returns to «in progress» and the attempt is given back (§4.3)."""
    submission.status, submission.graded_by = S.RETURNED, teacher
    submission.teacher_comment = comment
    submission.save(update_fields=["status", "graded_by", "teacher_comment", "updated_at"])
    progress.return_stage(submission.enrollment, submission.stage, by=teacher)
    _notify(submission, feedback.Kind.RETURNED)
    return submission
