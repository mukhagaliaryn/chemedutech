"""Conversations with the AI assistant: one thread per user × mode × object, a daily request limit, every turn
logged (AIConversation / AIMessage / AIUsage — research data). The caller (product layer) passes the context as text;
this layer knows nothing about sections or lessons."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import get_language

from ..models import AIConversation, AIMessage, AIUsage, Mode
from ..prompts import assistant
from .client import CallFailed, call

HISTORY_TURNS = 8  # earlier turns sent back with a new question


class AIUnavailable(Exception):
    """AI is switched off or failed this time — the page says so and works on without it."""


class LimitReached(AIUnavailable):
    """The student's requests for today are used up."""


def enabled() -> bool:
    return bool(settings.AI_TUTOR_ENABLED)


def remaining_today(user) -> int:
    usage = AIUsage.objects.filter(user=user, date=timezone.localdate()).first()
    return max(0, settings.AI_TUTOR_DAILY_REQUESTS - (usage.requests if usage else 0))


def conversation_for(user, mode, context_type, context_id) -> AIConversation | None:
    return (
        AIConversation.objects.filter(user=user, mode=mode, context_type=context_type, context_id=context_id)
        .order_by("-created_at")
        .first()
    )


def thread(user, mode, context_type, context_id) -> list[AIMessage]:
    conversation = conversation_for(user, mode, context_type, context_id)
    return list(conversation.messages.all()) if conversation else []


def _neutral(text: str) -> str:
    """The student's words cannot close their own block."""
    return text.replace("<", "‹").replace(">", "›")


def quote(text: str) -> str:
    """The student's own text inside the context (a draft, an answer): marked as theirs, never as instructions."""
    return f"<student_text>\n{_neutral(text)}\n</student_text>"


def _history(conversation) -> list[dict]:
    turns = list(conversation.messages.exclude(content="").order_by("-created_at", "-pk")[: HISTORY_TURNS * 2])
    turns.reverse()
    out = []
    for m in turns:
        if m.role == AIMessage.Role.USER:
            out.append({"role": "user", "content": quote(m.content)})
        elif not m.error:
            out.append({"role": "assistant", "content": m.content})
    while out and out[0]["role"] != "user":  # the API wants a user turn first
        out.pop(0)
    return out


def ask(user, *, context_type: str, context_id: int, context: str, text: str = "", intent: str = "", client=None):
    """Send the student's message (or a quick action ``intent``) in the assistant mode; returns the AI's AIMessage.

    Raises LimitReached when today's requests are used up and AIUnavailable when AI is off or the call failed
    (the failed turn is still logged with its error)."""
    if not enabled():
        raise AIUnavailable("disabled")
    if remaining_today(user) <= 0:
        raise LimitReached("limit")
    request = str(assistant.INTENTS.get(intent, "")) if intent else ""
    text = (text or request).strip()[:4000]
    if not text:
        raise AIUnavailable("empty")
    with transaction.atomic():
        conversation = conversation_for(user, Mode.ASSISTANT, context_type, context_id)
        if conversation is None:
            conversation = AIConversation.objects.create(
                user=user, mode=Mode.ASSISTANT, context_type=context_type, context_id=context_id,
                prompt_version=assistant.PROMPT_VERSION, model=settings.AI_TUTOR_MODEL,
            )  # fmt: skip
        AIMessage.objects.create(conversation=conversation, role=AIMessage.Role.USER, intent=intent, content=text)
    language = assistant.LANGUAGES.get((get_language() or "kk")[:2], "Kazakh")
    system = f"{assistant.SYSTEM}\n\n<context>\nInterface language: {language}.\n{context}\n</context>"
    usage, _created = AIUsage.objects.get_or_create(user=user, date=timezone.localdate())
    AIUsage.objects.filter(pk=usage.pk).update(requests=F("requests") + 1)
    try:
        reply = call(system, _history(conversation), client=client)
    except CallFailed as exc:
        AIMessage.objects.create(
            conversation=conversation, role=AIMessage.Role.ASSISTANT, intent=intent, error=str(exc)
        )
        raise AIUnavailable(str(exc)) from exc
    AIUsage.objects.filter(pk=usage.pk).update(
        input_tokens=F("input_tokens") + reply.input_tokens, output_tokens=F("output_tokens") + reply.output_tokens
    )
    return AIMessage.objects.create(
        conversation=conversation, role=AIMessage.Role.ASSISTANT, intent=intent, content=reply.text,
        input_tokens=reply.input_tokens, output_tokens=reply.output_tokens, latency_ms=reply.latency_ms,
    )  # fmt: skip
