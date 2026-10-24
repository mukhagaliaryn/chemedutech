"""The AI student (mode ``student_sim``, guide @S4-ASSEMBLE): one structured answer per lesson stage of a trial —
the student's answer, its type, the possible error, the difficulty and the AI assistant's methodical suggestion.
Every request is logged (AIConversation per trial, AIMessage per stage) and counts towards the daily limit."""

from __future__ import annotations

import json

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from django.utils.translation import get_language

from ..models import AIConversation, AIMessage, AIUsage, Mode
from ..prompts import assistant, student_sim
from .chat import AIUnavailable, LimitReached, conversation_for, enabled, remaining_today
from .client import CallFailed, call

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
    holds the five fields; ``answer_type`` (correct / partial / wrong) makes the AI give that kind of answer. Raises LimitReached / AIUnavailable like ``ask`` (a failed call is logged)."""
    if not enabled():
        raise AIUnavailable("disabled")
    if remaining_today(user) <= 0:
        raise LimitReached("limit")
    level = student_sim.LEVELS.get(level, "medium")
    conversation = conversation_for(user, Mode.STUDENT_SIM, context_type, context_id)
    if conversation is None:
        conversation = AIConversation.objects.create(
            user=user, mode=Mode.STUDENT_SIM, context_type=context_type, context_id=context_id,
            prompt_version=student_sim.PROMPT_VERSION, model=settings.AI_TUTOR_MODEL,
        )  # fmt: skip
    request = f"Do the task of this lesson stage as a {level}-level student, then analyse it."
    AIMessage.objects.create(conversation=conversation, role=AIMessage.Role.USER, intent=intent, content=request)
    language = assistant.LANGUAGES.get((get_language() or "kk")[:2], "Kazakh")
    system = (
        f"{student_sim.SYSTEM}\n\n<context>\nInterface language: {language}.\nReadiness level: {level}.\n"
        + (f"Required answer type: {answer_type}.\n" if answer_type in ANSWER_TYPES else "")
        + f"{context}\n</context>"
    )
    usage, _created = AIUsage.objects.get_or_create(user=user, date=timezone.localdate())
    AIUsage.objects.filter(pk=usage.pk).update(requests=F("requests") + 1)
    try:
        reply = call(system, [{"role": "user", "content": request}], schema=student_sim.SCHEMA, client=client)
        data = json.loads(reply.text)
        if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in FIELDS):
            raise CallFailed("bad structured answer")
    except (CallFailed, ValueError) as exc:
        AIMessage.objects.create(
            conversation=conversation, role=AIMessage.Role.ASSISTANT, intent=intent, error=str(exc)
        )
        raise AIUnavailable(str(exc)) from exc
    AIUsage.objects.filter(pk=usage.pk).update(
        input_tokens=F("input_tokens") + reply.input_tokens, output_tokens=F("output_tokens") + reply.output_tokens
    )
    data = {k: data[k].strip() for k in FIELDS}
    return AIMessage.objects.create(
        conversation=conversation, role=AIMessage.Role.ASSISTANT, intent=intent, content=data["answer"],
        structured=data, input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
        latency_ms=reply.latency_ms,
    )  # fmt: skip
