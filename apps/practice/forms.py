"""The practice form: widgets for each answer field and turning POST data back into raw answers."""

import json

from .checkers import shuffled_options
from .models import PracticeItem

K = PracticeItem.Kind


def collect_answers(task, data) -> dict:
    """POST → {item_id: raw} in the shapes the checkers expect (see checkers.py)."""
    answers = {}
    for item in task.items.all():
        name = f"q{item.pk}"
        spec = item.answer_spec or {}
        if item.kind == K.NUMERIC:
            answers[item.pk] = {"value": data.get(f"{name}_value", ""), "unit": data.get(f"{name}_unit", "")}
        elif item.kind == K.CHOICE:
            answers[item.pk] = data.getlist(name)
        elif item.kind == K.MATCHING:
            lefts = list(spec.get("pairs", {}))
            answers[item.pk] = {
                left: data.get(f"{name}_m{i}", "") for i, left in enumerate(lefts) if data.get(f"{name}_m{i}")
            }
        elif item.kind == K.ORDERING:
            steps = shuffled_options(item.pk, list(spec.get("order", [])))
            positions = []
            for i, step in enumerate(steps):
                try:
                    positions.append((int(data.get(f"{name}_o{i}", "")), i, step))
                except ValueError:
                    positions.append((len(steps) + i + 1, i, step))  # no position given → at the end
            answers[item.pk] = [step for _pos, _i, step in sorted(positions)]
        else:
            answers[item.pk] = data.get(name, "")
    return answers


def _previous(answer):
    if answer is None:
        return None
    text = answer.raw_value
    if answer.item.kind in (K.NUMERIC, K.CHOICE, K.MATCHING, K.ORDERING):
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
    return text


def widget_rows(task, submission=None) -> list[dict]:
    """Everything a template needs to draw each field, pre-filled with the last answers."""
    previous = {a.item_id: a for a in submission.answers.select_related("item")} if submission else {}
    rows = []
    for item in task.items.all():
        spec = item.answer_spec or {}
        prev = _previous(previous.get(item.pk))
        row = {"item": item, "name": f"q{item.pk}", "value": prev if isinstance(prev, str) else ""}
        if item.kind == K.NUMERIC:
            prev = prev if isinstance(prev, dict) else {}
            row.update(value=prev.get("value", ""), unit=prev.get("unit") or spec.get("unit", ""))
            row["units"] = spec.get("units") or ([spec["unit"]] if spec.get("unit") else [])
        elif item.kind in (K.CHOICE, K.BLANK):
            row["options"] = spec.get("options") or []
            row["multiple"] = len(spec.get("correct") or []) > 1
            row["chosen"] = prev if isinstance(prev, list) else ([prev] if prev else [])
        elif item.kind == K.MATCHING:
            pairs = spec.get("pairs", {})
            prev = prev if isinstance(prev, dict) else {}
            rights = shuffled_options(item.pk, list(pairs.values()))
            row["pairs"] = [
                {"index": i, "left": left, "rights": rights, "chosen": prev.get(left, "")}
                for i, left in enumerate(pairs)
            ]
        elif item.kind == K.ORDERING:
            steps = shuffled_options(item.pk, list(spec.get("order", [])))
            order = prev if isinstance(prev, list) else []
            row["steps"] = [
                {"index": i, "text": step, "position": (order.index(step) + 1) if step in order else ""}
                for i, step in enumerate(steps)
            ]
            row["positions"] = list(range(1, len(steps) + 1))
        rows.append(row)
    return rows
