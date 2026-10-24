"""The Anthropic client of the AI layer — the only place that calls the API for the ICPAI features (tests replace
``get_client`` with a fake; there is no network in tests)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import anthropic
from django.conf import settings

# Models that accept the server-side refusal fallback on the Claude API ("default" routing).
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


class CallFailed(Exception):
    """The API could not give a usable answer (network, rate limit, refusal, server error)."""


@dataclass
class Reply:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY or None,
        timeout=float(settings.AI_TUTOR_TIMEOUT_S),
        max_retries=1,
    )


def call(system: str, messages: list[dict], *, max_tokens: int = 2000, client=None) -> Reply:
    client = client or get_client()
    model = settings.AI_TUTOR_MODEL
    params = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "output_config": {"effort": settings.AI_TUTOR_EFFORT},
    }
    started = time.monotonic()
    try:
        if settings.AI_TUTOR_FALLBACKS and model in FALLBACK_MODELS:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
            )
        else:
            response = client.messages.create(**params)
    except (anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
        raise CallFailed(f"{type(exc).__name__}: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise CallFailed(f"{type(exc).__name__} {exc.status_code}: {exc.message}") from exc
    if response.stop_reason == "refusal":
        raise CallFailed("refusal")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise CallFailed(f"empty answer (stop_reason={response.stop_reason})")
    return Reply(
        text=text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
