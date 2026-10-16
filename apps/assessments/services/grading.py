"""Auto-grading of one answer. Pure functions: (question, raw input) → GradedAnswer."""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .. import chem
from ..models import Question

ZERO = Decimal("0")


@dataclass
class GradedAnswer:
    is_correct: bool
    points: Decimal
    choice_ids: list[int] = field(default_factory=list)
    text_value: str = ""
    numeric_value: Decimal | None = None


def parse_number(raw) -> Decimal | None:
    """Accepts "2,24", "2.24", " 2 240,5 ", "−3" (unicode minus); returns None when it is not a number."""
    text = str(raw or "").strip().replace("−", "-").replace(",", ".")
    text = re.sub(r"[\s  ]", "", text)
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def normalize_text(raw) -> str:
    """Case, spacing and trailing punctuation do not matter; Unicode is NFC-normalised."""
    text = unicodedata.normalize("NFC", str(raw or "")).casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" .,;:!?«»\"'")


def _choice_ids(raw) -> list[int]:
    values = raw if isinstance(raw, list | tuple) else [raw]
    ids = []
    for v in values:
        try:
            ids.append(int(v))
        except (TypeError, ValueError):
            continue
    return sorted(set(ids))


def grade(question: Question, raw) -> GradedAnswer:
    full = question.points
    kind = question.kind
    if kind in (Question.Kind.SINGLE, Question.Kind.MULTIPLE):
        valid = {c.pk: c.is_correct for c in question.choices.all()}
        chosen = [i for i in _choice_ids(raw) if i in valid]
        if kind == Question.Kind.SINGLE:
            chosen = chosen[:1]
        correct = {pk for pk, ok in valid.items() if ok}
        ok = bool(chosen) and set(chosen) == correct
        return GradedAnswer(ok, full if ok else ZERO, choice_ids=chosen)
    if kind == Question.Kind.NUMERIC:
        value = parse_number(raw)
        ok = (
            value is not None
            and question.numeric_answer is not None
            and abs(value - question.numeric_answer) <= (question.numeric_tolerance or ZERO)
        )
        return GradedAnswer(ok, full if ok else ZERO, text_value=str(raw or "")[:200], numeric_value=value)
    if kind == Question.Kind.SHORT_TEXT:
        given = normalize_text(raw)
        accepted = {normalize_text(a) for a in (question.accepted_answers or [])}
        ok = bool(given) and given in accepted
        return GradedAnswer(ok, full if ok else ZERO, text_value=str(raw or "")[:500])
    if kind in (Question.Kind.FORMULA, Question.Kind.EQUATION):
        given = str(raw or "").strip()
        match = chem.formulas_equal if kind == Question.Kind.FORMULA else chem.equation_matches
        ok = bool(given) and any(match(expected, given) for expected in question.accepted_answers or [])
        return GradedAnswer(ok, full if ok else ZERO, text_value=given[:500])
    raise ValueError(f"Unknown question kind: {kind}")
