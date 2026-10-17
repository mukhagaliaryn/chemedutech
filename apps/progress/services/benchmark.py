"""The course's pre/post knowledge test (research, STEP-22, D61).

One quiz (``Course.benchmark_quiz``) is taken twice: once before the first stage (pre) and once after the
course (post). Each phase has a single attempt, only the overall percent is shown to the student, and it never
touches StageProgress or the course score. The post-test opens when every topic is completed or when the
teacher opens it for the group (``CourseGroup.posttest_opened_at``).
"""

from django.utils.translation import gettext as _

from apps.assessments import services as quiz_services
from apps.assessments.models import QuizAttempt
from apps.courses.models import CourseGroup

from ..models import CourseResult, StageProgress

PRE, POST = QuizAttempt.Phase.PRE, QuizAttempt.Phase.POST
PHASES = (PRE, POST)

NONE, LOCKED, OPEN, DONE = "none", "locked", "open", "done"


def benchmark_quiz(course):
    """The course's pre/post test when it has questions; an empty one does not gate anybody."""
    quiz = course.benchmark_quiz if course.benchmark_quiz_id else None
    if quiz is None or not quiz.questions.filter(is_active=True).exists():
        return None
    return quiz


def phase_attempt(enrollment, phase, quiz=None) -> QuizAttempt | None:
    quiz = quiz or benchmark_quiz(enrollment.course)
    if quiz is None:
        return None
    return QuizAttempt.objects.filter(user=enrollment.student, quiz=quiz, phase=phase).order_by("-attempt_no").first()


def _started_course(enrollment) -> bool:
    """Students who passed a stage before the pre-test was added are not sent back to it."""
    return StageProgress.objects.filter(
        enrollment=enrollment, status__in=(StageProgress.Status.PASSED, StageProgress.Status.AWAITING_CHECK)
    ).exists()


def pretest_state(enrollment) -> str:
    """none (no test / not needed) · open (must be taken before the first stage) · done."""
    quiz = benchmark_quiz(enrollment.course)
    if quiz is None:
        return NONE
    attempt = phase_attempt(enrollment, PRE, quiz)
    if attempt and attempt.is_finished:
        return DONE
    if attempt is None and _started_course(enrollment):
        return NONE
    return OPEN


def pretest_required(enrollment) -> bool:
    return enrollment is not None and pretest_state(enrollment) == OPEN


def _course_completed(enrollment) -> bool:
    result = CourseResult.objects.filter(enrollment=enrollment).first()
    return enrollment.status == "completed" or bool(
        result and (result.completed_at or result.score_percent is not None)
    )


def _opened_by_teacher(enrollment) -> bool:
    if not enrollment.group_id:
        return False
    return CourseGroup.objects.filter(
        course_id=enrollment.course_id, group_id=enrollment.group_id, posttest_opened_at__isnull=False
    ).exists()


def posttest_state(enrollment) -> str:
    """none (no test) · locked (course not finished yet) · open · done."""
    quiz = benchmark_quiz(enrollment.course)
    if quiz is None:
        return NONE
    attempt = phase_attempt(enrollment, POST, quiz)
    if attempt and attempt.is_finished:
        return DONE
    if attempt or _course_completed(enrollment) or _opened_by_teacher(enrollment):
        return OPEN
    return LOCKED


def phase_state(enrollment, phase) -> str:
    return pretest_state(enrollment) if phase == PRE else posttest_state(enrollment)


def start(enrollment, phase) -> QuizAttempt:
    """Resume or start the single attempt of a phase (AttemptError when it is not open or already taken)."""
    if phase not in PHASES:
        raise quiz_services.AttemptError(_("Unknown test."))
    state = phase_state(enrollment, phase)
    if state == DONE:
        raise quiz_services.AttemptError(_("You have already taken this test."))
    if state != OPEN:
        raise quiz_services.AttemptError(
            _("The final knowledge test opens when you finish the course.")
            if phase == POST
            else _("This test is not needed any more.")
        )
    quiz = benchmark_quiz(enrollment.course)
    return quiz_services.start_attempt(enrollment.student, quiz, enrollment, phase=phase)


def summary(enrollment) -> dict:
    """For the course map / dashboard: {quiz, pre, post, pre_attempt, post_attempt} or {} without a test."""
    quiz = benchmark_quiz(enrollment.course)
    if quiz is None:
        return {}
    return {
        "quiz": quiz,
        "pre": pretest_state(enrollment),
        "post": posttest_state(enrollment),
        "pre_attempt": phase_attempt(enrollment, PRE, quiz),
        "post_attempt": phase_attempt(enrollment, POST, quiz),
    }
