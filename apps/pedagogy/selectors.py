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
        {"key": f.key, "label": f.label, "icon": f.icon, "html": stage.fields.get(f.key, "")}
        for f in frames.fields_of(stage.lesson.frame)
    ]
