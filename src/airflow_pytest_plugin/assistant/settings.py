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

import logging
import math
import os
import re
from dataclasses import dataclass
from typing import TypeVar

PROVIDER_ENV = "AIRFLOW_PYTEST_ASSISTANT_PROVIDER"
MODEL_ENV = "AIRFLOW_PYTEST_ASSISTANT_MODEL"
CONTEXT_MODEL_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL"
CONTEXT_BYTES_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_BYTES"
CONTEXT_N_CTX_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_N_CTX"
CONTEXT_MAX_TOKENS_ENV = "AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MAX_TOKENS"
LOCAL_BUDGET_SECONDS_ENV = "AIRFLOW_PYTEST_ASSISTANT_LOCAL_BUDGET_SECONDS"
MAX_OUTPUT_TOKENS_ENV = "AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS"
TIMEOUT_ENV = "AIRFLOW_PYTEST_ASSISTANT_TIMEOUT"
MAX_CONCURRENT_ENV = "AIRFLOW_PYTEST_ASSISTANT_MAX_CONCURRENT"
DIRECT_MAX_SUMMARIES_ENV = "AIRFLOW_PYTEST_ASSISTANT_DIRECT_MAX_SUMMARIES"
TRACEBACK_BYTES_ENV = "AIRFLOW_PYTEST_ASSISTANT_TRACEBACK_BYTES"
CAPTURE_BYTES_ENV = "AIRFLOW_PYTEST_ASSISTANT_CAPTURE_BYTES"
HEALTHCHECK_ENV = "AIRFLOW_PYTEST_ASSISTANT_HEALTHCHECK"
RATE_LIMIT_ENV = "AIRFLOW_PYTEST_ASSISTANT_RATE_LIMIT"
RATE_WINDOW_ENV = "AIRFLOW_PYTEST_ASSISTANT_RATE_WINDOW"
DAILY_TOKEN_QUOTA_ENV = "AIRFLOW_PYTEST_ASSISTANT_DAILY_TOKEN_QUOTA"
HISTORY_DAYS_ENV = "AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS"

_log = logging.getLogger(__name__)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def healthcheck_enabled() -> bool:
    """Whether the operator opted into the paid provider readiness endpoint.

    Read per request rather than frozen at startup: turning a diagnostic on should not
    require restarting every API-server process.
    """
    raw = _text_env(HEALTHCHECK_ENV)
    return raw is not None and raw.lower() in _TRUE_VALUES


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

#: Simultaneous assistant calls per API-server process when no local reducer is configured.
#: Enough for a small team to use the panel at once; each costs a fraction of a mebibyte,
#: and what the request actually waits on is the remote provider.
DEFAULT_DIRECT_CONCURRENCY = 4

#: Paths to Markdown the assistant may quote when asked about the product. Setting this
#: **replaces** the manual shipped with the package rather than adding to it: an operator
#: who has written their own documentation for this product means that one, and two
#: overlapping manuals in the same retrieval pool answer the same question twice.
DOCS_ENV = "AIRFLOW_PYTEST_ASSISTANT_DOCS"
DOCS_BYTES_ENV = "AIRFLOW_PYTEST_ASSISTANT_DOCS_BYTES"

#: Set to a false value to ship no documentation at all -- no built-in manual, and the
#: assistant answers product questions only from the short PRODUCT block in its prompt.
DOCS_BUILTIN_ENV = "AIRFLOW_PYTEST_ASSISTANT_DOCS_BUILTIN"


def _paths_env(name: str) -> tuple[str, ...]:
    """Split a path list on the separators an operator is likely to reach for."""
    raw = _text_env(name)
    if not raw:
        return ()
    parts = [part.strip() for part in re.split(r"[,:;\n]", raw)]
    return tuple(part for part in parts if part)


def _documentation_paths() -> tuple[str, ...]:
    """Return what the assistant may quote: the operator's manual, or the shipped one.

    The built-in manual is the default so that ``/docs`` answers "how do I run my first
    test?" on a fresh install -- before this, the mechanism was there and every deployment
    started with an empty corpus, which reads to a user as the feature not working.
    """
    from .docs import builtin_paths

    configured = _paths_env(DOCS_ENV)
    if configured:
        return configured
    raw = _text_env(DOCS_BUILTIN_ENV)
    if raw is not None and raw.lower() in _FALSE_VALUES:
        return ()
    return builtin_paths()


def _text_env(name: str) -> str | None:
    raw = os.environ.get(name)
    return raw.strip() if raw and raw.strip() else None


_Number = TypeVar("_Number", int, float)


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _text_env(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        _log.warning("%s is not a number (%r); using %s", name, raw, default)
        return default
    return _report(
        name, value, _bound(value, default, minimum, maximum), minimum, maximum
    )


def _report(
    name: str, asked: _Number, used: _Number, minimum: _Number, maximum: _Number
) -> _Number:
    """Say out loud when a setting was not taken at face value.

    These are the knobs an operator reaches for when an answer says its context was
    limited, and the range is not obvious from the outside. Silence made the worst case
    invisible: elsewhere in this plugin ``0`` removes a limit -- ``MAX_REPORT_MIB=0``,
    ``RATE_LIMIT=0`` -- so ``CONTEXT_BYTES=0`` is a reasonable thing to try, and it
    quietly produced the same 48 KiB and the same truncation as before.
    """
    if asked == used:
        return used
    _log.warning(
        "%s=%s is outside its range %s-%s; using %s",
        name,
        asked,
        minimum,
        maximum,
        used,
    )
    return used


def _bound(
    value: _Number, default: _Number, minimum: _Number, maximum: _Number
) -> _Number:
    """Resolve an out-of-range setting the way its author most likely meant.

    Above the ceiling the value is clamped to it: "as much as you allow" is what someone
    writing a number too large means, and the ceiling is by definition still safe. Below
    the floor the value is nonsense and the documented default is used -- clamping up would
    be wrong for the settings whose floor is the *off* position, where ``RATE_LIMIT=-5``
    would disable the limiter and ``DAILY_TOKEN_QUOTA`` would mean unlimited.

    The asymmetry matters because ``DAILY_TOKEN_QUOTA`` defaults to unlimited: falling back
    to the default for a too-large value turned "cap me at two billion tokens" into no cap.
    """
    if value > maximum:
        return maximum
    if value < minimum:
        return default
    return value


def _bounded_float(
    name: str, default: float, *, minimum: float, maximum: float
) -> float:
    raw = _text_env(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        _log.warning("%s is not a number (%r); using %s", name, raw, default)
        return default
    if math.isnan(value) or math.isinf(value):
        _log.warning("%s is not a finite number (%r); using %s", name, raw, default)
        return default
    return _report(
        name, value, _bound(value, default, minimum, maximum), minimum, maximum
    )


@dataclass(frozen=True)
class AssistantSettings:
    """Reader-side assistant settings resolved once at app startup."""

    provider: str | None
    model: str | None
    context_model_path: str | None
    max_context_bytes: int
    context_n_ctx: int
    context_max_tokens: int
    local_budget_seconds: float
    max_output_tokens: int
    rate_limit: int
    rate_window_seconds: float
    daily_token_quota: int
    history_days: int
    timeout: float
    max_concurrent: int
    direct_max_summaries: int
    traceback_bytes: int
    capture_bytes: int
    #: Markdown an operator mounted for the assistant to quote. Empty unless configured.
    docs_paths: tuple[str, ...] = ()
    #: How much of it one question may carry.
    docs_bytes: int = 4_096

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
            local_budget_seconds=_bounded_float(
                LOCAL_BUDGET_SECONDS_ENV, 120.0, minimum=5.0, maximum=3_600.0
            ),
            max_output_tokens=_bounded_int(
                MAX_OUTPUT_TOKENS_ENV, 3_072, minimum=128, maximum=8_192
            ),
            # A generous default that still stops a runaway loop: one question a minute,
            # sustained for an hour, is far beyond human use of a chat window.
            rate_limit=_bounded_int(RATE_LIMIT_ENV, 60, minimum=0, maximum=100_000),
            rate_window_seconds=_bounded_float(
                RATE_WINDOW_ENV, 3_600.0, minimum=1.0, maximum=86_400.0
            ),
            # Only the operator knows their budget, so spend is unlimited until they say.
            daily_token_quota=_bounded_int(
                DAILY_TOKEN_QUOTA_ENV, 0, minimum=0, maximum=1_000_000_000
            ),
            # Server-side chat is opt-out rather than opt-in: the tables only exist if an
            # operator ran the CLI, so reaching this line already means they chose it.
            history_days=_bounded_int(HISTORY_DAYS_ENV, 30, minimum=0, maximum=3_650),
            timeout=_bounded_float(TIMEOUT_ENV, 45.0, minimum=1.0, maximum=300.0),
            # The semaphore exists for the in-process GGUF: llama.cpp serialises on its
            # own lock and each copy costs gigabytes, so that path gets exactly one slot.
            # Direct mode has neither problem -- measured at ~0.15 MiB per additional
            # concurrent request -- and one slot there made the assistant single-user:
            # the second person to ask got 429 until the first was finished.
            docs_paths=_documentation_paths(),
            docs_bytes=_bounded_int(DOCS_BYTES_ENV, 4_096, minimum=0, maximum=32_768),
            max_concurrent=_bounded_int(
                MAX_CONCURRENT_ENV,
                1 if path else DEFAULT_DIRECT_CONCURRENCY,
                minimum=1,
                maximum=8,
            ),
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
    "DAILY_TOKEN_QUOTA_ENV",
    "DIRECT_MAX_SUMMARIES_ENV",
    "DOCS_BUILTIN_ENV",
    "DOCS_ENV",
    "HEALTHCHECK_ENV",
    "HISTORY_DAYS_ENV",
    "LOCAL_BUDGET_SECONDS_ENV",
    "MAX_CONCURRENT_ENV",
    "MAX_OUTPUT_TOKENS_ENV",
    "MODEL_ENV",
    "PROVIDER_ENV",
    "RATE_LIMIT_ENV",
    "RATE_WINDOW_ENV",
    "TIMEOUT_ENV",
    "TRACEBACK_BYTES_ENV",
    "AssistantSettings",
    "DEFAULT_MODELS",
    "healthcheck_enabled",
]
