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

"""Validate assistant configuration and assemble lazy runtime factories."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .anthropic import AnthropicAssistant
from .common import AnswerProvider, ContextReducer
from .fake import FakeAssistant
from .gigachat import GigaChatAssistant
from .llama import LlamaCppReducer, safe_local_input_bytes
from .openai import OpenAIAssistant
from .passthrough import PassthroughReducer
from .runtime import AssistantRuntime
from .settings import CONTEXT_MODEL_ENV, PROVIDER_ENV, AssistantSettings

_PROVIDER_MODULES = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gigachat": "gigachat",
}


def configured_assistant_runtime() -> AssistantRuntime:
    """Build a lazy runtime from environment variables without importing SDKs."""
    settings = AssistantSettings.from_env()
    problem = _configuration_problem(settings)
    context_name = (
        Path(settings.context_model_path).name if settings.context_model_path else None
    )
    if problem:
        return AssistantRuntime.disabled(
            problem,
            provider_name=settings.provider,
            model_name=settings.model,
            context_model_name=context_name,
        )
    return AssistantRuntime(
        provider_factory=lambda: _provider_factory(settings),
        reducer_factory=lambda: _reducer_factory(settings),
        provider_name=settings.provider,
        model_name=settings.model,
        context_model_name=context_name,
        max_context_bytes=settings.max_context_bytes,
        max_output_tokens=settings.max_output_tokens,
        max_concurrent=settings.max_concurrent,
        local_input_bytes=(
            min(settings.max_context_bytes, safe_local_input_bytes(settings))
            if settings.context_model_path
            else None
        ),
        direct_max_summaries=settings.direct_max_summaries,
        max_failure_bytes=settings.traceback_bytes,
        max_capture_bytes=settings.capture_bytes,
    )


def _configuration_problem(settings: AssistantSettings) -> str | None:
    if settings.provider is None:
        return f"Set {PROVIDER_ENV} to enable the report assistant."
    if settings.provider not in {*_PROVIDER_MODULES, "fake"}:
        return (
            f"Unsupported assistant provider {settings.provider!r}; "
            "choose anthropic, openai, gigachat, or fake."
        )
    module = _PROVIDER_MODULES.get(settings.provider)
    if module and importlib.util.find_spec(module) is None:
        return (
            f"Provider {settings.provider!r} is selected but its SDK is not installed; "
            f"install the 'assistant-{settings.provider}' extra."
        )
    if settings.context_model_path:
        if not Path(settings.context_model_path).is_file():
            return f"Local context model set by {CONTEXT_MODEL_ENV} was not found."
        if importlib.util.find_spec("llama_cpp") is None:
            return (
                "A local context model is configured but llama-cpp-python is missing; "
                "install the 'assistant-local' extra."
            )
        if safe_local_input_bytes(settings) < 4_096:
            return (
                "The local context window is too small for the configured question and "
                "output limits; increase AIRFLOW_PYTEST_ASSISTANT_CONTEXT_N_CTX or "
                "decrease AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MAX_TOKENS."
            )
    return None


def _provider_factory(settings: AssistantSettings) -> AnswerProvider:
    if settings.provider == "fake":
        return FakeAssistant()
    if settings.provider == "anthropic":
        return AnthropicAssistant(settings)
    if settings.provider == "openai":
        return OpenAIAssistant(settings)
    if settings.provider == "gigachat":
        return GigaChatAssistant(settings)
    raise RuntimeError(f"unsupported assistant provider: {settings.provider}")


def _reducer_factory(settings: AssistantSettings) -> ContextReducer:
    if settings.context_model_path:
        return LlamaCppReducer(settings)
    return PassthroughReducer()


__all__ = ["configured_assistant_runtime"]
