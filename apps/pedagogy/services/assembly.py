"""«Assemble the lesson», the trial with the AI student and «Assemble the final version» (guide @S4-ASSEMBLE).

Assembling joins the stages in order into one 45-minute lesson and freezes it as a LessonVersion; the AI student then
does each stage of that version at one readiness level (one request per stage, on demand); after the trial the
student revises the stages and assembles the final version — the lesson is closed and goes to the portfolio."""

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.ai import services as ai
from apps.core.html import html_to_text

from .. import frames
from ..models import Lesson, LessonEvent, LessonVersion, Trial, TrialTurn
from .lessons import LessonError, _editable, _log, clean

E = LessonEvent.Action
TASK_FIELDS = ("student_task", "experiment")  # «Тапсырма» of the AI student's window: what the students are to do


def problems(lesson: Lesson) -> list[dict]:
    """What stops the assembly: empty details, empty stages, the minutes not adding up to the lesson's duration."""
    out = []
    if not (lesson.title.strip() and lesson.topic.strip() and lesson.aim.strip()):
        out.append({"code": "details"})
    stages = list(lesson.stages.all())
    for stage in stages:
        if not any(stage.fields.values()):
            out.append({"code": "empty_stage", "order": stage.order, "title": stage.title})
    total = sum(s.minutes for s in stages)
    if total != lesson.duration_min:
        out.append({"code": "minutes", "total": total, "duration": lesson.duration_min})
    return out


@transaction.atomic
def save_details(lesson: Lesson, *, title: str, topic: str, aim: str, outcomes: str) -> Lesson:
    """The lesson's name, topic, aim and expected results (guide @S4-ASSEMBLE 1, item 1)."""
    _editable(lesson)
    values = {
        "title": (title or "").strip()[:255],
        "topic": (topic or "").strip()[:255],
        "aim": (aim or "").strip()[:4000],
        "outcomes": clean(outcomes),
    }
    if values != {k: getattr(lesson, k) for k in values}:
        for field, value in values.items():
            setattr(lesson, field, value)
        lesson.save()
        _log(lesson, E.DETAILS_SAVED)
    return lesson


def snapshot(lesson: Lesson) -> dict:
    """The whole lesson as it is now: details, the template it came from, the stages with their minutes and fields."""
    template = lesson.source_template
    stages, start = [], 0
    for stage in lesson.stages.all():
        stages.append({
            "order": stage.order, "key": stage.key, "title": stage.title, "minutes": stage.minutes, "start": start,
            "end": start + stage.minutes, "fields": dict(stage.fields), "redesigned": stage.edited,
        })  # fmt: skip
        start += stage.minutes
    return {
        "title": lesson.title, "topic": lesson.topic, "grade": lesson.grade, "duration_min": lesson.duration_min,
        "aim": lesson.aim, "outcomes": lesson.outcomes, "frame": lesson.frame, "kind": lesson.kind,
        "method": lesson.method, "digital_tools": lesson.digital_tools,
        "subject": template.subject if template else "",
        "template": {
            "code": template.code, "number": template.number, "name": template.name,
            "technology": template.technology, "product": template.product,
        } if template else None,
        "stages": stages,
    }  # fmt: skip


def _version(lesson, reason) -> LessonVersion:
    number = (lesson.versions.aggregate(n=Max("number"))["n"] or 0) + 1
    return LessonVersion.objects.create(lesson=lesson, number=number, reason=reason, snapshot=snapshot(lesson))


@transaction.atomic
def assemble(lesson: Lesson) -> LessonVersion:
    """«Assemble the lesson»: a new version of the lesson as it is; the lesson becomes «assembled»."""
    lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    _editable(lesson)
    if problems(lesson):
        raise LessonError("not_ready")
    version = _version(lesson, LessonVersion.Reason.ASSEMBLE)
    if lesson.status == Lesson.Status.DRAFT:
        lesson.status = Lesson.Status.ASSEMBLED
        lesson.save(update_fields=["status", "updated_at"])
    _log(lesson, E.ASSEMBLED, version=version.number)
    return version


def assembled_version(lesson: Lesson) -> LessonVersion | None:
    return lesson.versions.filter(reason=LessonVersion.Reason.ASSEMBLE).order_by("-number").first()


@transaction.atomic
def start_trial(lesson: Lesson, level: str) -> Trial:
    """«Try it out with the AI student» on the latest assembled version, at the chosen level."""
    _editable(lesson)
    version = assembled_version(lesson)
    if version is None:
        raise LessonError("not_assembled")
    if level not in Trial.Level.values:
        raise LessonError("level")
    return Trial.objects.create(lesson=lesson, version=version, level=level)


def stage_of(trial: Trial, order: int) -> dict:
    stage = next((s for s in trial.version.snapshot["stages"] if s["order"] == order), None)
    if stage is None:
        raise LessonError("stage")
    return stage


def task_html(stage: dict) -> str:
    return "".join(stage["fields"].get(key, "") for key in TASK_FIELDS)


def _context(trial: Trial, stage: dict) -> str:
    data = trial.version.snapshot
    labels = {f.key: str(f.label) for f in frames.fields_of(data.get("frame", "template"), stage.get("key", ""))}
    outline = "\n".join(f"{s['order']}. «{s['title']}» – {s['minutes']} min" for s in data["stages"])
    content = "\n\n".join(
        f"{labels.get(key, key)}:\n{html_to_text(html)}" for key, html in stage["fields"].items() if html
    )
    return (
        f"A chemistry lesson for {data.get('grade') or 'school'} students, {data['duration_min']} minutes.\n"
        f"Lesson topic: {data['topic']}\nLesson aim: {data['aim']}\nStages:\n{outline}\n\n"
        f"The stage to do: {stage['order']} «{stage['title']}» ({stage['start']}–{stage['end']} min), "
        f"written by the future teacher:\n{ai.quote(content)}"
    )


def run_turn(trial: Trial, order: int, *, client=None) -> TrialTurn:
    """«See the AI student's answer» on one stage: the AI student's structured answer, made once per trial and stage.
    Raises ai.LimitReached / ai.AIUnavailable when the AI cannot answer now (not atomic: the AI log of a failed call
    stays)."""
    turn = trial.turns.filter(stage_order=order).first()
    if turn:
        return turn
    stage = stage_of(trial, order)
    message = ai.simulate(
        trial.lesson.owner, context_type="trial", context_id=trial.pk, context=_context(trial, stage),
        level=trial.level, intent=f"stage_{order}", client=client,
    )  # fmt: skip
    data = message.structured
    try:
        with transaction.atomic():
            turn = TrialTurn.objects.create(
                trial=trial, stage_order=order, stage_title=stage["title"], task=task_html(stage),
                answer=data["answer"], answer_type=data["answer_type"], possible_error=data["possible_error"],
                difficulty=data["difficulty"], suggestion=data["suggestion"], message_id=message.pk,
            )  # fmt: skip
    except IntegrityError:  # a second click while the first answer was coming
        return trial.turns.get(stage_order=order)
    if trial.finished_at is None and trial.turns.count() >= len(trial.version.snapshot["stages"]):
        trial.finished_at = timezone.now()
        trial.save(update_fields=["finished_at"])
        Lesson.objects.filter(pk=trial.lesson_id, status=Lesson.Status.ASSEMBLED).update(status=Lesson.Status.TESTED)
    return turn


def finished_trial(lesson: Lesson) -> Trial | None:
    return lesson.trials.filter(finished_at__isnull=False).order_by("-finished_at").first()


@transaction.atomic
def finalize(lesson: Lesson) -> LessonVersion:
    """«Assemble the final version»: after a trial with the AI student, the lesson as revised is frozen and closed."""
    lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    _editable(lesson)
    if finished_trial(lesson) is None:
        raise LessonError("no_trial")
    if problems(lesson):
        raise LessonError("not_ready")
    version = _version(lesson, LessonVersion.Reason.FINAL)
    lesson.status = Lesson.Status.FINAL
    lesson.save(update_fields=["status", "updated_at"])
    _log(lesson, E.FINAL, version=version.number)
    return version
