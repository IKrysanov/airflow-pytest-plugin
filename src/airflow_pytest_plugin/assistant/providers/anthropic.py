# Copyright 2026 the airflow-pytest-plugin contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Anthropic final-answer adapter."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from ..common import (
    AssistantProviderResponse,
    AssistantTokenUsage,
    response_text,
    usage_count,
)
from ..settings import DEFAULT_MODELS, AssistantSettings


class AnthropicAssistant:
    """Final answers through the Anthropic Messages API."""

    def __init__(self, settings: AssistantSettings) -> None:
        import anthropic

        self._model = settings.model or DEFAULT_MODELS["anthropic"]
        self._client: Any = anthropic.Anthropic(max_retries=0, timeout=settings.timeout)

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def answer(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> AssistantProviderResponse:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "\n".join(
            str(block.text)
            for block in message.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        )
        token_usage = self._usage(getattr(message, "usage", None))
        return AssistantProviderResponse(
            text=text,
            token_usage=token_usage,
            stop_reason=response_text(message, "stop_reason"),
        )

    def stream(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Iterator[str | AssistantProviderResponse]:
        """Yield text as the Messages API produces it, then the final usage."""
        with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            yield from stream.text_stream
            message = stream.get_final_message()
        yield AssistantProviderResponse(
            text="",
            token_usage=self._usage(getattr(message, "usage", None)),
            stop_reason=response_text(message, "stop_reason"),
        )

    @staticmethod
    def _usage(usage: Any) -> AssistantTokenUsage | None:
        uncached = usage_count(usage, "input_tokens")
        output = usage_count(usage, "output_tokens")
        if uncached is None or output is None:
            return None
        cached = (usage_count(usage, "cache_creation_input_tokens") or 0) + (
            usage_count(usage, "cache_read_input_tokens") or 0
        )
        input_tokens = uncached + cached
        return AssistantTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output,
            total_tokens=input_tokens + output,
            cached_input_tokens=cached,
        )

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()


__all__ = ["AnthropicAssistant"]
