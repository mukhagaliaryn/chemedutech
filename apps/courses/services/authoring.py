"""Course authoring (teacher cabinet, STEP-11): structure, order and safe deletion.

Learning order is Module.order → Topic.number → Stage.order. Moving topics renumbers them course-wide.
Nothing a student has worked on is deleted: such objects are made optional / unpublished instead.
"""

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from ..models import Course, Module, Stage, Topic
from .content import ensure_stage_content


class AuthoringError(Exception):
    """Shown to the teacher as is (already translated)."""


def _next_order(qs) -> int:
    return (qs.aggregate(m=Max("order"))["m"] or 0) + 1


def _reorder(objects: list, ids: list[int]) -> None:
    by_pk = {o.pk: o for o in objects}
    if sorted(by_pk) != sorted(ids):
        raise AuthoringError(_("The list has changed. Reload the page and try again."))
    for position, pk in enumerate(ids, start=1):
        obj = by_pk[pk]
        if obj.order != position:
            obj.order = position
            obj.save(update_fields=["order", "updated_at"])


# --- course -----------------------------------------------------------------------------------


@transaction.atomic
def renumber_topics(course: Course) -> None:
    """Topic numbers follow module order, then topic order (two passes keep numbers unique on the way)."""
    topics = list(
        Topic.objects.filter(module__course=course)
        .select_related("module")
        .order_by("module__order", "module__pk", "order", "number", "pk")
    )
    offset = 1000
    for t in topics:
        Topic.objects.filter(pk=t.pk).update(number=t.number + offset)
    for number, t in enumerate(topics, start=1):
        Topic.objects.filter(pk=t.pk).update(number=number)


@transaction.atomic
def save_module(course: Course, data: dict, module: Module | None = None) -> Module:
    if module is None:
        module = Module(course=course, order=_next_order(course.modules.all()))
    for name in ("title", "description", "weight"):
        if name in data:
            setattr(module, name, data[name])
    module.save()
    return module


@transaction.atomic
def reorder_modules(course: Course, ids: list[int]) -> None:
    _reorder(list(course.modules.all()), ids)
    renumber_topics(course)


def delete_module(module: Module) -> None:
    if module.topics.exists():
        raise AuthoringError(_("Delete or move the topics of the module first."))
    module.delete()


# --- topics -----------------------------------------------------------------------------------


@transaction.atomic
def save_topic(module: Module, data: dict, topic: Topic | None = None) -> Topic:
    if topic is None:
        last = Topic.objects.filter(module__course=module.course).aggregate(m=Max("number"))["m"] or 0
        topic = Topic(module=module, order=_next_order(module.topics.all()), number=last + 1)
    moved = topic.pk and topic.module_id != module.pk
    topic.module = module
    if moved:
        topic.order = _next_order(module.topics.exclude(pk=topic.pk))
    for name in ("title", "summary", "cover", "estimated_minutes", "weight", "is_published"):
        if name in data:
            setattr(topic, name, data[name])
    topic.save()
    renumber_topics(module.course)  # a new or moved topic takes its place in the course order
    topic.refresh_from_db(fields=["number"])
    return topic


@transaction.atomic
def reorder_topics(module: Module, ids: list[int]) -> None:
    _reorder(list(module.topics.all()), ids)
    renumber_topics(module.course)


def set_published(topic: Topic, published: bool) -> None:
    topic.is_published = published
    topic.save(update_fields=["is_published", "updated_at"])


def delete_topic(topic: Topic) -> None:
    if topic.stages.exists():
        raise AuthoringError(_("Delete the stages of the topic first, or unpublish it."))
    course = topic.module.course
    topic.delete()
    renumber_topics(course)


# --- stages -----------------------------------------------------------------------------------


STAGE_FIELDS = ("title", "is_required", "weight", "pass_percent")


@transaction.atomic
def create_stage(topic: Topic, kind: str, data: dict) -> Stage:
    stage = Stage(topic=topic, kind=kind, order=_next_order(topic.stages.all()))
    for name in STAGE_FIELDS:
        if name in data:
            setattr(stage, name, data[name])
    stage.save()
    ensure_stage_content(stage)  # theory / video / lab / test; a practice task is made by the practice app
    return stage


@transaction.atomic
def update_stage(stage: Stage, data: dict) -> Stage:
    for name in STAGE_FIELDS:
        if name in data:
            setattr(stage, name, data[name])
    stage.save()
    return stage


@transaction.atomic
def reorder_stages(topic: Topic, ids: list[int]) -> None:
    _reorder(list(topic.stages.all()), ids)


def stage_has_work(stage: Stage) -> bool:
    """Has any student started it, sent something or taken its quiz? (research data must stay)"""
    if stage.progress.exclude(started_at=None).exists():
        return True
    if stage.lab_attempts.exists() or stage.practice_submissions.exists():
        return True
    quizzes = [q for q in (stage.checkpoint_quiz, getattr(getattr(stage, "test_content", None), "quiz", None)) if q]
    return any(q.attempts.exists() for q in quizzes)


@transaction.atomic
def delete_stage(stage: Stage) -> None:
    if stage_has_work(stage):
        raise AuthoringError(
            _("Students have already worked on this stage. Make it optional or unpublish the topic instead.")
        )
    stage.progress.all().delete()  # only untouched locked / available rows
    content = stage.content
    if content is not None and stage.kind != Stage.Kind.PRACTICE:
        content.delete()
    stage.delete()


def attach_checkpoint(stage: Stage, quiz) -> None:
    stage.checkpoint_quiz = quiz
    stage.save(update_fields=["checkpoint_quiz", "updated_at"])


def attach_benchmark(course, quiz) -> None:
    """The course's pre/post knowledge test (STEP-22): one attempt per phase, answers never shown."""
    course.benchmark_quiz = quiz
    course.save(update_fields=["benchmark_quiz", "updated_at"])


def attach_test(stage: Stage, quiz) -> None:
    ensure_stage_content(stage, quiz=quiz)
