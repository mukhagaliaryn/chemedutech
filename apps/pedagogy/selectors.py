"""Reads for the lesson designer pages (section 4)."""

from django.db.models import Prefetch

from . import frames
from .models import Lesson, LessonStage, LessonTemplate, TemplateStage


def templates():
    return LessonTemplate.objects.filter(is_active=True).prefetch_related(
        Prefetch("stages", queryset=TemplateStage.objects.order_by("order"))
    )


def lesson_of(user, template) -> Lesson | None:
    return Lesson.objects.filter(owner=user, source_template=template, kind=Lesson.Kind.TEMPLATE_COPY).first()


def timeline(stages) -> list[dict]:
    """Stages with their minutes from–to and share of the lesson (the 45-minute bar of image16)."""
    total = sum(s.minutes for s in stages) or 1
    rows, start = [], 0
    for stage in stages:
        rows.append(
            {"stage": stage, "start": start, "end": start + stage.minutes, "share": stage.minutes * 100 / total}
        )
        start += stage.minutes
    return rows


def template_cards(user) -> list[dict]:
    """The designer's template cards: the template, its stage bar and the student's own lesson, if started."""
    lessons = {
        lesson.source_template_id: lesson
        for lesson in Lesson.objects.filter(owner=user, kind=Lesson.Kind.TEMPLATE_COPY).prefetch_related("stages")
    }
    cards = []
    for template in templates():
        lesson = lessons.get(template.pk)
        stages = list(lesson.stages.all()) if lesson else []
        cards.append({
            "template": template,
            "timeline": timeline(list(template.stages.all())),
            "lesson": lesson,
            "edited": sum(1 for s in stages if s.edited),
            "stage_count": len(stages) or template.stages.count(),
        })  # fmt: skip
    return cards


def template_blocks(stage: TemplateStage) -> list[dict]:
    """A template stage's blocks with the frame field's icon (for the template page)."""
    icons = {f.key: f.icon for f in frames.TEMPLATE}
    return [{**b, "icon": icons.get(b["field"], "list")} for b in stage.blocks]


def stage_fields(stage: LessonStage) -> list[dict]:
    """The stage's frame fields with their labels and the student's (or the copied) HTML."""
    return [
        {"key": f.key, "label": f.label, "icon": f.icon, "number": f.number, "html": stage.fields.get(f.key, "")}
        for f in frames.fields_of(stage.lesson.frame, stage.key)
    ]


# the columns of the assembled lesson's table (picture image17 «Қысқа мерзімді сабақ жоспары») → the frame's fields
PLAN_COLUMNS = (
    ("teacher", ("teacher_action",)),
    ("students", ("student_task", "experiment")),
    ("assessment", ("assessment", "result")),
    ("resources", ("methods",)),
)


def plan_rows(snapshot: dict) -> list[dict]:
    """The stages of a lesson version as table rows: each column a list of (field label, html) — the label is shown
    only where a column holds more than one field."""
    labels = {f.key: f.label for f in frames.fields_of(snapshot.get("frame", "template"))}
    rows = []
    for stage in snapshot["stages"]:
        cells = {}
        for column, keys in PLAN_COLUMNS:
            cells[column] = [
                {"label": labels[k] if len(keys) > 1 else "", "html": stage["fields"].get(k, "")}
                for k in keys
                if stage["fields"].get(k)
            ]
        rows.append({**stage, "cells": cells})
    return rows


def changed_since(lesson: Lesson, snapshot: dict) -> set[int]:
    """The stages whose content differs from a version — «revised tasks» after a trial."""
    then = {s["order"]: (s["title"], s["minutes"], s["fields"]) for s in snapshot["stages"]}
    return {s.order for s in lesson.stages.all() if then.get(s.order) != (s.title, s.minutes, s.fields)}
