"""Section 8 — the independent authorial lesson (guide @S8): the student designs a new lesson fully on their own
(II: details; stages of their own choosing, 45 minutes at most), «Айгерім» gives expert opinions (III; «Check again»
compares with the previous one), «Submit for the trial» checks the structure (V), the lesson is tried out stage by
stage with the AI student or in a real audience (the teacher enters the protocol), «Айгерім» analyses the trial (VI)
and the teacher confirms — the important scientific and final decisions are the teacher's. Then the next cycle (VII)."""

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.ai import services as ai
from apps.core.html import html_to_text

from .. import frames
from ..models import ExpertReview, Lesson, LessonEvent, LessonStage, LessonVersion, Review, Trial
from .assembly import _version, snapshot
from .lessons import LessonError, _editable, _log, clean
from .practice import GRADES, current_order

E = LessonEvent.Action
FRAME = "free"
DETAILS = ("programme", "course_group", "idea", "lab_task", "assessment", "feedback_way")
OPEN = (Lesson.Status.DRAFT, Lesson.Status.SUBMITTED, Lesson.Status.TESTED)


def lessons_of(user):
    return Lesson.objects.filter(owner=user, kind=Lesson.Kind.INDEPENDENT).order_by("cycle", "pk")


@transaction.atomic
def start_independent(user) -> Lesson:
    """«Start developing an independent lesson» (I) or the next cycle (VII): a new empty lesson; the open one is
    returned if there is one."""
    current = lessons_of(user).filter(status__in=OPEN).last()
    if current:
        return current
    cycle = (lessons_of(user).aggregate(n=Max("cycle"))["n"] or 0) + 1
    try:
        with transaction.atomic():
            lesson = Lesson.objects.create(
                owner=user, kind=Lesson.Kind.INDEPENDENT, frame=FRAME, cycle=cycle, title="", duration_min=45
            )
    except IntegrityError:  # pragma: no cover — a double click
        return lessons_of(user).filter(status__in=OPEN).last()
    _log(lesson, E.CREATED, frame=FRAME, cycle=cycle)
    return lesson


@transaction.atomic
def save_details(lesson: Lesson, data: dict) -> Lesson:
    """Part II's details: class, topic, learning aim, expected results, authorial pedagogical idea, teaching methods,
    digital tools, the lab or research task, assessment criteria, the way of feedback; programme, year and group."""
    _editable(lesson)
    grade = str(data.get("grade", "")).strip()
    topic = str(data.get("topic", "")).strip()[:255]
    values = {
        "topic": topic, "title": topic, "grade": grade if grade in GRADES else "",
        "aim": str(data.get("aim", "")).strip()[:4000], "outcomes": clean(str(data.get("outcomes", ""))),
        "method": str(data.get("method", "")).strip()[:4000],
        "digital_tools": str(data.get("digital_tools", "")).strip()[:4000],
    }  # fmt: skip
    details = {**lesson.details, **{k: str(data.get(k, "")).strip()[:4000] for k in DETAILS}}
    if values != {k: getattr(lesson, k) for k in values} or details != lesson.details:
        for name, value in values.items():
            setattr(lesson, name, value)
        lesson.details = details
        lesson.save()
        _log(lesson, E.DETAILS_SAVED)
    return lesson


def total_minutes(lesson) -> int:
    return sum(lesson.stages.values_list("minutes", flat=True))


@transaction.atomic
def add_stage(lesson: Lesson, *, title: str, minutes) -> LessonStage:
    """«Add a new stage»: the stages take 45 minutes at most in all."""
    _editable(lesson)
    title = (title or "").strip()[:255]
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise LessonError("minutes") from None
    if not title or minutes < 1:
        raise LessonError("empty")
    if total_minutes(lesson) + minutes > lesson.duration_min:
        raise LessonError("too_long")
    order = (lesson.stages.aggregate(n=Max("order"))["n"] or 0) + 1
    stage = LessonStage.objects.create(
        lesson=lesson, order=order, key="", title=title, minutes=minutes, fields={f.key: "" for f in frames.FREE}
    )
    _log(lesson, E.SAVED, stage, added=True)
    return stage


@transaction.atomic
def delete_stage(stage: LessonStage) -> None:
    """«Delete the stage»: the next stages move up."""
    lesson = stage.lesson
    _editable(lesson)
    if lesson.events.filter(stage=stage).exists():
        lesson.events.filter(stage=stage).update(stage=None)
    order = stage.order
    stage.delete()
    for later in lesson.stages.filter(order__gt=order).order_by("order"):
        later.order -= 1
        later.save(update_fields=["order"])
    _log(lesson, E.SAVED, removed=order)


def problems(lesson: Lesson) -> list[dict]:
    """What stops «Submit for the trial»: the details, no stages or an empty stage, more than 45 minutes."""
    out = []
    if not (lesson.topic.strip() and lesson.aim.strip() and lesson.grade):
        out.append({"code": "details"})
    stages = list(lesson.stages.all())
    if not stages:
        out.append({"code": "no_stages"})
    for stage in stages:
        if not any(stage.fields.values()):
            out.append({"code": "empty_stage", "order": stage.order, "title": stage.title})
    total = sum(s.minutes for s in stages)
    if total > lesson.duration_min:
        out.append({"code": "minutes", "total": total, "duration": lesson.duration_min})
    return out


def _lesson_text(data: dict) -> str:
    labels = {f.key: str(f.label) for f in frames.FREE}
    parts = [
        f"Topic: {data['topic']}; grade: {data.get('grade') or '—'}; {data['duration_min']} minutes.",
        f"Learning aim: {data['aim']}", f"Expected results: {html_to_text(data['outcomes'])}",
        f"Authorial pedagogical idea: {data.get('details', {}).get('idea', '') or '—'}",
        f"Teaching methods: {data.get('method') or '—'}; digital tools: {data.get('digital_tools') or '—'}",
        f"Lab or research task: {data.get('details', {}).get('lab_task', '') or '—'}",
        f"Assessment criteria: {data.get('details', {}).get('assessment', '') or '—'}",
        f"Way of feedback: {data.get('details', {}).get('feedback_way', '') or '—'}",
    ]  # fmt: skip
    for s in data["stages"]:
        body = "\n".join(f"- {labels.get(k, k)}: {html_to_text(v)}" for k, v in s["fields"].items() if v)
        parts.append(f"\nStage {s['order']} «{s['title']}» ({s['start']}–{s['end']} min)\n{body or '(empty)'}")
    return "\n".join(parts)


def _snapshot(lesson) -> dict:
    data = snapshot(lesson)
    data["details"] = dict(lesson.details)
    return data


def _review_text(review: ExpertReview) -> str:
    items = "\n".join(f"- {k}: {v['status']} — {v['text']}" for k, v in review.items.items())
    return f"Status: {review.status}. Focus: {review.focus}.\n{items}\nSummary: {review.summary}"


def expert_review(lesson: Lesson, *, client=None) -> ExpertReview:
    """«See Айгерім's opinion» / «Check again»: the six dimensions on the project as it is; the previous opinion is
    given to compare the first and the corrected version."""
    _editable(lesson)
    data = _snapshot(lesson)
    previous = lesson.expert_reviews.filter(kind=ExpertReview.Kind.DRAFT).first()
    context = f"The independent lesson project:\n{ai.quote(_lesson_text(data))}"
    if previous:
        context += f"\n\nThe previous opinion (on the earlier version):\n{_review_text(previous)}"
    message = ai.review(lesson.owner, context_type="lesson", context_id=lesson.pk, context=context, client=client)
    return _store(lesson, message, ExpertReview.Kind.DRAFT, data, previous=previous)


def _store(lesson, message, kind, data, *, previous=None, trial=None) -> ExpertReview:
    d = message.structured
    return ExpertReview.objects.create(
        lesson=lesson, trial=trial, kind=kind, snapshot=data, items=d["items"], status=d["status"], focus=d["focus"],
        summary=d["summary"], strengths=d["strengths"], suggestions=d["suggestions"], change=d["change"],
        previous=previous, message_id=message.pk,
    )  # fmt: skip


@transaction.atomic
def submit(lesson: Lesson) -> LessonVersion:
    """«Submit for the trial»: the structure is checked (V); the lesson waits for its trial date."""
    lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    _editable(lesson)
    if problems(lesson):
        raise LessonError("not_ready")
    version = _version(lesson, LessonVersion.Reason.ASSEMBLE)
    if lesson.status == Lesson.Status.DRAFT:
        lesson.status = Lesson.Status.SUBMITTED
        lesson.save(update_fields=["status", "updated_at"])
    _log(lesson, E.ASSEMBLED, version=version.number)
    return version


def open_trial(lesson):
    return lesson.trials.filter(finished_at__isnull=True).first()


@transaction.atomic
def start_trial(lesson: Lesson, *, grade: str, level: str) -> Trial:
    """The trial with the AI student, stage by stage (the class and the level); after «Submit for the trial»."""
    _editable(lesson)
    if lesson.status not in (Lesson.Status.SUBMITTED, Lesson.Status.TESTED):
        raise LessonError("not_submitted")
    if problems(lesson):
        raise LessonError("not_ready")
    if level not in Trial.Level.values or grade not in GRADES:
        raise LessonError("level")
    if open_trial(lesson):
        raise LessonError("open_trial")
    version = _version(lesson, LessonVersion.Reason.TRIAL)
    return Trial.objects.create(lesson=lesson, version=version, level=level, grade=grade, mode=Trial.Mode.STEPWISE)


@transaction.atomic
def finish_trial(trial: Trial) -> Trial:
    """Every stage analysed → the trial is finished; the lesson is «tried out»."""
    if trial.finished_at:
        return trial
    if trial.mode == Trial.Mode.STEPWISE and current_order(trial) is not None:
        raise LessonError("not_finished")
    trial.finished_at = timezone.now()
    trial.save(update_fields=["finished_at"])
    Lesson.objects.filter(pk=trial.lesson_id, status__in=OPEN).update(status=Lesson.Status.TESTED)
    return trial


@transaction.atomic
def record_real_trial(lesson: Lesson, teacher, *, grade: str, notes: str) -> Trial:
    """A trial in a real audience organised by the teacher: the teacher enters its protocol."""
    _editable(lesson)
    notes = (notes or "").strip()[:20000]
    if not notes:
        raise LessonError("empty")
    version = _version(lesson, LessonVersion.Reason.TRIAL)
    trial = Trial.objects.create(
        lesson=lesson, version=version, mode=Trial.Mode.REAL, grade=grade if grade in GRADES else "", notes=notes,
        recorded_by=teacher, finished_at=timezone.now(),
    )  # fmt: skip
    Lesson.objects.filter(pk=lesson.pk, status__in=OPEN).update(status=Lesson.Status.TESTED)
    return trial


def _protocol(trial: Trial) -> str:
    if trial.mode == Trial.Mode.REAL:
        return f"A trial in a real audience (grade {trial.grade or '—'}). The teacher's protocol:\n{trial.notes}"
    lines = [f"A trial with the AI student ({trial.level} level, grade {trial.grade})."]
    for t in trial.turns.order_by("stage_order"):
        lines.append(
            f"\nStage {t.stage_order} «{t.stage_title}», time {t.time_minutes or '—'} min\n"
            f"Explanation: {html_to_text(t.teacher_explanation)}\nTask: {html_to_text(t.task)}\n"
            f"AI student ({t.answer_type}): {t.answer}\nStudent's analysis: {html_to_text(t.student_analysis)}\n"
            f"Follow-up question: {html_to_text(t.follow_up_question) or '—'}\n"
            f"Correction: {html_to_text(t.correction) or '—'}"
        )
    return "\n".join(lines)


def trial_review(trial: Trial, *, client=None) -> ExpertReview:
    """Айгерім's expert analysis after a trial (VI): seven directions, comparing with the previous trial's analysis."""
    if trial.finished_at is None:
        raise LessonError("not_finished")
    lesson = trial.lesson
    previous = lesson.expert_reviews.filter(kind=ExpertReview.Kind.TRIAL).exclude(trial=trial).first()
    context = (
        f"The lesson as tried:\n{ai.quote(_lesson_text(trial.version.snapshot | {'details': lesson.details}))}\n\n"
        f"The trial:\n{ai.quote(_protocol(trial))}"
    )
    if previous:
        context += f"\n\nThe analysis of the previous trial:\n{_review_text(previous)}"
    message = ai.review(
        lesson.owner, context_type="trial", context_id=trial.pk, context=context, after_trial=True, client=client
    )
    return _store(lesson, message, ExpertReview.Kind.TRIAL, trial.version.snapshot, previous=previous, trial=trial)


@transaction.atomic
def confirm(review: ExpertReview, teacher, *, status: str, comment: str = "", score=None) -> ExpertReview:
    """The teacher confirms (or changes) Айгерім's status. For an analysis after a trial the teacher also gives the
    final grade (0–10); «Fits» closes the lesson — the cycle is complete."""
    if status not in ExpertReview.Status.values:
        raise LessonError("status")
    review.teacher_status = status
    review.teacher_comment = (comment or "").strip()[:4000]
    review.confirmed_by = teacher
    review.confirmed_at = timezone.now()
    review.save(update_fields=["teacher_status", "teacher_comment", "confirmed_by", "confirmed_at"])
    lesson = review.lesson
    if review.kind == ExpertReview.Kind.TRIAL and review.trial_id:
        try:
            points = int(score)
        except (TypeError, ValueError):
            raise LessonError("score") from None
        if not 0 <= points <= 10:
            raise LessonError("score")
        Review.objects.update_or_create(
            lesson=lesson, trial=review.trial,
            defaults={"teacher": teacher, "scores": {"total": points}, "total": points, "comment": review.teacher_comment},
        )  # fmt: skip
        if status == ExpertReview.Status.OK:
            lesson.status = Lesson.Status.FINAL
            lesson.save(update_fields=["status", "updated_at"])
            _log(lesson, E.FINAL, trial=review.trial_id)
    return review
