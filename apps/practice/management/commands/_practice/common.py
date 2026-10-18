"""Helpers for writing practice fields: each returns (label, prompt, kind, points, answer_spec, hint)."""

EQ_HELP = (
    "<p>Теңдеуді химиялық пернетақтамен немесе қарапайым түрде жазуға болады: <code>2H2 + O2 -> 2H2O</code>, "
    "иондар: <code>Ag+ + Cl- -> AgCl</code>, <code>SO4^2-</code>. Катализатор мен реакция жағдайын (t°) теңдеуге "
    "жазу міндетті емес; ↑ және ↓ белгілері бағаланбайды.</p>"
)

# oxidation-state changes offered in matching fields (the wrong ones are distractors)
CHANGES = [
    "0 → −1", "0 → +1", "0 → +2", "0 → +5", "0 → −2", "+1 → 0", "+2 → 0", "+4 → +2", "+4 → +6", "−1 → 0",
    "−1 → −2", "−2 → 0", "+5 → 0", "−3 → −3",
]  # fmt: skip


def equation(label, prompt, answer, points=2, hint=""):
    return (label, prompt, "equation", points, {"equation": answer, "require_balanced": True}, hint)


def choice(label, prompt, options, correct, points=1, hint=""):
    correct = correct if isinstance(correct, list) else [correct]
    return (label, prompt, "choice", points, {"options": options, "correct": correct}, hint)


def numeric(label, prompt, value, unit, units, points=2, hint="", tolerance_pct=1):
    return (label, prompt, "numeric", points,
            {"value": value, "tolerance_pct": tolerance_pct, "unit": unit, "units": units}, hint)  # fmt: skip


def matching(label, prompt, pairs, points=2, distractors=None, hint=""):
    if distractors is None:  # oxidation-state changes: three wrong ones from CHANGES
        distractors = [c for c in CHANGES if c not in pairs.values()][:3]
    return (label, prompt, "matching", points, {"pairs": pairs, "distractors": distractors}, hint)


def ordering(label, prompt, order, points=2, hint=""):
    return (label, prompt, "ordering", points, {"order": order}, hint)


def open_answer(label, prompt, points, hint=""):
    return (label, prompt, "open", points, None, hint)


def rubric(model_answer, criteria, notes=""):
    """criteria: [(text, points)]; their sum is the points of the open field."""
    return {"model_answer": model_answer, "criteria": criteria, "notes": notes}


MOL = ("mol", ["mol", "mmol"])
GRAM = ("g", ["mg", "g"])
LITRE = ("L", ["mL", "L"])
