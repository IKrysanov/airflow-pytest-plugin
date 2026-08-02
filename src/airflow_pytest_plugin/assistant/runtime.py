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

"""Lazy, concurrency-bounded orchestration for one report-assistant request."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any

from ..sources import ReportSource
from .common import (
    MAX_ANSWER_BYTES,
    MAX_CAPTURE_BYTES,
    MAX_FAILURE_BYTES,
    MAX_HISTORY_BYTES,
    MAX_HISTORY_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_QUESTION_CHARS,
    MAX_SCOPE_REPORTS,
    MAX_SUMMARIES,
    AnswerProvider,
    AssistantContext,
    AssistantPromptBytes,
    AssistantProviderResponse,
    AssistantQuery,
    AssistantReply,
    AssistantReportContext,
    AssistantTokenUsage,
    ContextReducer,
    clip_utf8,
)
from .context import ReportContextBuilder
from .exceptions import (
    AssistantBusyError,
    AssistantDisabledError,
    AssistantError,
    AssistantProviderError,
    AssistantRequestError,
)
from .metrics import AssistantMetrics
from .prompts import SYSTEM_PROMPT, build_provider_prompt, cited_evidence
from .redaction import environment_snapshot, redact_text
from .reduction import reduce_context_tree

_OUTPUT_LIMIT_REASONS = {
    "length",
    "max_completion_tokens",
    "max_output_tokens",
    "max_tokens",
    "token_limit",
}


def _provider_output_limited(reason: str | None) -> bool:
    if not reason:
        return False
    normalized = reason.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in _OUTPUT_LIMIT_REASONS


@dataclass(frozen=True)
class _PreparedRequest:
    """Everything a request needs before the final model is called.

    Built in one shot so the blocking and streaming paths cannot drift: both spend the same
    RBAC filtering, redaction and local reduction, and both report the same byte breakdown.
    """

    context: AssistantContext
    provider: AnswerProvider | None = None
    reducer: ContextReducer | None = None
    prompt: str = ""
    prompt_bytes: AssistantPromptBytes = AssistantPromptBytes()
    reduced: str = ""
    reduction_truncated: bool = False
    reduction_context_limited: bool = False
    local_reduce_calls: int = 0

    @property
    def has_reports(self) -> bool:
        """Whether any readable report was in scope."""
        return bool(self.context.reports_considered)


class AssistantRuntime:
    """Lazy, concurrency-bounded orchestration shared by assistant requests."""

    def __init__(
        self,
        *,
        provider_factory: Callable[[], AnswerProvider] | None,
        reducer_factory: Callable[[], ContextReducer] | None,
        provider_name: str | None,
        model_name: str | None,
        context_model_name: str | None,
        max_context_bytes: int,
        max_output_tokens: int,
        max_concurrent: int,
        local_input_bytes: int | None = None,
        local_budget_seconds: float = 120.0,
        direct_max_summaries: int = MAX_SUMMARIES,
        max_failure_bytes: int = MAX_FAILURE_BYTES,
        max_capture_bytes: int = MAX_CAPTURE_BYTES,
        unavailable_reason: str | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._reducer_factory = reducer_factory
        self._provider_name = provider_name
        self._model_name = model_name
        self._context_model_name = context_model_name
        self._max_context_bytes = max_context_bytes
        self._max_output_tokens = max_output_tokens
        self._local_input_bytes = local_input_bytes or max_context_bytes
        self._local_budget_seconds = max(1.0, local_budget_seconds)
        self._direct_max_summaries = max(1, direct_max_summaries)
        self._max_failure_bytes = max(0, max_failure_bytes)
        self._max_capture_bytes = max(0, max_capture_bytes)
        self._unavailable_reason = unavailable_reason
        self._provider: AnswerProvider | None = None
        self._reducer: ContextReducer | None = None
        self._load_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))
        self.metrics = AssistantMetrics()
        self._metrics = self.metrics

    @classmethod
    def disabled(
        cls,
        reason: str,
        *,
        provider_name: str | None = None,
        model_name: str | None = None,
        context_model_name: str | None = None,
    ) -> AssistantRuntime:
        """Build an inert runtime whose status explains how to enable it."""
        return cls(
            provider_factory=None,
            reducer_factory=None,
            provider_name=provider_name,
            model_name=model_name,
            context_model_name=context_model_name,
            max_context_bytes=4_096,
            max_output_tokens=256,
            max_concurrent=1,
            unavailable_reason=reason,
        )

    @property
    def enabled(self) -> bool:
        """Whether a query can attempt to load the configured models."""
        return self._provider_factory is not None and not self._unavailable_reason

    def status(self) -> dict[str, Any]:
        """Return configuration readiness without loading either model."""
        return {
            "enabled": self.enabled,
            "provider": self._provider_name,
            "model": self._model_name,
            "context_model": self._context_model_name,
            "context_mode": (
                "local-full-tree" if self._context_model_name else "direct-bounded"
            ),
            "reason": self._unavailable_reason,
            "max_question_chars": MAX_QUESTION_CHARS,
            "max_history_messages": MAX_HISTORY_MESSAGES,
            "max_scope_reports": MAX_SCOPE_REPORTS,
            "direct_max_summaries": self._direct_max_summaries,
            "direct_max_detail_reports": None,
            "direct_max_failures_per_report": None,
            "max_context_bytes": self._max_context_bytes,
            "max_output_tokens": self._max_output_tokens,
            "max_failure_bytes": self._max_failure_bytes,
            "max_capture_bytes": self._max_capture_bytes,
            "local_complete_tree": bool(self._context_model_name),
            "local_input_bytes": (
                self._local_input_bytes if self._context_model_name else None
            ),
            "local_budget_seconds": (
                self._local_budget_seconds if self._context_model_name else None
            ),
            "max_history_chars": MAX_HISTORY_CHARS,
            "max_history_bytes": MAX_HISTORY_BYTES,
        }

    def ask(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> AssistantReply:
        """Build evidence, locally reduce it, and obtain one provider answer."""
        raw_question = self._admit(query)
        started = time.monotonic()
        prepared: _PreparedRequest | None = None
        outcome = "error"
        try:
            prepared = self._prepare(
                source=source, can_read=can_read, user=user, query=query
            )
            if not prepared.has_reports:
                outcome = "empty_scope"
                return self._empty_scope_reply(
                    raw_question, prepared.context.scope_label
                )
            assert prepared.provider is not None
            provider_started = time.monotonic()
            response = prepared.provider.answer(
                system=SYSTEM_PROMPT,
                prompt=prepared.prompt,
                max_tokens=self._max_output_tokens,
            )
            if isinstance(response, AssistantProviderResponse):
                reply = self._finish(
                    prepared, response.text, response.token_usage, response.stop_reason
                )
            else:
                reply = self._finish(prepared, response, None, None)
            outcome = "answered"
            self._record(
                prepared,
                outcome,
                reply=reply,
                provider_seconds=time.monotonic() - provider_started,
            )
            return reply
        except AssistantError:
            raise
        except Exception as exc:
            raise self._provider_failure(exc) from exc
        finally:
            if outcome != "answered":
                self._record(
                    prepared, outcome, provider_seconds=time.monotonic() - started
                )
            self._slots.release()

    def stream(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> Generator[tuple[str, dict[str, Any]], None, None]:
        """Yield ``(event, payload)`` pairs for one question as the answer is produced.

        The first item is always ``meta`` (or ``done`` for an empty scope), so the caller
        can turn a failure during preparation into a real HTTP status before any bytes are
        streamed. Abandoning the iterator -- the browser pressing **Stop**, or a dropped
        connection -- closes the generator, which releases the model slot.
        """
        raw_question = self._admit(query)
        started = time.monotonic()
        prepared: _PreparedRequest | None = None
        outcome = "stopped"
        try:
            prepared = self._prepare(
                source=source, can_read=can_read, user=user, query=query
            )
            if not prepared.has_reports:
                outcome = "empty_scope"
                empty = self._empty_scope_reply(
                    raw_question, prepared.context.scope_label
                )
                yield "done", empty.to_dict()
                return
            assert prepared.provider is not None and prepared.reducer is not None
            yield "meta", self._stream_meta(prepared)
            provider_started = time.monotonic()
            try:
                text, usage, stop_reason, cut = yield from self._stream_answer(prepared)
            except AssistantError:
                raise
            except Exception as exc:
                raise self._provider_failure(exc) from exc
            reply = self._finish(prepared, text, usage, stop_reason, truncated=cut)
            outcome = "answered"
            self._record(
                prepared,
                outcome,
                reply=reply,
                provider_seconds=time.monotonic() - provider_started,
            )
            yield "done", reply.to_dict()
        except AssistantError:
            outcome = "error"
            raise
        except Exception as exc:
            outcome = "error"
            raise self._provider_failure(exc) from exc
        finally:
            if outcome != "answered":
                self._record(
                    prepared, outcome, provider_seconds=time.monotonic() - started
                )
            self._slots.release()

    def _stream_answer(
        self, prepared: _PreparedRequest
    ) -> Generator[
        tuple[str, dict[str, Any]],
        None,
        tuple[str, AssistantTokenUsage | None, str | None, bool],
    ]:
        """Yield each ``delta``; return the answer, usage, stop reason and whether it was cut."""
        provider = prepared.provider
        assert provider is not None
        stream = getattr(provider, "stream", None)
        if stream is None:
            # A provider without incremental output still works; the browser simply gets
            # the whole answer as one delta instead of a typing effect.
            response = provider.answer(
                system=SYSTEM_PROMPT,
                prompt=prepared.prompt,
                max_tokens=self._max_output_tokens,
            )
            if isinstance(response, AssistantProviderResponse):
                if response.text:
                    yield "delta", {"text": response.text}
                return (
                    response.text,
                    response.token_usage,
                    response.stop_reason,
                    False,
                )
            if response:
                yield "delta", {"text": response}
            return response, None, None, False

        parts: list[str] = []
        size = 0
        usage: AssistantTokenUsage | None = None
        stop_reason: str | None = None
        cut_at_cap = False
        for item in stream(
            system=SYSTEM_PROMPT,
            prompt=prepared.prompt,
            max_tokens=self._max_output_tokens,
        ):
            if isinstance(item, AssistantProviderResponse):
                usage = item.token_usage
                stop_reason = item.stop_reason
                if item.text and not parts:
                    parts.append(item.text)
                    size += len(item.text.encode("utf-8", "replace"))
                    yield "delta", {"text": item.text}
                continue
            if not item:
                continue
            # A provider that never stops still cannot exceed the answer cap, and the
            # browser is never asked to render more than it would have received at once.
            # Chunks can land exactly on the cap, so remember the cut instead of inferring
            # it from the final size: a silently truncated answer is the worst outcome.
            if size >= MAX_ANSWER_BYTES:
                cut_at_cap = True
                break
            parts.append(item)
            size += len(item.encode("utf-8", "replace"))
            yield "delta", {"text": item}
        return "".join(parts), usage, stop_reason, cut_at_cap

    def _admit(self, query: AssistantQuery) -> str:
        """Validate the request and take a model slot, or raise the right assistant error."""
        if not self.enabled:
            raise AssistantDisabledError(
                self._unavailable_reason or "The report assistant is disabled."
            )
        raw_question = query.question.strip()
        if not raw_question:
            raise AssistantRequestError("The assistant question must not be empty.")
        if not self._slots.acquire(blocking=False):
            self._metrics.rejected(mode=self._mode)
            raise AssistantBusyError(
                "The report assistant is busy. Wait for the current answer and try again."
            )
        self._metrics.request_started()
        return raw_question

    def _provider_failure(self, exc: Exception) -> AssistantProviderError:
        reason = clip_utf8(redact_text(" ".join(str(exc).split())), 300)
        detail = f"{type(exc).__name__}: {reason}" if reason else type(exc).__name__
        return AssistantProviderError(
            f"The report assistant could not complete the answer: {detail}"
        )

    @property
    def _mode(self) -> str:
        return "local" if self._context_model_name else "direct"

    def _record(
        self,
        prepared: _PreparedRequest | None,
        outcome: str,
        *,
        reply: AssistantReply | None = None,
        provider_seconds: float = 0.0,
    ) -> None:
        usage = reply.token_usage if reply is not None else None
        self._metrics.request_finished(
            mode=self._mode,
            outcome=outcome,
            reports_considered=(
                prepared.context.reports_considered if prepared is not None else 0
            ),
            provider_seconds=provider_seconds,
            local_reduce_calls=(
                prepared.local_reduce_calls if prepared is not None else 0
            ),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            cached_input_tokens=usage.cached_input_tokens if usage else 0,
            context_limited=bool(reply is not None and reply.context_limited),
            output_limited=bool(reply is not None and reply.output_limited),
        )

    def _stream_meta(self, prepared: _PreparedRequest) -> dict[str, Any]:
        assert prepared.provider is not None and prepared.reducer is not None
        return {
            "provider": prepared.provider.name,
            "model": prepared.provider.model,
            "context_model": prepared.reducer.name,
            "reports_considered": prepared.context.reports_considered,
            "scope": prepared.context.scope_label,
            "prompt_bytes": prepared.prompt_bytes.to_dict(),
            "provider_input_bytes": prepared.prompt_bytes.total,
            "report_context": self._report_context(prepared).to_dict(),
        }

    def _prepare(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> _PreparedRequest:
        """Build the exact provider input for one question.

        Everything that redacts report fields happens here, inside a single environment
        snapshot. Streaming resumes on arbitrary worker threads between chunks, so the
        snapshot must not span a ``yield``.
        """
        with environment_snapshot():
            return self._build_prompt(
                source=source, can_read=can_read, user=user, query=query
            )

    def _build_prompt(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> _PreparedRequest:
        local_reduce_calls = 0
        builder = ReportContextBuilder(
            max_context_bytes=(
                self._local_input_bytes
                if self._context_model_name
                else self._max_context_bytes
            ),
            max_summaries=self._direct_max_summaries,
            max_failure_bytes=self._max_failure_bytes,
            max_capture_bytes=self._max_capture_bytes,
        )
        if self._context_model_name:
            context = builder.build_complete(
                source=source, can_read=can_read, user=user, query=query
            )
        else:
            context = builder.build(
                source=source, can_read=can_read, user=user, query=query
            )
        if not context.reports_considered:
            return _PreparedRequest(context=context)

        provider, reducer = self._models()
        question = clip_utf8(redact_text(query.question.strip()), MAX_QUESTION_CHARS)
        reduction_truncated = False
        reduction_context_limited = False
        if self._context_model_name:
            reduction = reduce_context_tree(
                question=question,
                chunks=context.chunks,
                reducer=reducer,
                max_bytes=self._max_context_bytes,
                input_bytes=self._local_input_bytes,
                budget_seconds=self._local_budget_seconds,
            )
            reduced = reduction.text
            local_reduce_calls = reduction.reducer_calls
            reduction_truncated = (
                reduction.hard_truncated
                or reduction.source_truncated
                or reduction.budget_exhausted
            )
            reduction_context_limited = (
                reduction.hard_truncated
                or reduction.budget_exhausted
                or bool(getattr(context.chunks, "context_limited", False))
            )
        else:
            reduced = redact_text(
                reducer.reduce(question=question, context=context.text)
            )
        provider_prompt = build_provider_prompt(
            question=question,
            history=query.history,
            evidence=reduced,
        )
        prompt_bytes = AssistantPromptBytes(
            system=len(SYSTEM_PROMPT.encode("utf-8")),
            user=provider_prompt.user_bytes,
            context=provider_prompt.context_bytes,
            history=provider_prompt.history_bytes,
            structure=provider_prompt.structure_bytes,
        )
        return _PreparedRequest(
            context=context,
            provider=provider,
            reducer=reducer,
            prompt=provider_prompt.text,
            prompt_bytes=prompt_bytes,
            reduced=reduced,
            reduction_truncated=reduction_truncated,
            reduction_context_limited=reduction_context_limited,
            local_reduce_calls=local_reduce_calls,
        )

    def _report_context(self, prepared: _PreparedRequest) -> AssistantReportContext:
        return AssistantReportContext(
            content=prepared.reduced,
            format=(
                "locally-reduced-text"
                if self._context_model_name
                else "direct-snapshot-jsonl"
            ),
        )

    def _finish(
        self,
        prepared: _PreparedRequest,
        raw_answer: str,
        token_usage: AssistantTokenUsage | None,
        stop_reason: str | None,
        *,
        truncated: bool = False,
    ) -> AssistantReply:
        """Turn a completed provider response into the reply both paths return."""
        assert prepared.provider is not None and prepared.reducer is not None
        stripped = raw_answer.strip()
        output_limited = (
            truncated
            or len(stripped.encode("utf-8", "replace")) > MAX_ANSWER_BYTES
            or _provider_output_limited(stop_reason)
        )
        if (
            stop_reason is None
            and token_usage is not None
            and token_usage.output_tokens >= self._max_output_tokens
        ):
            output_limited = True
        answer = clip_utf8(stripped, MAX_ANSWER_BYTES)
        if not answer:
            raise AssistantProviderError(
                "The configured model returned an empty answer. Try again."
            )
        context = prepared.context
        return AssistantReply(
            answer=answer,
            evidence=cited_evidence(answer, context.evidence),
            provider=prepared.provider.name,
            model=prepared.provider.model,
            context_model=prepared.reducer.name,
            reports_considered=context.reports_considered,
            truncated=context.truncated or prepared.reduction_truncated,
            context_limited=(
                context.context_limited or prepared.reduction_context_limited
            ),
            scope=context.scope_label,
            prompt_bytes=prepared.prompt_bytes,
            token_usage=token_usage,
            report_context=self._report_context(prepared),
            output_limited=output_limited,
        )

    def _empty_scope_reply(self, question: str, scope_label: str) -> AssistantReply:
        no_reports = (
            "В текущей области нет доступных отчётов. "
            "Сбросьте или расширьте фильтры и попробуйте снова."
            if re.search(r"[А-Яа-яЁё]", question)
            else "No readable reports match the current scope. "
            "Clear or widen the dashboard filters and try again."
        )
        return AssistantReply(
            answer=no_reports,
            evidence=(),
            provider=self._provider_name or "",
            model=self._model_name or "",
            context_model=self._context_model_name,
            reports_considered=0,
            truncated=False,
            context_limited=False,
            scope=scope_label,
            prompt_bytes=AssistantPromptBytes(),
            token_usage=None,
            report_context=None,
            output_limited=False,
        )

    def _models(self) -> tuple[AnswerProvider, ContextReducer]:
        if self._provider is not None and self._reducer is not None:
            return self._provider, self._reducer
        with self._load_lock:
            if self._provider is None:
                if self._provider_factory is None:  # pragma: no cover - enabled guard
                    raise AssistantDisabledError("The report assistant is disabled.")
                self._provider = self._provider_factory()
            if self._reducer is None:
                if (
                    self._reducer_factory is None
                ):  # pragma: no cover - configured factory
                    raise AssistantDisabledError("No context reducer is configured.")
                self._reducer = self._reducer_factory()
        return self._provider, self._reducer

    def close(self) -> None:
        """Best-effort teardown for FastAPI shutdown and repeated test clients."""
        with self._load_lock:
            for model in (self._provider, self._reducer):
                if model is None:
                    continue
                try:
                    model.close()
                except Exception:
                    pass
            self._provider = None
            self._reducer = None


__all__ = ["AssistantRuntime"]
