"""«Айгерім» (mode ``expert``, guide @S8 III, VI): the expert opinion on an independent lesson — the project by six
dimensions or, after a trial, by seven directions. Logged and counted in the daily limit."""

from __future__ import annotations

from ..models import Mode
from ..prompts import expert
from .chat import AIUnavailable
from .structured import ask_structured, language

STATUSES = ("ok", "needs_more", "revise")


def review(user, *, context_type: str, context_id: int, context: str, after_trial: bool = False, client=None):
    """Returns the AIMessage whose ``structured`` = {items: {key: {status, text}}, status, focus, summary, strengths,
    suggestions, change}. Raises LimitReached / AIUnavailable."""
    keys = expert.TRIAL_DIRECTIONS if after_trial else expert.DRAFT_DIMENSIONS
    system = f"{expert.SYSTEM}\n\n<context>\nInterface language: {language()}.\n{context}\n</context>"
    message = ask_structured(
        user, mode=Mode.EXPERT, prompt_version=expert.PROMPT_VERSION, system=system,
        request="Give your expert opinion after the trial." if after_trial else "Give your expert opinion on the project.",
        schema=expert.schema(keys), context_type=context_type, context_id=context_id,
        intent="trial" if after_trial else "draft", client=client,
    )  # fmt: skip
    data = message.structured
    items = data.get("items") if isinstance(data.get("items"), dict) else None
    if items is None or data.get("status") not in STATUSES:
        raise AIUnavailable("bad structured answer")
    message.structured = {
        "items": {
            k: {"status": items.get(k, {}).get("status") if items.get(k, {}).get("status") in STATUSES else "needs_more",
                "text": str(items.get(k, {}).get("text", "")).strip()}
            for k in keys
        },
        "status": data["status"],
        "focus": str(data.get("focus", "")).strip()[:255],
        "summary": str(data.get("summary", "")).strip(),
        "strengths": [str(x).strip() for x in data.get("strengths", [])][:3],
        "suggestions": [str(x).strip() for x in data.get("suggestions", [])][:3],
        "change": str(data.get("change", "")).strip(),
    }  # fmt: skip
    message.save(update_fields=["structured"])
    return message
