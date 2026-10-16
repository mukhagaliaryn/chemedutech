"""Checkers of practice answer fields (ARCHITECTURE §3.6). Pure functions, no database.

check(kind, spec, raw) → CheckResult(fraction 0..1, is_correct, normalized, feedback)

``raw`` is what the form collected: a string for formula / equation / text_short / open / blank,
{"value": "2,24", "unit": "L"} for numeric, a list of option keys for choice, {left: right} for
matching, a list in the student's order for ordering. Feedback never reveals the correct answer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils.translation import gettext as _

from apps.assessments import chem
from apps.assessments.services.grading import normalize_text, parse_number

# unit → (dimension, factor to the base unit)
UNITS = {
    "mL": ("volume", Decimal("0.001")),
    "cm3": ("volume", Decimal("0.001")),
    "L": ("volume", Decimal("1")),
    "dm3": ("volume", Decimal("1")),
    "m3": ("volume", Decimal("1000")),
    "mg": ("mass", Decimal("0.001")),
    "g": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1000")),
    "mmol": ("amount", Decimal("0.001")),
    "mol": ("amount", Decimal("1")),
    "kmol": ("amount", Decimal("1000")),
    "s": ("time", Decimal("1")),
    "min": ("time", Decimal("60")),
    "h": ("time", Decimal("3600")),
    "%": ("fraction", Decimal("1")),
    "g/mol": ("molar_mass", Decimal("1")),
    "mol/L": ("concentration", Decimal("1")),
    "mL/min": ("rate", Decimal("1")),
}
UNIT_ALIASES = {"мл": "mL", "ml": "mL", "л": "L", "l": "L", "г": "g", "мг": "mg", "кг": "kg", "моль": "mol",
                "ммоль": "mmol", "см3": "cm3", "дм3": "dm3", "с": "s", "мин": "min", "сағ": "h"}  # fmt: skip


class SpecError(ValueError):
    """The author's answer_spec is not valid for the kind."""


@dataclass
class CheckResult:
    fraction: float  # share of the points earned, 0..1
    normalized: dict = field(default_factory=dict)
    feedback: str = ""

    @property
    def is_correct(self) -> bool:
        return self.fraction >= 1


def unit_key(unit: str) -> str:
    unit = (unit or "").strip().replace("³", "3")
    return UNIT_ALIASES.get(unit, UNIT_ALIASES.get(unit.lower(), unit))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _options(spec) -> list[str]:
    return [str(o) for o in spec.get("options") or []]


# --- spec validation -------------------------------------------------------------


def validate_spec(kind: str, spec) -> None:
    if not isinstance(spec, dict):
        raise SpecError(_("The correct answer must be a JSON object."))
    try:
        if kind == "numeric":
            if parse_number(spec.get("value")) is None:
                raise SpecError(_('Give the correct number: {"value": 2.24}'))
            for unit in [spec.get("unit"), *(spec.get("units") or [])]:
                if unit and unit_key(unit) not in UNITS:
                    raise SpecError(_("Unknown unit: %(unit)s") % {"unit": unit})
            if spec.get("unit") and spec.get("units") and spec["unit"] not in spec["units"]:
                raise SpecError(_("The answer's unit must be one of «units»."))
        elif kind == "formula":
            chem.parse_formula(spec.get("formula", ""))
        elif kind == "equation":
            equation = chem.parse_equation(spec.get("equation", ""))
            if spec.get("require_balanced", True) and not equation.is_balanced:
                raise SpecError(_("The correct equation is not balanced."))
        elif kind == "text_short":
            if not spec.get("accepted"):
                raise SpecError(_('List the accepted answers: {"accepted": ["…"]}'))
        elif kind in ("choice", "blank"):
            correct = spec.get("correct") or []
            if not correct:
                raise SpecError(_('List the correct answers: {"correct": ["…"]}'))
            options = _options(spec)
            if options and not set(map(str, correct)) <= set(options):
                raise SpecError(_("Every correct answer must be one of the options."))
            if kind == "choice" and not options:
                raise SpecError(_('A choice needs options: {"options": ["…"]}'))
        elif kind == "matching":
            pairs = spec.get("pairs")
            if not isinstance(pairs, dict) or len(pairs) < 2:
                raise SpecError(_('Give at least two pairs: {"pairs": {"left": "right"}}'))
        elif kind == "ordering":
            order = spec.get("order")
            if not isinstance(order, list) or len(order) < 2 or len(set(order)) != len(order):
                raise SpecError(_('Give at least two different steps: {"order": ["…", "…"]}'))
        else:
            raise SpecError(_("Unknown kind: %(kind)s") % {"kind": kind})
    except chem.ChemError as exc:
        raise SpecError(_("Cannot read the chemistry: %(error)s") % {"error": exc}) from exc


# --- checking ----------------------------------------------------------------------

CHEM_MESSAGES = {
    "empty": lambda d: _("The answer is empty."),
    "unknown_element": lambda d: _("There is no element «%(el)s». Check the letters and their case.") % {"el": d},
    "lowercase_element": lambda d: _("An element symbol starts with a capital letter."),
    "unbalanced_brackets": lambda d: _("Check the brackets."),
    "no_arrow": lambda d: _("Write the arrow between the sides: -> or =."),
    "many_arrows": lambda d: _("An equation has one arrow."),
}


def _chem_feedback(error: chem.ChemError) -> str:
    message = CHEM_MESSAGES.get(error.code)
    return message(error.detail) if message else _("The answer could not be read. Check how it is written.")


def check_numeric(spec, raw) -> CheckResult:
    raw = raw if isinstance(raw, dict) else {"value": raw}
    value = parse_number(raw.get("value"))
    if value is None:
        return CheckResult(0, feedback=_("Write a number, e.g. 2,24."))
    expected = Decimal(str(spec["value"]))
    expected_unit = unit_key(spec.get("unit", ""))
    given_unit = unit_key(raw.get("unit") or spec.get("unit", ""))
    if expected_unit:
        if given_unit not in UNITS or UNITS[given_unit][0] != UNITS[expected_unit][0]:
            return CheckResult(0, {"value": str(value), "unit": raw.get("unit", "")}, _("Check the unit."))
        value = value * UNITS[given_unit][1] / UNITS[expected_unit][1]
    tolerance = abs(expected) * Decimal(str(spec.get("tolerance_pct", 1))) / 100
    tolerance = max(tolerance, Decimal(str(spec.get("tolerance_abs", 0))))
    ok = abs(value - expected) <= tolerance
    normalized = {"value": str(value.normalize()), "unit": expected_unit}
    return CheckResult(1 if ok else 0, normalized, "" if ok else _("The number is not right. Check the calculation."))


def check_formula(spec, raw) -> CheckResult:
    try:
        given = chem.parse_formula(raw)
    except chem.ChemError as exc:
        return CheckResult(0, feedback=_chem_feedback(exc))
    ok = chem.parse_formula(spec["formula"]).key == given.key
    return CheckResult(1 if ok else 0, {"formula": given.pretty()}, "" if ok else _("This is not the right substance."))


def check_equation(spec, raw) -> CheckResult:
    try:
        given = chem.parse_equation(raw)
    except chem.ChemError as exc:
        return CheckResult(0, feedback=_chem_feedback(exc))
    result = chem.compare_equations(spec["equation"], given)
    normalized = {"equation": given.pretty(), "balanced": given.is_balanced}
    if not result.same_species:
        return CheckResult(0, normalized, _("Check the substances on both sides."))
    if not spec.get("require_balanced", True) or result.same_coefficients:
        return CheckResult(1, normalized)
    if result.balanced_not_reduced:
        return CheckResult(0.5, normalized, _("Balanced, but the coefficients can be reduced."))
    return CheckResult(0, normalized, _("The equation is not balanced."))


def check_text_short(spec, raw) -> CheckResult:
    given = normalize_text(raw)
    if not given:
        return CheckResult(0, feedback=_("The answer is empty."))
    typos = int(spec.get("typos", 1))
    distance = min(levenshtein(given, normalize_text(a)) for a in spec["accepted"])
    ok = distance <= typos
    return CheckResult(1 if ok else 0, {"text": given}, "" if ok else _("This is not the expected word."))


def check_choice(spec, raw) -> CheckResult:
    chosen = sorted({str(v) for v in (raw if isinstance(raw, list | tuple) else [raw]) if v not in (None, "")})
    correct = sorted({str(v) for v in spec["correct"]})
    ok = chosen == correct
    return CheckResult(1 if ok else 0, {"chosen": chosen}, "" if ok else _("Not the right choice."))


def check_blank(spec, raw) -> CheckResult:
    if _options(spec):
        return check_choice(spec, [raw])
    given = normalize_text(raw)
    ok = given in {normalize_text(a) for a in spec["correct"]}
    return CheckResult(1 if ok else 0, {"text": given}, "" if ok else _("This is not the expected word."))


def check_matching(spec, raw) -> CheckResult:
    pairs = {str(k): str(v) for k, v in spec["pairs"].items()}
    given = {str(k): str(v) for k, v in (raw or {}).items()} if isinstance(raw, dict) else {}
    right = sum(1 for left, value in pairs.items() if given.get(left) == value)
    fraction = right / len(pairs)
    feedback = "" if fraction == 1 else _("%(n)s of %(total)s pairs are right.") % {"n": right, "total": len(pairs)}
    return CheckResult(fraction, {"pairs": given}, feedback)


def check_ordering(spec, raw) -> CheckResult:
    order = [str(s) for s in spec["order"]]
    given = [str(s) for s in raw] if isinstance(raw, list | tuple) else []
    right = sum(1 for i, step in enumerate(order) if i < len(given) and given[i] == step)
    fraction = right / len(order)
    feedback = (
        ""
        if fraction == 1
        else _("%(n)s of %(total)s steps are in the right place.") % {"n": right, "total": len(order)}
    )
    return CheckResult(fraction, {"order": given}, feedback)


CHECKERS = {
    "numeric": check_numeric,
    "formula": check_formula,
    "equation": check_equation,
    "text_short": check_text_short,
    "choice": check_choice,
    "blank": check_blank,
    "matching": check_matching,
    "ordering": check_ordering,
}


def check(kind: str, spec: dict, raw) -> CheckResult:
    if kind not in CHECKERS:
        raise ValueError(f"{kind} is not checked by code")
    return CHECKERS[kind](spec, raw)


def shuffled_options(item_pk: int, values: list) -> list:
    """A stable per-item order for matching/ordering widgets, so the answer order is not given away."""
    return sorted(values, key=lambda v: (hashlib.md5(f"{item_pk}:{v}".encode()).hexdigest(), str(v)))
