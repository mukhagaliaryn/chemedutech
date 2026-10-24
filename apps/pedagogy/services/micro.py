"""Section 6 — the microlesson and the professional trial ground (guide @S6): one microlesson per student, made from a
part of a section 5 practice (I: details; II: four stages of the MICRO_4 frame); the AI assistant only marks each
stage and seven criteria «correct» / «wrong» (III); the trial is a 10-minute dialogue with the AI student (IV) that
may be repeated after changes (V), each trial kept and graded by the teacher apart (VI); «Assemble the microlesson»
closes it (VII)."""

import hashlib
import json

from django.db import IntegrityError, transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.ai import services as ai
from apps.core.html import html_to_text

from .. import frames
from ..models import Check, Lesson, LessonEvent, LessonStage, LessonVersion, Trial, TrialMessage
from .assembly import _version
from .lessons import LessonError, _editable, _log, clean
from .practice import GRADES

E = LessonEvent.Action
FRAME = "micro_4"
DURATION_S = 600  # the microlesson's 10 minutes (@S6 I, IV)
MAX_MESSAGE = 3000


@transaction.atomic
def start_micro(user, practice: Lesson, stage_order: int) -> Lesson:
    """«Create the microlesson»: the student's one microlesson from a part (stage) of a section 5 practice — the part is
    its source (shown, not copied). A second one is not made: the existing microlesson is returned."""
    existing = Lesson.objects.filter(owner=user, kind=Lesson.Kind.MICROLESSON).first()
    if existing:
        return existing
    if practice.owner_id != user.pk or practice.kind != Lesson.Kind.RESEARCH_PRACTICE:
        raise LessonError("source")
    part = practice.stages.filter(order=stage_order).first()
    if part is None:
        raise LessonError("source")
    try:
        with transaction.atomic():
            lesson = Lesson.objects.create(
                owner=user, kind=Lesson.Kind.MICROLESSON, frame=FRAME, source_template=practice.source_template,
                source_lesson=practice, title=practice.topic or practice.title, topic=practice.topic,
                grade=practice.grade, duration_min=10,
                details={"source_stage": part.order, "source_title": part.title},
            )  # fmt: skip
    except IntegrityError:
        return Lesson.objects.get(owner=user, kind=Lesson.Kind.MICROLESSON)
    for order, spec in enumerate(frames.MICRO_4, start=1):
        LessonStage.objects.create(
            lesson=lesson, order=order, key=spec.key, title=str(spec.title), minutes=spec.minutes,
            fields={f.key: "" for f in spec.fields},
        )  # fmt: skip
    _log(lesson, E.CREATED, frame=FRAME, source=practice.pk, part=part.order)
    return lesson


@transaction.atomic
def save_micro_details(lesson: Lesson, data: dict) -> Lesson:
    """Part I: education programme, study year, topic, class (7–11), aim, expected result, pedagogical method,
    digital tool (10 minutes; the student's name comes from the account)."""
    _editable(lesson)
    grade = str(data.get("grade", "")).strip()
    topic = str(data.get("topic", "")).strip()[:255]
    values = {
        "topic": topic,
        "title": topic or lesson.title,
        "grade": grade if grade in GRADES else "",
        "aim": str(data.get("aim", "")).strip()[:4000],
        "outcomes": clean(str(data.get("outcomes", ""))),
        "method": str(data.get("method", "")).strip()[:4000],
        "digital_tools": str(data.get("digital_tools", "")).strip()[:4000],
    }
    details = {
        **lesson.details,
        "programme": str(data.get("programme", "")).strip()[:255],
        "study_year": str(data.get("study_year", "")).strip()[:64],
    }
    if values != {k: getattr(lesson, k) for k in values} or details != lesson.details:
        for name, value in values.items():
            setattr(lesson, name, value)
        lesson.details = details
        lesson.save()
        _log(lesson, E.DETAILS_SAVED)
    return lesson


def fingerprint(lesson: Lesson) -> str:
    """The content the checker looks at: the details and the four stages."""
    data = {
        "topic": lesson.topic, "grade": lesson.grade, "aim": lesson.aim, "outcomes": lesson.outcomes,
        "stages": [s.fields for s in lesson.stages.order_by("order")],
    }  # fmt: skip
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def latest_check(lesson: Lesson) -> Check | None:
    return lesson.checks.order_by("-created_at", "-pk").first()


def check_state(lesson: Lesson) -> dict:
    """The latest check, whether it is for the content as it is now, and whether the trial may start."""
    check = latest_check(lesson)
    current = bool(check) and check.fingerprint == fingerprint(lesson)
    return {"check": check, "current": current, "passed": current and check.passed}


def _text(lesson: Lesson) -> str:
    parts = [
        f"Topic: {lesson.topic}", f"Grade: {lesson.grade or '—'}", f"Aim: {lesson.aim}",
        f"Expected result: {html_to_text(lesson.outcomes)}", f"Pedagogical method: {lesson.method or '—'}",
        f"Digital tool: {lesson.digital_tools or '—'}",
    ]  # fmt: skip
    for stage in lesson.stages.order_by("order"):
        spec = frames.stage_spec(FRAME, stage.key)
        labels = {f.key: str(f.label) for f in spec.fields}
        body = "\n".join(f"- {labels[k]}: {html_to_text(v) or '(empty)'}" for k, v in stage.fields.items())
        parts.append(f"\nStage {stage.order} «{stage.title}» ({spec.start}–{spec.end} min). Aim: {spec.aim}\n{body}")
    return "\n".join(parts)


def check_micro(lesson: Lesson, *, client=None) -> Check:
    """Send the microlesson to the checker (also «Check again»): only «correct» / «wrong» come back."""
    _editable(lesson)
    content = fingerprint(lesson)
    message = ai.check(
        lesson.owner, context_type="microlesson", context_id=lesson.pk, context=ai.quote(_text(lesson)), client=client
    )
    return Check.objects.create(
        lesson=lesson, fingerprint=content, stages=message.structured["stages"],
        criteria=message.structured["criteria"], message_id=message.pk,
    )  # fmt: skip


@transaction.atomic
def start_dialog(lesson: Lesson, *, grade: str, level: str) -> Trial:
    """«Try the microlesson out»: the class and the AI student's level; only after a passed check of the content as it
    is. The microlesson is frozen as a version (each trial keeps the version it tried)."""
    _editable(lesson)
    if not check_state(lesson)["passed"]:
        raise LessonError("not_checked")
    if level not in Trial.Level.values or grade not in GRADES:
        raise LessonError("level")
    if lesson.trials.filter(finished_at__isnull=True).exists():
        raise LessonError("open_trial")
    version = _version(lesson, LessonVersion.Reason.TRIAL)
    return Trial.objects.create(lesson=lesson, version=version, level=level, grade=grade, mode=Trial.Mode.DIALOG)


def elapsed_s(trial: Trial) -> int:
    """The microlesson's time so far: from the start, without the time the AI student took to answer."""
    end = trial.finished_at or timezone.now()
    waited = trial.messages.aggregate(ms=Sum("wait_ms"))["ms"] or 0
    return max(0, int((end - trial.started_at).total_seconds() - waited / 1000))


def stage_at(seconds: int) -> int:
    """The microlesson stage by the timer: 0–2, 2–5, 5–8, 8–10 minutes."""
    for order, spec in enumerate(frames.MICRO_4, start=1):
        if seconds < spec.end * 60:
            return order
    return len(frames.MICRO_4)


def _transcript(trial: Trial) -> str:
    kinds = dict(TrialMessage.Kind.choices)
    lines = []
    for m in trial.messages.order_by("number"):
        lines.append(f"Teacher ({kinds[m.kind]}): {html_to_text(m.text)}")
        lines.append(f"Student: {m.reply}")
    return "\n".join(lines) or "(the microlesson has just started)"


def send(trial: Trial, *, kind: str, text: str, client=None) -> TrialMessage:
    """The teacher's explanation, question or pedagogical action; the AI student replies. The time is up after
    10 minutes: the trial is finished and nothing more is sent (agreed with the user)."""
    _editable(trial.lesson)
    if trial.finished_at:
        raise LessonError("finished")
    if elapsed_s(trial) >= DURATION_S:
        finish_dialog(trial)
        raise LessonError("time_up")
    if kind not in TrialMessage.Kind.values:
        raise LessonError("kind")
    text = (text or "").strip()[:MAX_MESSAGE]
    if not text:
        raise LessonError("empty")
    at = elapsed_s(trial)
    kinds = dict(TrialMessage.Kind.choices)
    context = (
        f"The microlesson (written by the teacher):\n{ai.quote(_text(trial.lesson))}\n\n"
        f"Grade {trial.grade}. Now: {at // 60}:{at % 60:02d} of 10:00, stage {stage_at(at)}.\n"
        f"The dialogue so far:\n{ai.quote(_transcript(trial))}\n\n"
        f"The teacher's new message ({kinds[kind]}):\n{ai.quote(text)}"
    )
    message = ai.reply(
        trial.lesson.owner, context_type="trial", context_id=trial.pk, context=context, level=trial.level,
        intent=kind, client=client,
    )  # fmt: skip
    data = message.structured
    number = (trial.messages.aggregate(n=Max("number"))["n"] or 0) + 1
    return TrialMessage.objects.create(
        trial=trial, number=number, stage_order=stage_at(at), kind=kind, text=text, reply=data["reply"].strip(),
        answer_type=data["answer_type"], at_s=at, wait_ms=message.latency_ms, message_id=message.pk,
    )  # fmt: skip


@transaction.atomic
def finish_dialog(trial: Trial) -> Trial:
    """«Finish the microlesson» (or the timer ran out): the dialogue becomes the trial protocol."""
    if trial.finished_at:
        return trial
    trial.finished_at = timezone.now()
    trial.save(update_fields=["finished_at"])
    Lesson.objects.filter(pk=trial.lesson_id, status=Lesson.Status.DRAFT).update(status=Lesson.Status.TESTED)
    return trial


def trial_number(trial: Trial) -> int:
    """1-сынақ, 2-сынақ … in the order of the microlesson's trials."""
    return trial.lesson.trials.filter(started_at__lte=trial.started_at, pk__lte=trial.pk).count()


@transaction.atomic
def assemble_micro(lesson: Lesson) -> LessonVersion:
    """«Assemble the microlesson»: the latest version, its four stages, the history of the trials with the AI student's
    answers and the changes between them; the microlesson is closed (after at least one finished trial)."""
    lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    _editable(lesson)
    trials = list(lesson.trials.filter(mode=Trial.Mode.DIALOG, finished_at__isnull=False).order_by("started_at"))
    if not trials:
        raise LessonError("no_trial")
    lesson.trials.filter(finished_at__isnull=True).update(finished_at=timezone.now())
    version = _version(lesson, LessonVersion.Reason.FINAL)
    version.snapshot["trials"] = [
        {
            "number": n, "pk": t.pk, "grade": t.grade, "level": t.level, "version": t.version.number,
            "started_at": t.started_at.isoformat(), "seconds": elapsed_s(t),
            "messages": [
                {k: getattr(m, k) for k in ("number", "stage_order", "kind", "text", "reply", "answer_type", "at_s")}
                for m in t.messages.order_by("number")
            ],
        }
        for n, t in enumerate(trials, start=1)
    ]  # fmt: skip
    version.save(update_fields=["snapshot"])
    lesson.status = Lesson.Status.FINAL
    lesson.save(update_fields=["status", "updated_at"])
    _log(lesson, E.FINAL, version=version.number, trials=len(trials))
    return version
