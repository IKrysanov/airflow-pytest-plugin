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

"""Shared assistant limits, protocols, value objects, and byte clipping."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

MAX_QUESTION_CHARS = 4_000
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 4_000
MAX_HISTORY_BYTES = 16_000
# The browser replays prior turns verbatim, and an answer is capped at MAX_ANSWER_BYTES,
# not at the per-turn prompt clip. Rejecting that replay would break the chat for good
# after one long answer, so the wire contract is deliberately wider than the clip; the
# 64 KiB body limit remains the real anti-abuse guard.
MAX_HISTORY_INPUT_CHARS = 64_000
MAX_SCOPE_REPORTS = 100
MAX_SCOPE_CHARS = 512

MAX_SUMMARIES = 100
MAX_FAILURE_BYTES = 3 * 1024
MAX_CAPTURE_BYTES = 2 * 1024
MAX_ANSWER_BYTES = 64 * 1024


@dataclass(frozen=True)
class AssistantTokenUsage:
    """Provider-reported token counts for the final answer call."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        """Return stable names shared by every provider and the browser."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_input_tokens": self.cached_input_tokens,
        }


@dataclass(frozen=True)
class AssistantProviderResponse:
    """Final provider text plus optional exact token accounting."""

    text: str
    token_usage: AssistantTokenUsage | None = None
    stop_reason: str | None = None


def usage_count(usage: Any, key: str) -> int | None:
    """Read one non-negative integer from an SDK object or mapping."""
    if usage is None:
        return None
    value = usage.get(key) if isinstance(usage, Mapping) else getattr(usage, key, None)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def response_text(value: Any, key: str) -> str | None:
    """Read one short, non-empty SDK response string from an object or mapping."""
    raw = value.get(key) if isinstance(value, Mapping) else getattr(value, key, None)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()[:64]


class AnswerProvider(Protocol):
    """A remote (or test) model that writes the final grounded answer."""

    @property
    def name(self) -> str:
        """Provider name shown in status and responses."""

    @property
    def model(self) -> str:
        """Model name shown in status and responses."""

    def answer(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> str | AssistantProviderResponse:
        """Return one answer for the supplied prompt."""

    def close(self) -> None:
        """Release provider resources."""


class StreamingAnswerProvider(AnswerProvider, Protocol):
    """A provider that can also emit its answer incrementally.

    Optional: the runtime falls back to :meth:`AnswerProvider.answer` when a provider does
    not implement ``stream``, so a non-streaming adapter still works -- the browser simply
    receives the whole answer as one delta.
    """

    def stream(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Iterator[str | AssistantProviderResponse]:
        """Yield answer fragments, then one final response carrying usage and stop reason."""


class ContextReducer(Protocol):
    """Optional local model that compacts evidence before it leaves the server."""

    @property
    def name(self) -> str | None:
        """Local model label, or ``None`` for deterministic passthrough."""

    def reduce(self, *, question: str, context: str) -> str:
        """Return a compact, evidence-preserving context."""

    def close(self) -> None:
        """Release local-model resources."""


@dataclass(frozen=True)
class AssistantTurn:
    """One bounded prior chat turn supplied by the browser."""

    role: str
    content: str


@dataclass(frozen=True)
class AssistantScope:
    """The dashboard scope captured when the question was sent."""

    dag_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    report_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssistantQuery:
    """One question and its non-persistent browser context."""

    question: str
    scope: AssistantScope = AssistantScope()
    history: tuple[AssistantTurn, ...] = ()


@dataclass(frozen=True)
class AssistantEvidence:
    """One report reference the model may cite as ``[R<n>]``."""

    key: str
    report_id: str
    dag_id: str
    run_id: str
    task_id: str
    created_at: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the browser-safe evidence-link payload."""
        return {
            "key": self.key,
            "report_id": self.report_id,
            "dag_id": self.dag_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class AssistantContext:
    """Report facts plus the references used to label them.

    ``text`` is the deterministic bounded snapshot used in direct mode. ``chunks`` is the
    complete report tree used when an in-process reducer is configured. It is a one-shot
    stream, so the API server never assembles one unbounded raw prompt in memory.
    """

    text: str
    evidence: tuple[AssistantEvidence, ...]
    reports_considered: int
    truncated: bool
    context_limited: bool
    scope_label: str
    chunks: Iterable[str] = ()


@dataclass(frozen=True)
class AssistantPromptBytes:
    """UTF-8 byte sizes of the exact provider input, split into auditable parts."""

    system: int = 0
    user: int = 0
    context: int = 0
    history: int = 0
    structure: int = 0

    @property
    def total(self) -> int:
        """Return the sum handed to the provider as system and user-role strings."""
        return self.system + self.user + self.context + self.history + self.structure

    def to_dict(self) -> dict[str, int]:
        """Return browser-safe component sizes plus their total."""
        return {
            "system": self.system,
            "user": self.user,
            "context": self.context,
            "history": self.history,
            "structure": self.structure,
            "total": self.total,
        }


@dataclass(frozen=True)
class AssistantReportContext:
    """Exact report-evidence block sent to the final provider."""

    content: str
    format: Literal["direct-snapshot-jsonl", "locally-reduced-text"]

    def to_dict(self) -> dict[str, str | int]:
        """Return the auditable browser payload without system prompt or history."""
        return {
            "content": self.content,
            "format": self.format,
            "bytes": len(self.content.encode("utf-8")),
        }


@dataclass(frozen=True)
class AssistantReply:
    """A grounded answer returned by the HTTP layer."""

    answer: str
    evidence: tuple[AssistantEvidence, ...]
    provider: str
    model: str
    context_model: str | None
    reports_considered: int
    truncated: bool
    context_limited: bool
    scope: str
    prompt_bytes: AssistantPromptBytes
    token_usage: AssistantTokenUsage | None
    report_context: AssistantReportContext | None
    output_limited: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON response body."""
        return {
            "answer": self.answer,
            "evidence": [item.to_dict() for item in self.evidence],
            "provider": self.provider,
            "model": self.model,
            "context_model": self.context_model,
            "reports_considered": self.reports_considered,
            "truncated": self.truncated,
            "context_limited": self.context_limited,
            "scope": self.scope,
            "provider_input_bytes": self.prompt_bytes.total,
            "prompt_bytes": self.prompt_bytes.to_dict(),
            "token_usage": (
                self.token_usage.to_dict() if self.token_usage is not None else None
            ),
            "report_context": (
                self.report_context.to_dict()
                if self.report_context is not None
                else None
            ),
            "output_limited": self.output_limited,
        }


def clip_utf8(text: str, limit: int) -> str:
    """Clip text to at most ``limit`` encoded bytes and mark the truncation."""
    raw = text.encode("utf-8", "replace")
    if len(raw) <= limit:
        return text
    marker = b"\n...[truncated]..."
    if limit <= len(marker):
        return raw[:limit].decode("utf-8", "ignore")
    kept = raw[: limit - len(marker)].decode("utf-8", "ignore")
    return kept + marker.decode()


__all__ = [
    "MAX_CAPTURE_BYTES",
    "MAX_HISTORY_BYTES",
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_INPUT_CHARS",
    "MAX_HISTORY_MESSAGES",
    "MAX_QUESTION_CHARS",
    "MAX_SCOPE_CHARS",
    "MAX_SCOPE_REPORTS",
    "AnswerProvider",
    "AssistantContext",
    "AssistantEvidence",
    "AssistantProviderResponse",
    "AssistantPromptBytes",
    "AssistantQuery",
    "AssistantReportContext",
    "AssistantReply",
    "AssistantScope",
    "AssistantTurn",
    "AssistantTokenUsage",
    "ContextReducer",
    "StreamingAnswerProvider",
    "response_text",
    "usage_count",
]
