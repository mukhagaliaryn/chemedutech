"""The student's lesson from an authorial template (guide @S4-AI «ЖИ-ассистенттің жұмыс істеу механизмі»):
choose a template → «Create my version» (a copy) → choose a stage → «Clear the content» (the original goes out of the
editor, an empty work area opens) → write the stage with the AI assistant → save. Every step is logged."""

import nh3
from django.db import transaction
from django.utils import timezone

from apps.core.html import html_to_text

from .. import frames
from ..models import Lesson, LessonEvent, LessonStage, LessonTemplate

TEXT_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "sub", "sup", "ul", "ol", "li"}
MAX_FIELD = 20000
MAX_MINUTES = 45

E = LessonEvent.Action


class LessonError(Exception):
    """The change is not allowed (a stage that was not cleared, a final lesson …)."""


def clean(html: str) -> str:
    """The student's rich text: only text marks (sub/sup for formulas, lists); empty editors become ""."""
    html = nh3.clean((html or "")[:MAX_FIELD], tags=TEXT_TAGS, attributes={})
    return html if html_to_text(html).strip() else ""


def template_fields(blocks: list[dict], frame: str = "template") -> dict[str, str]:
    """A template stage's blocks sorted into the frame's fields, each block under its own label (guide order)."""
    out = {key: "" for key in frames.keys_of(frame)}
    for block in blocks:
        out[block["field"]] += f"<p><strong>{block['label']}</strong></p>{block['html']}"
    return out


def _log(lesson, action, stage=None, **data):
    LessonEvent.objects.create(lesson=lesson, stage=stage, action=action, data=data)


@transaction.atomic
def start(user, template: LessonTemplate) -> Lesson:
    """«Create my version»: the student's copy of the template (one per template; the existing one is returned)."""
    lesson = Lesson.objects.filter(owner=user, source_template=template, kind=Lesson.Kind.TEMPLATE_COPY).first()
    if lesson:
        return lesson
    lesson = Lesson.objects.create(
        owner=user, kind=Lesson.Kind.TEMPLATE_COPY, frame="template", source_template=template,
        title=template.name, topic=template.topic, grade=template.grade, duration_min=template.duration_min,
        aim=template.aim, outcomes=template.outcomes,
    )  # fmt: skip
    for stage in template.stages.order_by("order"):
        fields = template_fields(stage.blocks, lesson.frame)
        LessonStage.objects.create(
            lesson=lesson, order=stage.order, title=stage.title, minutes=stage.minutes, fields=fields,
            original={"title": stage.title, "minutes": stage.minutes, "fields": fields},
        )  # fmt: skip
    _log(lesson, E.CREATED, template=template.code)
    return lesson


def _editable(lesson):
    if lesson.status == Lesson.Status.FINAL:
        raise LessonError("final")


@transaction.atomic
def clear(stage: LessonStage) -> LessonStage:
    """«Clear the content»: the stage's fields are emptied; the original stays in ``original``."""
    _editable(stage.lesson)
    if stage.cleared:
        return stage
    stage.fields = {key: "" for key in frames.keys_of(stage.lesson.frame, stage.key)}
    stage.cleared_at = timezone.now()
    stage.save(update_fields=["fields", "cleared_at", "updated_at"])
    _log(stage.lesson, E.CLEARED, stage)
    return stage


@transaction.atomic
def restore(stage: LessonStage) -> LessonStage:
    """The template's content back in the stage; what the student wrote is in the log of saves."""
    _editable(stage.lesson)
    if not stage.cleared:
        return stage
    stage.fields = dict(stage.original.get("fields", {}))
    stage.title = stage.original.get("title", stage.title)
    stage.minutes = stage.original.get("minutes", stage.minutes)
    stage.cleared_at = None
    stage.edited = False
    stage.save()
    _log(stage.lesson, E.RESTORED, stage)
    return stage


def _value(spec, value) -> str:
    """A field's value as stored: minutes as digits (1–45), text cleaned."""
    if spec.number:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())[:2]
        return str(max(1, min(MAX_MINUTES, int(digits)))) if digits else ""
    return clean(str(value or ""))


@transaction.atomic
def save(stage: LessonStage, *, title: str, minutes, fields: dict, inserted: int | None = None) -> LessonStage:
    """The student's version of a stage: a cleared template stage (section 4) or a stage of a frame's fixed stages
    (section 5 — its title and minutes come from the frame). ``inserted`` — the AI message added to the editor before
    this save («Add to the editor», logged as the student's decision)."""
    _editable(stage.lesson)
    frame = stage.lesson.frame
    if frame == "template" and not stage.cleared:
        raise LessonError("not_cleared")
    before = (stage.title, stage.minutes, stage.fields)
    if frame in ("template", "free"):  # the student's own stage names and minutes
        stage.title = (title or "").strip()[:255] or stage.title
        try:
            stage.minutes = max(1, min(MAX_MINUTES, int(minutes)))
        except (TypeError, ValueError):
            pass
    if frame == "free":  # section 8: the stages take 45 minutes at most (guide @S8 II)
        others = sum(s.minutes for s in stage.lesson.stages.exclude(pk=stage.pk))
        if others + stage.minutes > stage.lesson.duration_min:
            raise LessonError("too_long")
    stage.fields = {f.key: _value(f, fields.get(f.key, "")) for f in frames.fields_of(stage.lesson.frame, stage.key)}
    stage.edited = any(stage.fields.values())
    if inserted:
        _log(stage.lesson, E.AI_INSERTED, stage, message=inserted)
    if (stage.title, stage.minutes, stage.fields) == before:
        return stage  # an autosave with nothing new
    stage.save()
    _log(stage.lesson, E.SAVED, stage, chars={k: len(html_to_text(v)) for k, v in stage.fields.items() if v})
    return stage
