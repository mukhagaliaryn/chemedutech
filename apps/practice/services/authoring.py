"""Practice task authoring (teacher cabinet). Answered fields are never deleted (research data)."""

import json

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from .. import checkers
from ..models import GradingRubric, PracticeItem, PracticeTask, RubricCriterion


class AuthoringError(Exception):
    """Shown to the teacher as is (already translated)."""


def ensure_task(stage) -> PracticeTask:
    task, _created = PracticeTask.objects.get_or_create(stage=stage, defaults={"title": stage.title})
    return task


def item_in_use(item: PracticeItem) -> bool:
    return item.pk is not None and item.answers.exists()


@transaction.atomic
def save_item(task: PracticeTask, item: PracticeItem) -> PracticeItem:
    """``item`` is validated by the form (answer_spec through checkers.validate_spec)."""
    if item.pk is None:
        item.task = task
        item.order = (task.items.aggregate(m=Max("order"))["m"] or 0) + 1
    elif item_in_use(item):
        stored = PracticeItem.objects.get(pk=item.pk)
        if stored.kind != item.kind:
            raise AuthoringError(_("Students have answered this field: its kind cannot change."))
    item.save()
    return item


@transaction.atomic
def save_rubric(item: PracticeItem, model_answer: str, notes: str, criteria: list[dict]) -> GradingRubric:
    """criteria — [{"criterion": RubricCriterion|None, "text", "points", "delete"}] in order."""
    rubric, _created = GradingRubric.objects.get_or_create(item=item, defaults={"model_answer": model_answer})
    rubric.model_answer, rubric.notes = model_answer, notes
    rubric.save()
    in_use = item_in_use(item)
    for c in criteria:
        if c["delete"] and c["criterion"] is not None:
            if in_use:
                raise AuthoringError(
                    _("Answers were graded by these criteria: a criterion cannot be deleted, only reworded.")
                )
            c["criterion"].delete()
    keep = [c for c in criteria if not c["delete"] and c["text"].strip()]
    for order, c in enumerate(keep, start=1):
        criterion = c["criterion"] or RubricCriterion(rubric=rubric)
        criterion.order, criterion.text, criterion.points = order, c["text"].strip(), c["points"]
        criterion.save()
    return rubric


@transaction.atomic
def delete_item(item: PracticeItem) -> None:
    if item_in_use(item):
        raise AuthoringError(_("Students have answered this field: it cannot be deleted."))
    rubric = getattr(item, "rubric", None)
    if rubric is not None:
        rubric.criteria.all().delete()
        rubric.delete()
    item.delete()


@transaction.atomic
def reorder_items(task: PracticeTask, ids: list[int]) -> None:
    items = {i.pk: i for i in task.items.all()}
    if sorted(items) != sorted(ids):
        raise AuthoringError(_("The list has changed. Reload the page and try again."))
    for order, pk in enumerate(ids, start=1):
        PracticeItem.objects.filter(pk=pk).update(order=order)


def try_answer(item: PracticeItem, answer: str, client=None) -> dict:
    """«Try it»: grade a sample answer the way a student's would be graded; nothing is saved.

    Returns {"result": CheckResult|None, "ai": dict|None, "error": str}. Open fields call the AI.
    """
    from .ai_grading import run_grading

    if item.kind == PracticeItem.Kind.OPEN:
        if not hasattr(item, "rubric"):
            return {"result": None, "ai": None, "error": _("Add a grading rubric with criteria first.")}
        return {"result": None, "ai": run_grading(item, answer, client=client), "error": ""}
    raw = answer
    if item.kind in ("numeric", "choice", "matching", "ordering"):
        try:
            raw = json.loads(answer)
        except json.JSONDecodeError:
            raw = answer if item.kind == "numeric" else [answer]
    try:
        return {"result": checkers.check(item.kind, item.answer_spec, raw), "ai": None, "error": ""}
    except (KeyError, TypeError, ValueError) as exc:
        return {"result": None, "ai": None, "error": f"{type(exc).__name__}: {exc}"}
