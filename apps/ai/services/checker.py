"""The AI assistant in the checker mode (``checker``, guide @S6 III): «correct» / «wrong» for each stage and each of
the seven criteria — nothing else. Logged and counted in the daily limit."""

from __future__ import annotations

from ..models import Mode
from ..prompts import checker
from .chat import AIUnavailable
from .structured import ask_structured, language


def check(user, *, context_type: str, context_id: int, context: str, client=None):
    """Check the work described in ``context``; returns the AIMessage whose ``structured`` = {stages: {"1": "ok", …},
    criteria: {"aim": "ok", …}}. Raises LimitReached / AIUnavailable."""
    system = f"{checker.SYSTEM}\n\n<context>\nInterface language: {language()}.\n{context}\n</context>"
    message = ask_structured(
        user, mode=Mode.CHECKER, prompt_version=checker.PROMPT_VERSION, system=system,
        request="Check the microlesson.", schema=checker.SCHEMA, context_type=context_type, context_id=context_id,
        intent="check", client=client,
    )  # fmt: skip
    data = message.structured
    stages, criteria = data.get("stages"), data.get("criteria")
    if not isinstance(stages, dict) or not isinstance(criteria, dict):
        raise AIUnavailable("bad structured answer")
    message.structured = {
        "stages": {str(n): ("ok" if stages.get(str(n)) == "ok" else "wrong") for n in range(1, 5)},
        "criteria": {k: ("ok" if criteria.get(k) == "ok" else "wrong") for k in checker.CRITERIA},
    }
    message.save(update_fields=["structured"])
    return message


def check_portfolio(user, *, context_type: str, context_id: int, context: str, client=None):
    """Check the reflection and the development map of a portfolio: {items: {"q1": "ok", …, "micro": "wrong"}}."""
    system = f"{checker.PORTFOLIO_SYSTEM}\n\n<context>\nInterface language: {language()}.\n{context}\n</context>"
    message = ask_structured(
        user, mode=Mode.CHECKER, prompt_version=checker.PORTFOLIO_VERSION, system=system,
        request="Check the portfolio.", schema=checker.PORTFOLIO_SCHEMA, context_type=context_type,
        context_id=context_id, intent="check_portfolio", client=client,
    )  # fmt: skip
    items = message.structured.get("items")
    if not isinstance(items, dict):
        raise AIUnavailable("bad structured answer")
    message.structured = {"items": {k: ("ok" if items.get(k) == "ok" else "wrong") for k in checker.PORTFOLIO_ITEMS}}
    message.save(update_fields=["structured"])
    return message
