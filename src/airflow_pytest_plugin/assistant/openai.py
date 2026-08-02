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

"""OpenAI and OpenAI-compatible final-answer adapter."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from .common import (
    AssistantProviderResponse,
    AssistantTokenUsage,
    response_text,
    usage_count,
)
from .settings import DEFAULT_MODELS, AssistantSettings


class OpenAIAssistant:
    """Final answers through OpenAI Chat Completions."""

    def __init__(self, settings: AssistantSettings) -> None:
        import openai

        self._model = settings.model or DEFAULT_MODELS["openai"]
        self._client: Any = openai.OpenAI(max_retries=0, timeout=settings.timeout)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def answer(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> AssistantProviderResponse:
        completion = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        choices = getattr(completion, "choices", None) or []
        choice = choices[0] if choices else None
        message = getattr(choice, "message", None) if choice is not None else None
        return AssistantProviderResponse(
            text=str(getattr(message, "content", "") or ""),
            token_usage=self._usage(getattr(completion, "usage", None)),
            stop_reason=response_text(choice, "finish_reason"),
        )

    def stream(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Iterator[str | AssistantProviderResponse]:
        """Yield each content delta, then the final usage chunk when the SDK sends one."""
        chunks = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            stream_options={"include_usage": True},
        )
        usage: Any = None
        stop_reason: str | None = None
        for chunk in chunks:
            usage = getattr(chunk, "usage", None) or usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            stop_reason = response_text(choice, "finish_reason") or stop_reason
            delta = getattr(choice, "delta", None)
            text = getattr(delta, "content", None) if delta is not None else None
            if text:
                yield str(text)
        yield AssistantProviderResponse(
            text="", token_usage=self._usage(usage), stop_reason=stop_reason
        )

    @staticmethod
    def _usage(usage: Any) -> AssistantTokenUsage | None:
        input_tokens = usage_count(usage, "prompt_tokens")
        output_tokens = usage_count(usage, "completion_tokens")
        if input_tokens is None or output_tokens is None:
            return None
        total_tokens = usage_count(usage, "total_tokens")
        details = (
            usage.get("prompt_tokens_details")
            if isinstance(usage, dict)
            else getattr(usage, "prompt_tokens_details", None)
        )
        return AssistantTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(
                total_tokens
                if total_tokens is not None
                else input_tokens + output_tokens
            ),
            cached_input_tokens=usage_count(details, "cached_tokens") or 0,
        )

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()


__all__ = ["OpenAIAssistant"]
