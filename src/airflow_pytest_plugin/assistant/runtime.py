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
from collections.abc import Callable
from typing import Any

from ..sources import ReportSource
from .common import (
    MAX_ANSWER_BYTES,
    MAX_CAPTURE_BYTES,
    MAX_FAILURE_BYTES,
    MAX_HISTORY_MESSAGES,
    MAX_QUESTION_CHARS,
    MAX_SCOPE_REPORTS,
    MAX_SUMMARIES,
    AnswerProvider,
    AssistantPromptBytes,
    AssistantProviderResponse,
    AssistantQuery,
    AssistantReply,
    AssistantReportContext,
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
from .prompts import SYSTEM_PROMPT, build_provider_prompt, cited_evidence
from .redaction import redact_text
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
        self._direct_max_summaries = max(1, direct_max_summaries)
        self._max_failure_bytes = max(0, max_failure_bytes)
        self._max_capture_bytes = max(0, max_capture_bytes)
        self._unavailable_reason = unavailable_reason
        self._provider: AnswerProvider | None = None
        self._reducer: ContextReducer | None = None
        self._load_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))

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
        if not self.enabled:
            raise AssistantDisabledError(
                self._unavailable_reason or "The report assistant is disabled."
            )
        raw_question = query.question.strip()
        if not raw_question:
            raise AssistantRequestError("The assistant question must not be empty.")
        if not self._slots.acquire(blocking=False):
            raise AssistantBusyError(
                "The report assistant is busy. Wait for the current answer and try again."
            )
        try:
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
                return self._empty_scope_reply(raw_question, context.scope_label)

            provider, reducer = self._models()
            question = clip_utf8(redact_text(raw_question), MAX_QUESTION_CHARS)
            reduction_truncated = False
            reduction_context_limited = False
            if self._context_model_name:
                reduction = reduce_context_tree(
                    question=question,
                    chunks=context.chunks,
                    reducer=reducer,
                    max_bytes=self._max_context_bytes,
                    input_bytes=self._local_input_bytes,
                )
                reduced = reduction.text
                reduction_truncated = (
                    reduction.hard_truncated or reduction.source_truncated
                )
                reduction_context_limited = reduction.hard_truncated or bool(
                    getattr(context.chunks, "context_limited", False)
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
            provider_response = provider.answer(
                system=SYSTEM_PROMPT,
                prompt=provider_prompt.text,
                max_tokens=self._max_output_tokens,
            )
            if isinstance(provider_response, AssistantProviderResponse):
                raw_answer = provider_response.text
                token_usage = provider_response.token_usage
                stop_reason = provider_response.stop_reason
            else:
                raw_answer = provider_response
                token_usage = None
                stop_reason = None
            stripped_answer = raw_answer.strip()
            answer_was_clipped = (
                len(stripped_answer.encode("utf-8", "replace")) > MAX_ANSWER_BYTES
            )
            output_limited = answer_was_clipped or _provider_output_limited(stop_reason)
            if (
                stop_reason is None
                and token_usage is not None
                and token_usage.output_tokens >= self._max_output_tokens
            ):
                output_limited = True
            answer = clip_utf8(stripped_answer, MAX_ANSWER_BYTES)
            if not answer:
                raise AssistantProviderError(
                    "The configured model returned an empty answer. Try again."
                )
            return AssistantReply(
                answer=answer,
                evidence=cited_evidence(answer, context.evidence),
                provider=provider.name,
                model=provider.model,
                context_model=reducer.name,
                reports_considered=context.reports_considered,
                truncated=context.truncated or reduction_truncated,
                context_limited=(context.context_limited or reduction_context_limited),
                scope=context.scope_label,
                prompt_bytes=prompt_bytes,
                token_usage=token_usage,
                report_context=AssistantReportContext(
                    content=reduced,
                    format=(
                        "locally-reduced-text"
                        if self._context_model_name
                        else "direct-snapshot-jsonl"
                    ),
                ),
                output_limited=output_limited,
            )
        except AssistantError:
            raise
        except Exception as exc:
            reason = clip_utf8(redact_text(" ".join(str(exc).split())), 300)
            detail = f"{type(exc).__name__}: {reason}" if reason else type(exc).__name__
            raise AssistantProviderError(
                f"The report assistant could not complete the answer: {detail}"
            ) from exc
        finally:
            self._slots.release()

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
