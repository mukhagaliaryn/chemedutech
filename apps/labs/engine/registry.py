"""Registry of code-defined labs. Add a new lab by importing it in LABS."""
from __future__ import annotations

from .spec import LabSpec


def _load() -> dict[str, LabSpec]:
    from apps.labs.experiments.t01 import LAB as T01
    from apps.labs.experiments.t02 import LAB as T02
    from apps.labs.experiments.t03 import LAB as T03
    from apps.labs.experiments.t04 import LAB as T04

    labs = [T01, T02, T03, T04]
    return {lab.key: lab for lab in labs}


_cache: dict[str, LabSpec] | None = None


def all_labs() -> dict[str, LabSpec]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def get_lab(key: str) -> LabSpec | None:
    return all_labs().get(key)


def lab_choices():
    return [(k, f"{k} – {lab.title}") for k, lab in all_labs().items()]
