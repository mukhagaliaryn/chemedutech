"""Section 5 — the digital research practice (guide @S5): «The development sheet of the digital research practice»
(I — the lesson's details, II — eight stages of the RESEARCH_8 frame), the stepwise trial with the AI student
(IV: the class and level; the stages one by one — the teacher's explanation, the task, the time, the AI student's
answer, the analysis, the next stage; V: correct, partial and wrong answers mixed), the analysis sheet (VI) and
«Finish the trial and gather the results»; the teacher's 10-point grade (VII), kept apart from ICPAI."""

import random

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ai import services as ai
from apps.core.html import html_to_text

from .. import frames
from ..models import Lesson, LessonEvent, LessonStage, LessonTemplate, LessonVersion, Review, Trial, TrialTurn
from .assembly import _version, problems
from .lessons import LessonError, _editable, _log, clean

E = LessonEvent.Action
FRAME = "research_8"
GRADES = ("7", "8", "9", "10", "11")
# the share of correct / partial / wrong answers by level (SPEC §4.5 4); a trial mixes them on purpose (@S5 V)
MIX = {"high": (0.7, 0.2, 0.1), "medium": (0.4, 0.4, 0.2), "low": (0.2, 0.4, 0.4)}
TYPES = ("correct", "partial", "wrong")


@transaction.atomic
def start_practice(user, template: LessonTemplate) -> Lesson:
    """The practice of one authorial template: the empty sheet of eight stages; the student's section 4 lesson of the
    template is its source (shown beside the sheet, not copied — SPEC О-7). One per template; the existing is returned."""
    lesson = Lesson.objects.filter(owner=user, source_template=template, kind=Lesson.Kind.RESEARCH_PRACTICE).first()
    if lesson:
        return lesson
    source = Lesson.objects.filter(owner=user, source_template=template, kind=Lesson.Kind.TEMPLATE_COPY).first()
    lesson = Lesson.objects.create(
        owner=user, kind=Lesson.Kind.RESEARCH_PRACTICE, frame=FRAME, source_template=template, source_lesson=source,
        title=source.title if source else "", topic=source.topic if source else template.topic,
    )  # fmt: skip
    for order, spec in enumerate(frames.RESEARCH_8, start=1):
        LessonStage.objects.create(
            lesson=lesson, order=order, key=spec.key, title=str(spec.title), minutes=spec.minutes,
            fields={f.key: "" for f in spec.fields},
        )  # fmt: skip
    _log(lesson, E.CREATED, template=template.code, frame=FRAME)
    return lesson


@transaction.atomic
def save_sheet_details(lesson: Lesson, data: dict) -> Lesson:
    """Part I of the sheet: name, chemistry topic, class (7–11), aim, expected results, authorial method, digital
    tools (the duration is 45 minutes)."""
    _editable(lesson)
    grade = str(data.get("grade", "")).strip()
    values = {
        "title": str(data.get("title", "")).strip()[:255],
        "topic": str(data.get("topic", "")).strip()[:255],
        "grade": grade if grade in GRADES else "",
        "aim": str(data.get("aim", "")).strip()[:4000],
        "outcomes": clean(str(data.get("outcomes", ""))),
        "method": str(data.get("method", "")).strip()[:4000],
        "digital_tools": str(data.get("digital_tools", "")).strip()[:4000],
    }
    if values != {k: getattr(lesson, k) for k in values}:
        for name, value in values.items():
            setattr(lesson, name, value)
        lesson.save()
        _log(lesson, E.DETAILS_SAVED)
    return lesson


def sheet_problems(lesson: Lesson) -> list[dict]:
    """What stops the trial: the details (with the class) and stages without content."""
    out = problems(lesson)
    if not lesson.grade and not any(p["code"] == "details" for p in out):
        out.insert(0, {"code": "details"})
    return out


@transaction.atomic
def start_stepwise(lesson: Lesson, *, grade: str, level: str) -> Trial:
    """«Try the lesson out»: the class and the AI student's level; the sheet is frozen as a version (reason «trial»)."""
    _editable(lesson)
    if sheet_problems(lesson):
        raise LessonError("not_ready")
    if level not in Trial.Level.values or grade not in GRADES:
        raise LessonError("level")
    version = _version(lesson, LessonVersion.Reason.TRIAL)
    return Trial.objects.create(lesson=lesson, version=version, level=level, grade=grade, mode=Trial.Mode.STEPWISE)


def planned_types(trial: Trial) -> list[str]:
    """The answer type of each stage: the level's mix over the stages, shuffled per trial (the same every time)."""
    count = len(trial.version.snapshot["stages"])
    shares = MIX.get(trial.level, MIX["medium"])
    numbers = [round(share * count) for share in shares]
    numbers[0] += count - sum(numbers)
    types = [t for t, n in zip(TYPES, numbers, strict=True) for _ in range(n)]
    random.Random(trial.pk).shuffle(types)
    return types


def current_order(trial: Trial) -> int | None:
    """The stage open now: the first one not analysed (None when all are)."""
    analysed = set(trial.turns.filter(analysed_at__isnull=False).values_list("stage_order", flat=True))
    return next((s["order"] for s in trial.version.snapshot["stages"] if s["order"] not in analysed), None)


def prefill(stage: dict) -> dict:
    """The stage's explanation, task and time from the sheet (the student may change them in the trial)."""
    spec = frames.stage_spec(FRAME, stage.get("key", ""))
    if spec is None:
        return {"explanation": "", "task": "", "minutes": ""}
    labels = {f.key: str(f.label) for f in spec.fields}

    def join(keys):
        parts = [(labels[k], stage["fields"].get(k, "")) for k in keys if stage["fields"].get(k)]
        if len(parts) == 1:
            return parts[0][1]
        return "".join(f"<p><strong>{label}</strong></p>{html}" for label, html in parts)

    return {"explanation": join(spec.explain), "task": join(spec.task), "minutes": stage["fields"].get(spec.time, "")}


def _context(trial: Trial, stage: dict, explanation: str, task: str, minutes: int) -> str:
    data = trial.version.snapshot
    spec = frames.stage_spec(FRAME, stage.get("key", ""))
    told = f"The teacher's explanation:\n{html_to_text(explanation)}\n\nThe task:\n{html_to_text(task)}"
    return (
        f"A chemistry lesson in grade {trial.grade}, {data['duration_min']} minutes. Topic: {data['topic']}.\n"
        f"Lesson aim: {data['aim']}\n"
        f"The teacher conducts the lesson stage by stage. Now: stage {stage['order']} «{stage['title']}» "
        f"({stage['start']}–{stage['end']} min); its aim: {spec.aim if spec else ''}\n"
        f"Time to do the task: {minutes} min.\n{ai.quote(told)}"
    )


def give_task(trial: Trial, order: int, *, explanation: str, task: str, minutes, client=None) -> TrialTurn:
    """Steps 1–4 of a stage: the teacher's explanation, the task and the time are given; the AI student answers with
    the planned type. Only the open stage; once per stage. Not atomic: the AI log of a failed call stays."""
    _editable(trial.lesson)
    if trial.finished_at or current_order(trial) != order:
        raise LessonError("not_open")
    existing = trial.turns.filter(stage_order=order).first()
    if existing:
        return existing
    explanation, task = clean(explanation), clean(task)
    if not (explanation or task):
        raise LessonError("empty")
    try:
        minutes = max(1, min(45, int(minutes)))
    except (TypeError, ValueError):
        minutes = None
    stage = next(s for s in trial.version.snapshot["stages"] if s["order"] == order)
    planned = planned_types(trial)[order - 1]
    message = ai.simulate(
        trial.lesson.owner, context_type="trial", context_id=trial.pk,
        context=_context(trial, stage, explanation, task, minutes or stage["minutes"]), level=trial.level,
        answer_type=planned, intent=f"stage_{order}", client=client,
    )  # fmt: skip
    data = message.structured
    try:
        with transaction.atomic():
            return TrialTurn.objects.create(
                trial=trial, stage_order=order, stage_title=stage["title"], task=task, teacher_explanation=explanation,
                time_minutes=minutes, answer=data["answer"], answer_type=data["answer_type"],
                possible_error=data["possible_error"], difficulty=data["difficulty"], suggestion=data["suggestion"],
                message_id=message.pk,
            )  # fmt: skip
    except IntegrityError:
        return trial.turns.get(stage_order=order)


@transaction.atomic
def analyse(turn: TrialTurn, *, analysis: str, follow_up: str = "", correction: str = "", improved_task: str = "",
            duration_s=None) -> TrialTurn:  # fmt: skip
    """Step 5 «Analysing the answer» and the analysis sheet (VI): the student's explanation (required), a follow-up
    question, the pedagogical correction, the improved task; then the next stage opens (step 6)."""
    _editable(turn.trial.lesson)
    if turn.trial.finished_at:
        raise LessonError("finished")
    analysis = clean(analysis)
    if not analysis:
        raise LessonError("empty")
    turn.student_analysis = analysis
    turn.follow_up_question = clean(follow_up)
    turn.correction = clean(correction)
    turn.improved_task = clean(improved_task)
    try:
        turn.duration_s = max(0, min(24 * 3600, int(duration_s))) if duration_s not in (None, "") else turn.duration_s
    except (TypeError, ValueError):
        pass
    turn.analysed_at = turn.analysed_at or timezone.now()
    turn.save()
    return turn


@transaction.atomic
def finish(trial: Trial) -> LessonVersion:
    """«Finish the trial and gather the results»: every stage analysed → the practice is closed (status final) and its
    sheet, the AI student's answers and the corrections are kept together as the final version."""
    lesson = Lesson.objects.select_for_update().get(pk=trial.lesson_id)
    _editable(lesson)
    if current_order(trial) is not None:
        raise LessonError("not_finished")
    trial.finished_at = timezone.now()
    trial.save(update_fields=["finished_at"])
    version = _version(lesson, LessonVersion.Reason.FINAL)
    version.snapshot["trial"] = {
        "pk": trial.pk, "grade": trial.grade, "level": trial.level,
        "turns": [
            {k: getattr(t, k) for k in (
                "stage_order", "stage_title", "teacher_explanation", "task", "time_minutes", "answer", "answer_type",
                "possible_error", "difficulty", "suggestion", "student_analysis", "follow_up_question", "correction",
                "improved_task", "duration_s",
            )}
            for t in trial.turns.order_by("stage_order")
        ],
    }  # fmt: skip
    version.save(update_fields=["snapshot"])
    lesson.status = Lesson.Status.FINAL
    lesson.save(update_fields=["status", "updated_at"])
    _log(lesson, E.FINAL, version=version.number, trial=trial.pk)
    return version


@transaction.atomic
def grade(lesson: Lesson, teacher, scores: dict, comment: str = "", trial: Trial | None = None) -> Review:
    """The teacher's 10-point grade, each of the five criteria 0–2: a finished section 5 practice (@S5 VII) or one
    finished trial of the section 6 microlesson (@S6 VI — each trial is graded apart)."""
    if lesson.kind == Lesson.Kind.MICROLESSON:
        if trial is None or trial.lesson_id != lesson.pk or trial.finished_at is None:
            raise LessonError("not_finished")
    elif lesson.kind != Lesson.Kind.RESEARCH_PRACTICE or lesson.status != Lesson.Status.FINAL or trial is not None:
        raise LessonError("not_final")
    clean_scores = {}
    for number, _label in Review.criteria_for(lesson):
        try:
            value = int(scores.get(str(number), scores.get(number)))
        except (TypeError, ValueError):
            raise LessonError("scores") from None
        if not 0 <= value <= Review.MAX_POINTS:
            raise LessonError("scores")
        clean_scores[str(number)] = value
    review, _created = Review.objects.update_or_create(
        lesson=lesson,
        trial=trial,
        defaults={"teacher": teacher, "scores": clean_scores, "total": sum(clean_scores.values()),
                  "comment": (comment or "").strip()[:4000]},
    )  # fmt: skip
    return review
