"""Answers of a made-up student: right with the student's accuracy, otherwise a plausible mistake."""

import json
import re
from decimal import Decimal
from types import SimpleNamespace

from apps.core.html import html_to_text

# --- quizzes ---------------------------------------------------------------------------------------


def quiz_answers(questions, accuracy, rng) -> dict:
    answers = {}
    for q in questions:
        right = rng.random() < accuracy
        choices = list(q.choices.all())
        if q.kind == "single":
            good = [c for c in choices if c.is_correct]
            bad = [c for c in choices if not c.is_correct]
            pick = good if right or not bad else bad
            answers[q.pk] = rng.choice(pick).pk
        elif q.kind == "multiple":
            good = [c.pk for c in choices if c.is_correct]
            if right or len(good) < 2:
                answers[q.pk] = good if right else [c.pk for c in choices if not c.is_correct][:1]
            else:
                answers[q.pk] = good[:-1]
        elif q.kind == "numeric":
            value = q.numeric_answer or Decimal(1)
            answers[q.pk] = str(value if right else value * Decimal("1.5"))
        else:
            accepted = q.accepted_answers or [""]
            answers[q.pk] = accepted[0] if right else "білмеймін"
    return answers


# --- practice --------------------------------------------------------------------------------------


def _wrong_equation(equation: str) -> str:
    """The same substances with other coefficients."""
    left, _arrow, right = equation.partition("->")
    species = [s.strip() for s in left.split(" + ")]  # « + » only: «Ag+ + Cl-» keeps the ion charges
    m = re.match(r"(\d+)(.+)", species[0])
    species[0] = m.group(2) if m else "2" + species[0]
    return " + ".join(species) + " ->" + right


def practice_raw(item, right: bool, rng):
    spec = item.answer_spec or {}
    kind = item.kind
    if kind == "equation":
        return spec["equation"] if right else _wrong_equation(spec["equation"])
    if kind == "choice":
        correct = spec.get("correct") or []
        wrong = [o for o in spec.get("options", []) if o not in correct]
        return correct if right or not wrong else [rng.choice(wrong)]
    if kind == "numeric":
        value = float(spec.get("value", 1))
        return {"value": str(value if right else round(value * rng.choice((0.5, 2, 1.4)), 3)), "unit": spec["unit"]}
    if kind == "matching":
        pairs = dict(spec.get("pairs", {}))
        if right or len(pairs) < 2:
            return pairs
        keys, values = list(pairs), list(pairs.values())
        return dict(zip(keys, values[1:] + values[:1], strict=True))
    if kind == "ordering":
        order = list(spec.get("order", []))
        return order if right else order[::-1]
    if kind == "formula":
        return spec.get("formula", "") if right else "X"
    if kind == "text_short":
        return (spec.get("accepted") or [""])[0] if right else "білмеймін"
    return ""


VAGUE = [
    "Бұл реакцияда заттар әрекеттеседі, сондықтан өнім түзіледі.",
    "Менің ойымша, бұл заттың қасиетіне байланысты.",
    "Тотығу дәрежесі өзгереді, сол себепті осындай болады.",
]


def open_text(item, fraction: float, rng) -> str:
    """A fuller answer for a stronger student: the model answer, its first sentences, or a vague guess."""
    model = html_to_text(item.rubric.model_answer) if hasattr(item, "rubric") else ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", model) if s.strip()]
    if fraction >= 0.85 and sentences:
        text = " ".join(sentences)
    elif fraction >= 0.55 and sentences:
        text = " ".join(sentences[: max(1, len(sentences) // 2)])
    else:
        text = rng.choice(VAGUE)
    return f"<p>{text}</p>"


FEEDBACK = {
    "high": "Жауап толық әрі дәл: барлық критерий орындалған. Тұжырымдарыңыз дәлелді.",
    "medium": "Негізгі ой дұрыс, бірақ кейбір критерийлер толық ашылмаған. Себеп-салдар байланысын нақтылаңыз.",
    "low": "Жауап толық емес: негізгі ұғымдар мен дәлелдер жетіспейді. Дәріс материалын қайта қарап шығыңыз.",
}
CRITERION = re.compile(r"- id (\d+) \(max ([\d.]+) points\)")


class DemoAI:
    """Stands in for the Anthropic client in the practice grader: scores every criterion at ``fraction``.

    No request leaves the machine; the grade is stored by the real grading code (model name «demo»)."""

    def __init__(self, rng):
        self.rng = rng
        self.fraction = 1.0
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        prompt = params["messages"][0]["content"]
        criteria = []
        for cid, top in CRITERION.findall(prompt):
            share = min(1.0, max(0.0, self.fraction + self.rng.uniform(-0.15, 0.1)))
            points = round(float(top) * share * 2) / 2
            reason = "Критерий орындалған." if points >= float(top) else "Критерий ішінара орындалған."
            criteria.append({"criterion_id": int(cid), "points": points, "reason": reason if points else "Жоқ."})
        level = "high" if self.fraction >= 0.85 else "medium" if self.fraction >= 0.55 else "low"
        data = {"criteria": criteria, "feedback_kk": FEEDBACK[level], "confidence": "high"}
        text = json.dumps(data, ensure_ascii=False)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
            to_dict=lambda: {"demo": True, "text": text},
        )


# --- labs ------------------------------------------------------------------------------------------


def option_key(options, right: bool, rng) -> str:
    good = [o.key for o in options if o.correct]
    bad = [o.key for o in options if not o.correct]
    if right and good:
        return rng.choice(good)
    return rng.choice(bad or good)


def lab_journal(spec, accuracy, rng) -> dict:
    data = {}
    for f in spec.journal:
        right = rng.random() < accuracy
        if f.kind == "choice" and f.options:
            data[f.key] = option_key(f.options, right, rng)
        elif f.kind == "equation" and f.answer:
            data[f.key] = f.answer if right else _wrong_equation(f.answer)
        elif f.kind == "number":
            data[f.key] = str(rng.randint(1, 20))
        else:
            data[f.key] = rng.choice(["Газ бөлінді.", "Түсі өзгерді.", "Тұнба түзілді.", "Өзгеріс байқалды."])
    return data


def lab_analysis(spec, accuracy, rng) -> dict:
    data = {}
    for q in spec.questions:
        if q.options:
            data[q.key] = option_key(q.options, rng.random() < accuracy, rng)
        else:
            data[q.key] = rng.choice(VAGUE)
    return data
