"""The AI student (mode ``student_sim``): one structured answer per lesson stage of a trial (sections 4 and 5 —
the answer, its type, the possible error, the difficulty and the AI assistant's methodical suggestion), or a reply in
the microlesson dialogue (section 6). Every request is logged and counts towards the daily limit."""

from __future__ import annotations

from ..models import Mode
from ..prompts import student_sim
from .chat import AIUnavailable
from .structured import ask_structured, language

FIELDS = tuple(student_sim.SCHEMA["required"])
ANSWER_TYPES = ("correct", "partial", "wrong")


def simulate(
    user,
    *,
    context_type: str,
    context_id: int,
    context: str,
    level: str,
    answer_type: str = "",
    intent: str = "",
    client=None,
):
    """The AI student at ``level`` does one stage described in ``context``; returns the AIMessage whose ``structured``
    holds the five fields; ``answer_type`` (correct / partial / wrong) makes the AI give that kind of answer. Raises
    LimitReached / AIUnavailable like ``ask`` (a failed call is logged)."""
    level = student_sim.LEVELS.get(level, "medium")
    system = (
        f"{student_sim.SYSTEM}\n\n<context>\nInterface language: {language()}.\nReadiness level: {level}.\n"
        + (f"Required answer type: {answer_type}.\n" if answer_type in ANSWER_TYPES else "")
        + f"{context}\n</context>"
    )
    message = ask_structured(
        user, mode=Mode.STUDENT_SIM, prompt_version=student_sim.PROMPT_VERSION, system=system,
        request=f"Do the task of this lesson stage as a {level}-level student, then analyse it.",
        schema=student_sim.SCHEMA, context_type=context_type, context_id=context_id, intent=intent, client=client,
    )  # fmt: skip
    if not all(isinstance(message.structured.get(k), str) for k in FIELDS):
        raise AIUnavailable("bad structured answer")
    message.structured = {k: message.structured[k].strip() for k in FIELDS}
    message.content = message.structured["answer"]
    message.save(update_fields=["structured", "content"])
    return message


def reply(user, *, context_type: str, context_id: int, context: str, level: str, intent: str = "", client=None):
    """The AI student's reply in the microlesson dialogue: ``context`` holds the microlesson, the dialogue so far and
    the teacher's new message. Returns the AIMessage whose ``structured`` = {reply, answer_type}."""
    level = student_sim.LEVELS.get(level, "medium")
    system = (
        f"{student_sim.DIALOG_SYSTEM}\n\n<context>\nInterface language: {language()}.\nReadiness level: {level}.\n"
        f"{context}\n</context>"
    )
    message = ask_structured(
        user, mode=Mode.STUDENT_SIM, prompt_version=student_sim.DIALOG_VERSION, system=system,
        request="Reply to the teacher's last message as the student.", schema=student_sim.DIALOG_SCHEMA,
        context_type=context_type, context_id=context_id, intent=intent, client=client,
    )  # fmt: skip
    data = message.structured
    if not isinstance(data.get("reply"), str) or data.get("answer_type") not in (*ANSWER_TYPES, "none"):
        raise AIUnavailable("bad structured answer")
    message.content = data["reply"].strip()
    message.save(update_fields=["content"])
    return message
