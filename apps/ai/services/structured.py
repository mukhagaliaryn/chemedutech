"""One structured request (JSON of a schema) in a non-chat mode — the AI student, the checker: the daily limit, the
conversation per object, every request and answer logged (a failed call too)."""

from __future__ import annotations

import json

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from django.utils.translation import get_language

from ..models import AIConversation, AIMessage, AIUsage
from ..prompts import assistant
from .chat import AIUnavailable, LimitReached, conversation_for, enabled, remaining_today
from .client import CallFailed, call


def language() -> str:
    return assistant.LANGUAGES.get((get_language() or "kk")[:2], "Kazakh")


def ask_structured(
    user,
    *,
    mode: str,
    prompt_version: str,
    system: str,
    request: str,
    schema: dict,
    context_type: str,
    context_id: int,
    intent: str = "",
    max_tokens: int = 4000,
    client=None,
) -> AIMessage:
    """Send ``request`` with ``system``; the answer must be JSON of ``schema`` with every required field. Returns the
    AIMessage whose ``structured`` holds it. Raises LimitReached / AIUnavailable (the failed turn is logged).
    ``max_tokens`` — room for the answer: Kazakh text takes many tokens, a cut JSON fails."""
    if not enabled():
        raise AIUnavailable("disabled")
    if remaining_today(user) <= 0:
        raise LimitReached("limit")
    conversation = conversation_for(user, mode, context_type, context_id)
    if conversation is None:
        conversation = AIConversation.objects.create(
            user=user, mode=mode, context_type=context_type, context_id=context_id, prompt_version=prompt_version,
            model=settings.AI_TUTOR_MODEL,
        )  # fmt: skip
    AIMessage.objects.create(conversation=conversation, role=AIMessage.Role.USER, intent=intent, content=request)
    usage, _created = AIUsage.objects.get_or_create(user=user, date=timezone.localdate())
    AIUsage.objects.filter(pk=usage.pk).update(requests=F("requests") + 1)
    try:
        reply = call(
            system, [{"role": "user", "content": request}], schema=schema, max_tokens=max_tokens, client=client
        )
        data = json.loads(reply.text)
        if not isinstance(data, dict) or any(k not in data for k in schema.get("required", ())):
            raise CallFailed("bad structured answer")
    except (CallFailed, ValueError) as exc:
        AIMessage.objects.create(
            conversation=conversation, role=AIMessage.Role.ASSISTANT, intent=intent, error=str(exc)
        )
        raise AIUnavailable(str(exc)) from exc
    AIUsage.objects.filter(pk=usage.pk).update(
        input_tokens=F("input_tokens") + reply.input_tokens, output_tokens=F("output_tokens") + reply.output_tokens
    )
    return AIMessage.objects.create(
        conversation=conversation, role=AIMessage.Role.ASSISTANT, intent=intent, content=reply.text,
        structured=data, input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
        latency_ms=reply.latency_ms,
    )  # fmt: skip
