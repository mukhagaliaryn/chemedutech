"""Stage-kind policies the stage player calls (theory/video material, quizzes). Built on engine.py."""

from django.db import transaction
from django.utils import timezone

from apps.assessments import selectors as quiz_selectors
from apps.assessments import services as quiz_services

from ..models import StageProgress
from .engine import _lock, _log, _open_row, complete_stage, start_stage

MATERIAL_DONE_PERCENT = 100


def stage_quiz(stage):
    """The quiz that grades a stage: the checkpoint quiz of theory/video, the quiz of a test stage."""
    if stage.kind == "test":
        content = stage.content
        return content.quiz if content else None
    return stage.checkpoint_quiz


@transaction.atomic
def complete_material(enrollment, stage, percent: int = MATERIAL_DONE_PERCENT) -> StageProgress:
    """Theory read / video watched. Opens the checkpoint quiz; without a quiz the stage is passed at once."""
    start_stage(enrollment, stage)
    enrollment = _lock(enrollment)
    sp = _open_row(enrollment, stage)
    sp.material_percent = max(sp.material_percent, min(int(percent), 100))
    first_time = sp.material_done_at is None
    sp.material_done_at = sp.material_done_at or timezone.now()
    sp.save(update_fields=["material_percent", "material_done_at", "updated_at"])
    if first_time:
        _log(enrollment, stage, "material_done")
    if stage_quiz(stage) is None and sp.status != StageProgress.Status.PASSED:
        sp = complete_stage(enrollment, stage, 100, passed=True)
    return sp


def record_watch(enrollment, stage, percent: int, min_percent: int) -> StageProgress:
    """Store how much of the video has been watched; reaching ``min_percent`` completes the material."""
    percent = max(0, min(int(percent), 100))
    if percent >= min_percent:
        return complete_material(enrollment, stage, percent)
    start_stage(enrollment, stage)
    sp = StageProgress.objects.get(enrollment=enrollment, stage=stage)
    if percent > sp.material_percent:
        StageProgress.objects.filter(pk=sp.pk).update(material_percent=percent)
        sp.material_percent = percent
    return sp


def quiz_is_open(enrollment, stage, sp: StageProgress | None) -> bool:
    """A test stage starts with its quiz; theory/video first need the material (ARCHITECTURE §4.2)."""
    if stage.kind == "test":
        return True
    return bool(sp and sp.material_done_at)


@transaction.atomic
def record_quiz_result(enrollment, stage, quiz) -> StageProgress:
    """After an attempt: the counted attempt (best/last/first) becomes the stage score.

    The quiz's pass mark decides (D25); no attempts left and not passed → passed with attention (D26).
    """
    counted = quiz_selectors.counted_attempt(enrollment.student, quiz)
    if counted is None:
        return StageProgress.objects.get(enrollment=enrollment, stage=stage)
    left = quiz_services.attempts_left(enrollment.student, quiz)
    return complete_stage(
        enrollment,
        stage,
        counted.percent,
        passed=counted.passed,
        attempts_exhausted=(left == 0 and not counted.passed),
    )
