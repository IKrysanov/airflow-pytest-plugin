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

"""Environment-backed settings for API-server report assistants."""

from __future__ import annotations

import os
from dataclasses import dataclass

PROVIDER_ENV = "AIRFLOW_PYTEST_ASSISTANT_PROVIDER"
MODEL_ENV = "AIRFLOW_PYTEST_ASSISTANT_MODEL"
CONTEXT_MODEL_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL"
CONTEXT_BYTES_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_BYTES"
CONTEXT_N_CTX_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_N_CTX"
CONTEXT_MAX_TOKENS_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MAX_TOKENS"
MAX_OUTPUT_TOKENS_ENV = "AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS"
TIMEOUT_ENV = "AIRFLOW_PYTEST_ASSISTANT_TIMEOUT"
MAX_CONCURRENT_ENV = "AIRFLOW_PYTEST_ASSISTANT_MAX_CONCURRENT"
DIRECT_MAX_SUMMARIES_ENV = "AIRFLOW_PYTEST_ASSISTANT_DIRECT_MAX_SUMMARIES"
TRACEBACK_BYTES_ENV = "AIRFLOW_PYTEST_ASSISTANT_TRACEBACK_BYTES"
CAPTURE_BYTES_ENV = "AIRFLOW_PYTEST_ASSISTANT_CAPTURE_BYTES"

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o-mini",
    "gigachat": "GigaChat",
    "fake": "offline-fake",
}

_PROVIDER_MODEL_ENVS = {
    "anthropic": "ANTHROPIC_MODEL",
    "openai": "OPENAI_MODEL",
    "gigachat": "GIGACHAT_MODEL",
}


def _text_env(name: str) -> str | None:
    raw = os.environ.get(name)
    return raw.strip() if raw and raw.strip() else None


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _text_env(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def _bounded_float(
    name: str, default: float, *, minimum: float, maximum: float
) -> float:
    raw = _text_env(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


@dataclass(frozen=True)
class AssistantSettings:
    """Reader-side assistant settings resolved once at app startup."""

    provider: str | None
    model: str | None
    context_model_path: str | None
    max_context_bytes: int
    context_n_ctx: int
    context_max_tokens: int
    max_output_tokens: int
    timeout: float
    max_concurrent: int
    direct_max_summaries: int
    traceback_bytes: int
    capture_bytes: int

    @classmethod
    def from_env(cls) -> AssistantSettings:
        """Resolve explicit assistant settings and provider-native model names."""
        provider = _text_env(PROVIDER_ENV)
        provider = provider.lower() if provider else None
        model = _text_env(MODEL_ENV)
        if provider and not model:
            native_env = _PROVIDER_MODEL_ENVS.get(provider)
            model = _text_env(native_env) if native_env else None
            model = model or DEFAULT_MODELS.get(provider)
        raw_path = _text_env(CONTEXT_MODEL_ENV)
        path = os.path.abspath(os.path.expanduser(raw_path)) if raw_path else None
        return cls(
            provider=provider,
            model=model,
            context_model_path=path,
            max_context_bytes=_bounded_int(
                CONTEXT_BYTES_ENV, 48 * 1024, minimum=4_096, maximum=256 * 1024
            ),
            context_n_ctx=_bounded_int(
                CONTEXT_N_CTX_ENV, 16_384, minimum=2_048, maximum=131_072
            ),
            context_max_tokens=_bounded_int(
                CONTEXT_MAX_TOKENS_ENV, 1_024, minimum=128, maximum=8_192
            ),
            max_output_tokens=_bounded_int(
                MAX_OUTPUT_TOKENS_ENV, 1_536, minimum=128, maximum=8_192
            ),
            timeout=_bounded_float(TIMEOUT_ENV, 45.0, minimum=1.0, maximum=300.0),
            max_concurrent=_bounded_int(MAX_CONCURRENT_ENV, 1, minimum=1, maximum=8),
            direct_max_summaries=_bounded_int(
                DIRECT_MAX_SUMMARIES_ENV, 100, minimum=1, maximum=1_000
            ),
            traceback_bytes=_bounded_int(
                TRACEBACK_BYTES_ENV,
                3 * 1024,
                minimum=0,
                maximum=64 * 1024,
            ),
            capture_bytes=_bounded_int(
                CAPTURE_BYTES_ENV,
                2 * 1024,
                minimum=0,
                maximum=64 * 1024,
            ),
        )


__all__ = [
    "CONTEXT_BYTES_ENV",
    "CONTEXT_MAX_TOKENS_ENV",
    "CONTEXT_MODEL_ENV",
    "CONTEXT_N_CTX_ENV",
    "CAPTURE_BYTES_ENV",
    "DIRECT_MAX_SUMMARIES_ENV",
    "MAX_CONCURRENT_ENV",
    "MAX_OUTPUT_TOKENS_ENV",
    "MODEL_ENV",
    "PROVIDER_ENV",
    "TIMEOUT_ENV",
    "TRACEBACK_BYTES_ENV",
    "AssistantSettings",
    "DEFAULT_MODELS",
]
