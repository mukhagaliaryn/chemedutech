"""Section 2 — the ICPAI diagnostics (guide @S2, docs/icpai/SPEC.md §2.2, §3.2; D71): three tests I → II → III taken
in order inside the section, once each; the section is passed when all are taken. A result is counted per component:
component % = earned / maximum × 100 (guide @S7 II); the level follows the total score (0–4 low, 5–7 medium,
8–10 high on the guide's 10-question tests — as shares of the maximum for any size).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils.translation import gettext as _

from apps.assessments import services as quiz_services
from apps.assessments.models import AttemptAnswer, Question, QuizAttempt

from ..models import DiagnosticResult, DiagnosticTest, Level
from ..providers.course import course_enrollment
from .engine import can_access, recalculate

OPEN, LOCKED, STARTED, DONE = "open", "locked", "started", "done"


def tests_of(section) -> list[DiagnosticTest]:
    return list(section.diagnostic_tests.select_related("quiz").order_by("phase"))  # "I" < "II" < "III"


def level_for(earned, maximum) -> str:
    share = Decimal(earned) / Decimal(maximum) if maximum else Decimal(0)
    if share >= Decimal("0.8"):
        return Level.HIGH
    if share >= Decimal("0.5"):
        return Level.MEDIUM
    return Level.LOW


def _percent(earned, maximum) -> Decimal:
    if not maximum:
        return Decimal(0)
    return (Decimal(earned) * 100 / Decimal(maximum)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def done_phases(enrollment) -> set[str]:
    return set(DiagnosticResult.objects.filter(enrollment=enrollment).values_list("phase", flat=True))


def open_attempt(enrollment, test) -> QuizAttempt | None:
    return (
        QuizAttempt.objects.filter(user_id=enrollment.student_id, quiz=test.quiz, phase=test.phase, finished_at=None)
        .order_by("-attempt_no")
        .first()
    )


def state(enrollment, test, tests=None, done=None) -> str:
    """done / started / open / locked: a stage opens when the section is open and every earlier stage is done."""
    done = done_phases(enrollment) if done is None else done
    if test.phase in done:
        return DONE
    tests = tests_of(test.section) if tests is None else tests
    earlier = [t.phase for t in tests if t.phase < test.phase]
    if not can_access(enrollment, test.section) or any(p not in done for p in earlier):
        return LOCKED
    return STARTED if open_attempt(enrollment, test) else OPEN


@transaction.atomic
def start(enrollment, test) -> QuizAttempt:
    """Start (or resume) the single attempt of an open stage; the attempt belongs to the course enrolment so that
    the research group is known. Raises AttemptError for a locked or finished stage."""
    if state(enrollment, test) not in (OPEN, STARTED):
        raise quiz_services.AttemptError(_("This diagnostic test is not open."))
    return quiz_services.start_attempt(
        enrollment.student, test.quiz, enrollment=course_enrollment(enrollment), phase=test.phase
    )


@transaction.atomic
def record(enrollment, test, attempt) -> list[DiagnosticResult]:
    """After the attempt is submitted: the four component results of the stage (once), then the section percent."""
    existing = list(DiagnosticResult.objects.filter(enrollment=enrollment, phase=test.phase))
    if existing or not attempt.is_finished:
        return existing
    questions = {q.pk: q for q in Question.objects.filter(pk__in=attempt.question_ids)}
    earned = {q.pk: Decimal(0) for q in questions.values()}
    for answer in AttemptAnswer.objects.filter(attempt=attempt):
        earned[answer.question_id] = answer.points
    by_component: dict[str, list[Decimal]] = {}
    for q in questions.values():
        if q.component:
            totals = by_component.setdefault(q.component, [Decimal(0), Decimal(0)])
            totals[0] += earned[q.pk]
            totals[1] += q.points
    total_earned = sum(t[0] for t in by_component.values())
    total_max = sum(t[1] for t in by_component.values())
    level = level_for(total_earned, total_max)
    rows = [
        DiagnosticResult(
            enrollment=enrollment,
            test=test,
            phase=test.phase,
            component=component,
            earned=e,
            maximum=m,
            percent=_percent(e, m),
            level=level,
            attempt=attempt,
        )  # fmt: skip
        for component, (e, m) in by_component.items()
    ]
    DiagnosticResult.objects.bulk_create(rows)
    recalculate(enrollment)
    return rows


def summary(results) -> dict:
    """{earned, maximum, percent, level} of one stage from its component rows."""
    rows = list(results)
    earned = sum((r.earned for r in rows), Decimal(0))
    maximum = sum((r.maximum for r in rows), Decimal(0))
    return {
        "earned": earned,
        "maximum": maximum,
        "percent": _percent(earned, maximum),
        "level": rows[0].level if rows else "",
    }
