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
import logging
from pathlib import Path
from typing import Any

from .common import AnswerProvider, ContextReducer
from .docs import load_documentation
from .providers.anthropic import AnthropicAssistant
from .providers.fake import FakeAssistant
from .providers.gigachat import GigaChatAssistant
from .providers.openai import OpenAIAssistant
from .redaction import redact_text
from .reducers import LlamaCppReducer, PassthroughReducer, safe_local_input_bytes
from .runtime import AssistantRuntime
from .settings import CONTEXT_MODEL_ENV, PROVIDER_ENV, AssistantSettings

_log = logging.getLogger(__name__)

_PROVIDER_MODULES = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gigachat": "gigachat",
}


def configured_assistant_runtime() -> AssistantRuntime:
    """Build a lazy runtime from environment variables without importing SDKs."""
    settings = AssistantSettings.from_env()
    # The reason reaches every viewer's chat window, and it quotes operator-supplied
    # values. A mistyped variable must not publish a key to the whole dashboard.
    problem = redact_text(_configuration_problem(settings) or "") or None
    context_name = (
        Path(settings.context_model_path).name if settings.context_model_path else None
    )
    if problem:
        # An operator who set the provider variable meant to have this feature. Staying
        # silent about a broken setup leaves them with a viewer that simply has no
        # assistant in it and nothing anywhere saying why.
        if settings.provider is not None:
            _log.warning("The report assistant is not available: %s", problem)
        return AssistantRuntime.disabled(
            problem,
            provider_name=settings.provider,
            model_name=settings.model,
            context_model_name=context_name,
            configured=settings.provider is not None,
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
        local_budget_seconds=settings.local_budget_seconds,
        rate_limit=settings.rate_limit,
        rate_window_seconds=settings.rate_window_seconds,
        daily_token_quota=settings.daily_token_quota,
        quota_store=_quota_store(settings),
        rate_store=_rate_store(settings),
        history=_history_store(settings),
        history_days=settings.history_days,
        direct_max_summaries=settings.direct_max_summaries,
        max_failure_bytes=settings.traceback_bytes,
        max_capture_bytes=settings.capture_bytes,
        documentation=load_documentation(settings.docs_paths),
        docs_bytes=settings.docs_bytes,
    )


def _quota_store(settings: AssistantSettings) -> Any:
    """Return the shared quota store, or ``None`` when no budget is configured.

    Nothing is imported or connected unless a quota is actually set, so a deployment that
    never wanted one pays no database cost for the feature.
    """
    if not settings.daily_token_quota:
        return None
    from .. import db

    return db.quota_store()


def _rate_store(settings: AssistantSettings) -> Any:
    """Return the shared request-rate store, or ``None`` when no limit is configured."""
    if not settings.rate_limit:
        return None
    from .. import db

    return db.rate_store()


def _history_store(settings: AssistantSettings) -> Any:
    """Return the chat-history store, or ``None`` when history is switched off."""
    if not settings.history_days:
        return None
    from .. import db

    return db.history_store()


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
