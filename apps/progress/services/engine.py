"""Gating and grading engine (ARCHITECTURE §4, §5). Every progress change goes through these functions;
no signals. Callers (stage players, teacher views) call them explicitly after an attempt or a review."""

from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.certificates import services as certificates
from apps.courses.models import Enrollment, Module, Stage, Topic
from apps.courses.selectors import stage_url
from apps.feedback import services as feedback

from ..grading import grade_for
from ..models import CourseResult, ModuleResult, ProgressEvent, StageProgress, TopicResult
from .scoring import q2, stage_weights, weighted_average

S = StageProgress.Status
FACTS = (S.IN_PROGRESS, S.AWAITING_CHECK, S.PASSED)
MAX_TIME_CHUNK_S = 30 * 60  # one add_time call never adds more than this (a forgotten tab is not study time)


class StageLocked(Exception):
    """The stage is not open for this student yet."""


# --- reading the course ---------------------------------------------------------


def _course_order(course):
    """Published topics in course order, each with its stages in order."""
    topics = list(
        Topic.objects.filter(module__course=course, is_published=True)
        .select_related("module")
        .prefetch_related("stages")
        .order_by("number")
    )
    return [(t, sorted(t.stages.all(), key=lambda s: (s.order, s.pk))) for t in topics]


def _lock(enrollment) -> Enrollment:
    return Enrollment.objects.select_for_update().select_related("course").get(pk=enrollment.pk)


# --- rows -----------------------------------------------------------------------


def _ensure_rows(enrollment, order) -> dict[int, StageProgress]:
    existing = {sp.stage_id: sp for sp in StageProgress.objects.filter(enrollment=enrollment)}
    missing = [
        StageProgress(enrollment=enrollment, stage=s) for _t, stages in order for s in stages if s.pk not in existing
    ]
    if missing:
        StageProgress.objects.bulk_create(missing, ignore_conflicts=True)
        existing = {sp.stage_id: sp for sp in StageProgress.objects.filter(enrollment=enrollment)}
    have_topics = set(TopicResult.objects.filter(enrollment=enrollment).values_list("topic_id", flat=True))
    TopicResult.objects.bulk_create(
        [TopicResult(enrollment=enrollment, topic=t) for t, _s in order if t.pk not in have_topics],
        ignore_conflicts=True,
    )
    module_ids = {t.module_id for t, _s in order}
    have_modules = set(ModuleResult.objects.filter(enrollment=enrollment).values_list("module_id", flat=True))
    ModuleResult.objects.bulk_create(
        [ModuleResult(enrollment=enrollment, module_id=m) for m in module_ids - have_modules], ignore_conflicts=True
    )
    CourseResult.objects.get_or_create(enrollment=enrollment)
    return existing


# --- the refresh ----------------------------------------------------------------


def _refresh(enrollment, order, progress: dict[int, StageProgress]) -> None:
    """Derive locked/available, topic statuses and every score from the stage facts."""
    course = enrollment.course
    sequential = course.is_sequential
    now = timezone.now()
    changed = []
    topic_rows = {r.topic_id: r for r in TopicResult.objects.filter(enrollment=enrollment)}
    topic_scores: dict[int, Decimal] = {}
    completed_topics: set[int] = set()
    topic_open = True  # the first published topic is open

    for topic, stages in order:
        previous_done = True
        any_fact = any_open = False
        for stage in stages:
            sp = progress[stage.pk]
            if sp.status not in FACTS:
                open_now = (not sequential) or (topic_open and previous_done) or sp.unlocked_by_id is not None
                new = S.AVAILABLE if open_now else S.LOCKED
                if sp.status != new:
                    sp.status = new
                    changed.append(sp)
            any_fact = any_fact or sp.status in FACTS
            any_open = any_open or sp.status != S.LOCKED
            if stage.is_required and not sp.counts_as_done:
                previous_done = False

        required = [s for s in stages if s.is_required]
        completed = bool(required) and all(progress[s.pk].status == S.PASSED for s in required)
        weights = stage_weights(course, stages)
        score = weighted_average((weights[s.pk], progress[s.pk].score_percent or 0) for s in required)

        row = topic_rows[topic.pk]
        status = (
            TopicResult.Status.COMPLETED
            if completed
            else TopicResult.Status.IN_PROGRESS
            if any_fact
            else TopicResult.Status.AVAILABLE
            if any_open
            else TopicResult.Status.LOCKED
        )
        if completed and row.status != TopicResult.Status.COMPLETED:
            ProgressEvent.objects.create(
                enrollment=enrollment, topic=topic, action="topic_completed", score_percent=score
            )
        row.status, row.score_percent = status, score
        row.completed_at = (row.completed_at or now) if completed else None
        row.save(update_fields=["status", "score_percent", "completed_at", "updated_at"])
        if completed:
            completed_topics.add(topic.pk)
            topic_scores[topic.pk] = score or Decimal(0)
        topic_open = completed

    if changed:
        StageProgress.objects.bulk_update(changed, ["status"])
    _refresh_totals(enrollment, order, topic_scores, completed_topics, now)


def _refresh_totals(enrollment, order, topic_scores, completed_topics, now) -> None:
    course = enrollment.course
    by_module: dict[int, list[Topic]] = {}
    for topic, _stages in order:
        by_module.setdefault(topic.module_id, []).append(topic)
    modules = {m.pk: m for m in Module.objects.filter(pk__in=by_module)}
    module_rows = {r.module_id: r for r in ModuleResult.objects.filter(enrollment=enrollment)}

    current_pairs, final_pairs = [], []
    all_done = bool(by_module)
    for module_id, topics in by_module.items():
        module = modules[module_id]
        done = [t for t in topics if t.pk in completed_topics]
        current = weighted_average((t.weight, topic_scores[t.pk]) for t in done)
        complete = len(done) == len(topics)
        row = module_rows[module_id]
        row.current_percent = current
        row.score_percent = current if complete else None
        row.completed_at = (row.completed_at or now) if complete else None
        row.save(update_fields=["current_percent", "score_percent", "completed_at", "updated_at"])
        if current is not None:
            current_pairs.append((module.weight, current))
        if complete:
            final_pairs.append((module.weight, current))
        all_done = all_done and complete

    result = CourseResult.objects.get(enrollment=enrollment)
    was_completed = result.completed_at is not None
    result.current_percent = weighted_average(current_pairs)
    result.topics_total = len(order)
    result.topics_completed = len(completed_topics)
    if all_done:
        final = weighted_average(final_pairs)
        grade = grade_for(final)
        result.score_percent, result.letter, result.gpa_points = final, grade.letter, grade.gpa
        result.passed = final >= course.passing_score
        result.completed_at = result.completed_at or now
    else:
        result.score_percent, result.letter, result.gpa_points, result.passed, result.completed_at = (
            None, "", None, False, None,
        )  # fmt: skip
    result.save()

    if all_done and not was_completed:
        ProgressEvent.objects.create(
            enrollment=enrollment, action="course_completed", score_percent=result.score_percent
        )
    if result.passed and course.certificate_enabled:  # issue_for does nothing when it is already issued
        transaction.on_commit(lambda: certificates.issue_for(enrollment))
    target = Enrollment.Status.COMPLETED if all_done else Enrollment.Status.ACTIVE
    if enrollment.status != Enrollment.Status.DROPPED and enrollment.status != target:
        enrollment.status = target
        enrollment.completed_at = now if all_done else None
        enrollment.save(update_fields=["status", "completed_at", "updated_at"])


# --- public API -----------------------------------------------------------------


@transaction.atomic
def recalculate(enrollment) -> None:
    """Create missing rows (new stages/topics), re-derive statuses and recompute topic → module → course."""
    enrollment = _lock(enrollment)
    order = _course_order(enrollment.course)
    _refresh(enrollment, order, _ensure_rows(enrollment, order))


def ensure_progress(enrollment) -> None:
    """Progress rows for every published stage; the first stage of the first topic opens."""
    recalculate(enrollment)


def _progress_row(enrollment, stage) -> StageProgress:
    sp = StageProgress.objects.filter(enrollment=enrollment, stage=stage).first()
    if sp is None:
        recalculate(enrollment)
        sp = StageProgress.objects.filter(enrollment=enrollment, stage=stage).first()
    return sp


def can_access(enrollment, stage) -> bool:
    if enrollment is None or enrollment.status == Enrollment.Status.DROPPED:
        return False
    if enrollment.course_id != stage.topic.module.course_id or not stage.topic.is_published:
        return False
    sp = _progress_row(enrollment, stage)
    return sp is not None and sp.status != S.LOCKED


def _open_row(enrollment, stage) -> StageProgress:
    if not can_access(enrollment, stage):
        raise StageLocked(stage)
    return StageProgress.objects.select_for_update().get(enrollment=enrollment, stage=stage)


def _log(enrollment, stage, action, actor=None, score=None):
    ProgressEvent.objects.create(
        enrollment=enrollment, stage=stage, topic_id=stage.topic_id, action=action, actor=actor, score_percent=score
    )


@transaction.atomic
def start_stage(enrollment, stage) -> StageProgress:
    enrollment = _lock(enrollment)
    sp = _open_row(enrollment, stage)
    if sp.status == S.AVAILABLE:
        sp.status, sp.started_at = S.IN_PROGRESS, timezone.now()
        sp.save(update_fields=["status", "started_at", "updated_at"])
        _log(enrollment, stage, "started")
        recalculate(enrollment)
    return sp


@transaction.atomic
def complete_stage(
    enrollment,
    stage,
    score_percent,
    *,
    passed: bool | None = None,
    awaiting_check: bool = False,
    attempts_exhausted: bool = False,
) -> StageProgress:
    """Record the stage result the caller has counted (best/last attempt, lab score …).

    passed — the caller's verdict (quiz stages use the quiz's own pass mark); None → score ≥ Stage.pass_percent.
    awaiting_check — part of the score waits for a teacher: the next stage opens, the topic does not complete.
    attempts_exhausted — not passed and no attempts left: passed with a «needs attention» mark (§4.3).
    A passed stage never goes back by the student's action; its score follows the counted attempt.
    """
    enrollment = _lock(enrollment)
    sp = _open_row(enrollment, stage)
    score = q2(score_percent)
    if passed is None:
        passed = score >= stage.pass_percent
    now = timezone.now()
    sp.started_at = sp.started_at or now
    sp.score_percent = score
    if passed:
        sp.status, sp.needs_attention = S.PASSED, False
        action = "passed"
    elif sp.status == S.PASSED:
        action = "failed"  # a worse retake: keep it passed, the counted score is the caller's call
    elif awaiting_check:
        sp.status = S.AWAITING_CHECK
        action = "awaiting_check"
    elif attempts_exhausted:
        sp.status, sp.needs_attention = S.PASSED, True
        action = "passed"
    else:
        sp.status = S.IN_PROGRESS
        action = "failed"
    sp.completed_at = (sp.completed_at or now) if sp.status == S.PASSED else None
    sp.save()
    _log(enrollment, stage, action, score=score)
    recalculate(enrollment)
    return sp


@transaction.atomic
def confirm_stage(enrollment, stage, score_percent, by) -> StageProgress:
    """A teacher sets the final score (confirms an AI grade, overrides a mark): the stage is passed and stays so."""
    enrollment = _lock(enrollment)
    sp = _open_row(enrollment, stage)
    sp.score_percent = q2(score_percent)
    sp.status, sp.needs_attention = S.PASSED, False
    sp.completed_at = sp.completed_at or timezone.now()
    sp.save()
    _log(enrollment, stage, "confirmed", actor=by, score=sp.score_percent)
    recalculate(enrollment)
    return sp


@transaction.atomic
def return_stage(enrollment, stage, by) -> StageProgress:
    """A teacher returns the work: the stage goes back to «in progress» (the topic is no longer complete)."""
    enrollment = _lock(enrollment)
    sp = _open_row(enrollment, stage)
    sp.status, sp.completed_at = S.IN_PROGRESS, None
    sp.save(update_fields=["status", "completed_at", "updated_at"])
    _log(enrollment, stage, "returned", actor=by, score=sp.score_percent)
    recalculate(enrollment)
    return sp


@transaction.atomic
def unlock_stage(enrollment, stage, by_teacher) -> StageProgress:
    """Open a stage for one student by hand (§4.5). Logged; the stage stays open whatever the order says."""
    enrollment = _lock(enrollment)
    if _progress_row(enrollment, stage) is None:  # unpublished topic or another course
        raise StageLocked(stage)
    sp = StageProgress.objects.select_for_update().get(enrollment=enrollment, stage=stage)
    sp.unlocked_by, sp.unlocked_at = by_teacher, timezone.now()
    if sp.status == S.LOCKED:
        sp.status = S.AVAILABLE
    sp.save()
    _log(enrollment, stage, "unlocked", actor=by_teacher)
    recalculate(enrollment)
    transaction.on_commit(
        lambda: feedback.notify(enrollment.student, feedback.Kind.UNLOCKED, stage.title, stage_url(stage))
    )
    return sp


def add_time(enrollment, stage, seconds: int) -> None:
    seconds = max(0, min(int(seconds), MAX_TIME_CHUNK_S))
    if seconds:
        StageProgress.objects.filter(enrollment=enrollment, stage=stage).update(
            time_spent_s=F("time_spent_s") + seconds
        )


def blocking_stage(enrollment, stage) -> Stage | None:
    """What the student has to finish first to open ``stage`` (for the «finish … first» page)."""
    if can_access(enrollment, stage):
        return None
    progress = {sp.stage_id: sp for sp in StageProgress.objects.filter(enrollment=enrollment)}
    for topic, stages in _course_order(enrollment.course):
        same_topic = topic.pk == stage.topic_id
        for s in stages:
            if same_topic and s.pk == stage.pk:
                return None
            sp = progress.get(s.pk)
            if not s.is_required or sp is None:
                continue
            done = sp.counts_as_done if same_topic else sp.status == S.PASSED
            if not done:
                return s
        if same_topic:
            return None
    return None
