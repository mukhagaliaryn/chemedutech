"""A scripted stand-in for the Anthropic client of the AI layer (apps.ai.services.client): the demo queues the answer
of each request just before the service call; the services store it as they store a real answer (model «demo»).
Nothing leaves the machine."""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

from django.test import override_settings


class DemoTutor:
    def __init__(self):
        self.queue = []
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def next(self, answer):
        """The answer of the next request: a dict (a structured answer) or a text (an assistant reply)."""
        self.queue.append(answer)

    def _create(self, **params):
        if not self.queue:
            raise AssertionError("demo: an AI request nobody scripted")
        answer = self.queue.pop(0)
        text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=900 + len(str(params.get("system", ""))) // 4, output_tokens=len(text) // 3
            ),
        )

    @contextmanager
    def active(self):
        settings = {"AI_TUTOR_ENABLED": True, "AI_TUTOR_MODEL": "demo", "AI_TUTOR_FALLBACKS": False,
                    "AI_TUTOR_DAILY_REQUESTS": 100000}  # fmt: skip
        with override_settings(**settings), mock.patch("apps.ai.services.client.get_client", return_value=self):
            yield self
        if self.queue:
            raise AssertionError(f"demo: {len(self.queue)} scripted AI answers were not asked for")
