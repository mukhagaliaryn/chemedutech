"""Code-based description of lab works and experiments.

A lab work (one per course topic) contains one or more experiments. Every
experiment is three files that live side by side by convention:

* ``apps/labs/experiments/<lab>/<experiment>.py`` – the ``ExperimentSpec``
  (equipment, ordered commands, safety messages, journal fields, analysis
  questions). All human-readable text is ``gettext_lazy`` so it is translated
  to kk/ru via compilemessages.
* ``apps/labs/templates/labs/scenes/<scene>.html`` – the 2D SVG bench.
* ``static/js/lab/experiments/<scene>.js`` – scene behaviour (animations and
  the physical model), registered with ``ChemLab.scene("<scene>", ...)``.

The generic runner (``static/js/lab/engine.js``) enforces step order, raises
warnings, writes the research log and drives the journal / analysis flow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from django.utils.encoding import force_str

ItemKind = Literal["glass", "device", "reagent"]
StepKind = Literal["place", "action", "process", "choice", "journal", "finish"]


@dataclass(frozen=True)
class Item:
    """A piece of equipment or a reagent shown in the left panel."""

    key: str
    name: str
    kind: ItemKind
    icon: str  # icon id in templates/labs/partials/icons.html
    formula: str = ""
    required: bool = True  # False → distractor, placing it raises a warning
    note: str = ""  # shown when a distractor is placed

    def as_json(self):
        return {
            "key": self.key,
            "name": force_str(self.name),
            "kind": self.kind,
            "icon": self.icon,
            "formula": self.formula,
            "required": self.required,
            "note": force_str(self.note),
        }


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    correct: bool = False
    feedback: str = ""

    def as_json(self):
        return {"key": self.key, "label": force_str(self.label), "correct": self.correct, "feedback": force_str(self.feedback)}


@dataclass(frozen=True)
class Step:
    """One student command.

    * ``place``   – done by dragging ``items`` onto the bench (or the button).
    * ``action``  – instant command, the scene animates it.
    * ``process`` – starts a timed process; the next step unlocks when the
      scene reports that the process is finished.
    * ``choice``  – student picks one of ``options``; wrong options warn.
    * ``journal`` – opens the lab journal; done when required fields are saved.
    * ``finish``  – saves the attempt and opens the analysis task.
    """

    key: str
    command: str
    result: str
    kind: StepKind = "action"
    items: tuple[str, ...] = ()
    options: tuple[Option, ...] = ()
    early_warning: str = ""  # safety/logic message if tried too early
    hint: str = ""
    safety: bool = False  # True → a premature attempt is logged as a safety violation

    def as_json(self):
        return {
            "key": self.key,
            "command": force_str(self.command),
            "result": force_str(self.result),
            "kind": self.kind,
            "items": list(self.items),
            "options": [o.as_json() for o in self.options],
            "early_warning": force_str(self.early_warning),
            "hint": force_str(self.hint),
            "safety": self.safety,
        }


@dataclass(frozen=True)
class JournalField:
    key: str
    label: str
    kind: Literal["text", "number", "choice"] = "text"
    unit: str = ""
    options: tuple[Option, ...] = ()
    required: bool = True

    def as_json(self):
        return {
            "key": self.key,
            "label": force_str(self.label),
            "kind": self.kind,
            "unit": force_str(self.unit),
            "options": [o.as_json() for o in self.options],
            "required": self.required,
        }


@dataclass(frozen=True)
class Question:
    """Analysis question shown after the experiment is finished."""

    key: str
    text: str
    options: tuple[Option, ...] = ()  # empty → open answer

    def as_json(self):
        return {"key": self.key, "text": force_str(self.text), "options": [o.as_json() for o in self.options]}


@dataclass(frozen=True)
class ExperimentSpec:
    key: str  # unique within the lab, e.g. "hydrogen"
    number: int
    title: str
    goal: str
    scene: str  # scene id → template + JS module
    equation: str  # HTML (sub/sup allowed)
    explanation: str
    items: tuple[Item, ...]
    steps: tuple[Step, ...]
    journal: tuple[JournalField, ...] = ()
    questions: tuple[Question, ...] = ()
    extra_equations: tuple[tuple[str, str], ...] = ()  # (label, html)
    params: dict = field(default_factory=dict)  # numbers for the physical model

    @property
    def scene_template(self):
        return f"labs/scenes/{self.scene}.html"

    @property
    def scene_script(self):
        return f"js/lab/experiments/{self.scene}.js"

    def step(self, key):
        return next(s for s in self.steps if s.key == key)

    def as_json(self):
        return {
            "key": self.key,
            "number": self.number,
            "title": force_str(self.title),
            "goal": force_str(self.goal),
            "scene": self.scene,
            "equation": self.equation,
            "explanation": force_str(self.explanation),
            "extra_equations": [[force_str(a), b] for a, b in self.extra_equations],
            "items": [i.as_json() for i in self.items],
            "steps": [s.as_json() for s in self.steps],
            "journal": [j.as_json() for j in self.journal],
            "questions": [q.as_json() for q in self.questions],
            "params": self.params,
        }


@dataclass(frozen=True)
class LabScoring:
    """Lab score formula (ARCHITECTURE §5.4); a lab may override any number.

    process  = max(0, 100 − order·order_errors − safety·safety_warnings − wrong·(wrong_items + wrong_choices))
    journal  = journal_correct / journal_total · 100      (choice fields of the journal)
    analysis = analysis_correct / analysis_total · 100    (closed analysis questions)
    experiment = w_process·process + w_journal·journal + w_analysis·analysis
    A part with nothing to score (no choice fields) drops out and the other weights are rescaled.
    """

    order_error_penalty: float = 10
    safety_warning_penalty: float = 15
    wrong_penalty: float = 5
    weight_process: float = 0.3
    weight_journal: float = 0.2
    weight_analysis: float = 0.5


@dataclass(frozen=True)
class LabSpec:
    key: str  # e.g. "t01"
    topic_number: int
    title: str
    experiments: tuple[ExperimentSpec, ...]
    scoring: LabScoring = field(default_factory=LabScoring)

    def experiment(self, key):
        for e in self.experiments:
            if e.key == key:
                return e
        return None
