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

"""GigaChat final-answer adapter."""

from __future__ import annotations

import contextlib
from typing import Any

from .common import (
    AssistantProviderResponse,
    AssistantTokenUsage,
    response_text,
    usage_count,
)
from .settings import DEFAULT_MODELS, AssistantSettings


class GigaChatAssistant:
    """Final answers through GigaChat's native SDK environment."""

    def __init__(self, settings: AssistantSettings) -> None:
        import gigachat

        self._model = settings.model or DEFAULT_MODELS["gigachat"]
        self._client: Any = gigachat.GigaChat(max_retries=0, timeout=settings.timeout)

    @property
    def name(self) -> str:
        return "gigachat"

    @property
    def model(self) -> str:
        return self._model

    def answer(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> AssistantProviderResponse:
        completion = self._client.chat(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            }
        )
        choices = getattr(completion, "choices", None) or []
        choice = choices[0] if choices else None
        message = getattr(choice, "message", None) if choice is not None else None
        usage = getattr(completion, "usage", None)
        prompt_tokens = usage_count(usage, "prompt_tokens")
        output_tokens = usage_count(usage, "completion_tokens")
        cached = usage_count(usage, "precached_prompt_tokens") or 0
        total_tokens = usage_count(usage, "total_tokens")
        token_usage = None
        if prompt_tokens is not None and output_tokens is not None:
            token_usage = AssistantTokenUsage(
                # GigaChat documents prompt_tokens and total_tokens as billable
                # counts after cached tokens have been deducted.
                input_tokens=prompt_tokens,
                output_tokens=output_tokens,
                total_tokens=(
                    total_tokens
                    if total_tokens is not None
                    else prompt_tokens + output_tokens
                ),
                cached_input_tokens=cached,
            )
        if isinstance(message, dict):
            text = str(message.get("content") or "")
        else:
            text = str(getattr(message, "content", "") or "")
        return AssistantProviderResponse(
            text=text,
            token_usage=token_usage,
            stop_reason=response_text(choice, "finish_reason"),
        )

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()


__all__ = ["GigaChatAssistant"]
