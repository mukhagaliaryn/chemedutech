"""Write operations on lab attempts (public interface of the labs domain)."""

from __future__ import annotations

from collections import Counter

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from apps.labs.engine import get_lab
from apps.labs.engine.spec import ExperimentSpec, LabScoring
from apps.labs.models import LabAttempt, LabEvent
from apps.labs.scoring import attempt_score
from apps.organizations.selectors import research_cohort_for

MAX_EVENTS_PER_BATCH = 200
VALID_TYPES = {t.value for t in LabEvent.Type}


def start_attempt(user, lab_key: str, experiment: ExperimentSpec, enrollment=None, stage=None) -> LabAttempt:
    """Open an attempt for the run page.

    A plain page reload must not inflate the research data, so an unfinished
    attempt in which the student has not done anything yet (only the "start"
    event) is reused instead of creating a new one. Inside a course stage the
    attempt is tied to the enrolment and its research group is copied from it.
    """
    untouched = (
        LabAttempt.objects.filter(
            user=user,
            lab_key=lab_key,
            experiment_key=experiment.key,
            status=LabAttempt.Status.IN_PROGRESS,
            enrollment=enrollment,
            stage=stage,
        )
        .annotate(n_events=Count("events"))
        .filter(n_events__lte=1)
        .order_by("-started_at")
        .first()
    )
    if untouched:
        untouched.events.all().delete()
        untouched.started_at = timezone.now()
        untouched.save(update_fields=["started_at"])
        return untouched
    return LabAttempt.objects.create(
        user=user,
        lab_key=lab_key,
        experiment_key=experiment.key,
        enrollment=enrollment,
        stage=stage,
        research_cohort=enrollment.research_cohort if enrollment else research_cohort_for(user),
    )


def record_events(attempt: LabAttempt, events: list[dict]) -> int:
    """Store a batch sent by the browser. Idempotent on (attempt, seq)."""
    saved = 0
    for raw in events[:MAX_EVENTS_PER_BATCH]:
        try:
            seq = int(raw["seq"])
            t_ms = max(0, int(raw.get("t", 0)))
            etype = str(raw["type"])
        except (KeyError, TypeError, ValueError):
            continue
        if etype not in VALID_TYPES:
            continue
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        try:
            with transaction.atomic():
                LabEvent.objects.create(
                    attempt=attempt, seq=seq, t_ms=t_ms, type=etype, step=str(raw.get("step", ""))[:48], payload=payload
                )
            saved += 1
        except IntegrityError:
            continue  # already stored (retry of a batch)
    return saved


def _score_choices(fields, answers: dict) -> tuple[int, int]:
    correct = total = 0
    for f in fields:
        right = {o.key for o in f.options if o.correct}
        if not right:
            continue
        total += 1
        if answers.get(f.key) in right:
            correct += 1
    return correct, total


def save_journal(attempt: LabAttempt, experiment: ExperimentSpec, data: dict) -> LabAttempt:
    allowed = {f.key for f in experiment.journal}
    clean = {k: str(v)[:2000] for k, v in data.items() if k in allowed}
    attempt.journal = clean
    attempt.journal_correct, attempt.journal_total = _score_choices(experiment.journal, clean)
    attempt.save(update_fields=["journal", "journal_correct", "journal_total"])
    return attempt


def _recompute_metrics(attempt: LabAttempt):
    counts = Counter(attempt.events.values_list("type", flat=True))
    attempt.order_errors = counts[LabEvent.Type.ORDER_ERROR]
    attempt.safety_warnings = counts[LabEvent.Type.SAFETY_WARNING]
    attempt.wrong_items = counts[LabEvent.Type.WRONG_ITEM]
    attempt.wrong_choices = counts[LabEvent.Type.WRONG_CHOICE]
    attempt.hints_used = counts[LabEvent.Type.HINT]
    # time spent on each step = time between consecutive step_done events
    times, last = {}, 0
    for step, t in attempt.events.filter(type=LabEvent.Type.STEP_DONE).values_list("step", "t_ms"):
        times[step] = t - last
        last = t
    attempt.step_times = times


def finish_attempt(attempt: LabAttempt) -> LabAttempt:
    if attempt.status == LabAttempt.Status.IN_PROGRESS:
        attempt.finished_at = timezone.now()
        attempt.duration_s = int((attempt.finished_at - attempt.started_at).total_seconds())
        attempt.status = LabAttempt.Status.FINISHED
    _recompute_metrics(attempt)
    attempt.save()
    return attempt


def submit_analysis(attempt: LabAttempt, experiment: ExperimentSpec, answers: dict) -> LabAttempt:
    allowed = {q.key for q in experiment.questions}
    clean = {k: str(v)[:4000] for k, v in answers.items() if k in allowed}
    attempt.analysis = clean
    attempt.analysis_correct, attempt.analysis_total = _score_choices(experiment.questions, clean)
    attempt.status = LabAttempt.Status.ANALYSED
    lab = get_lab(attempt.lab_key)
    attempt.score_percent = attempt_score(attempt, lab.scoring if lab else LabScoring())
    attempt.save(update_fields=["analysis", "analysis_correct", "analysis_total", "status", "score_percent"])
    return attempt
