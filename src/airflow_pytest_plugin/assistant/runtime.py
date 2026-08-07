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

import threading
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any

from .. import chatcrypto
from ..sources import ReportSource
from . import audit
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
    encodable,
)
from .context import ReportContextBuilder
from .docs import DocumentationLibrary
from .exceptions import (
    AssistantBusyError,
    AssistantDisabledError,
    AssistantError,
    AssistantForbiddenError,
    AssistantProviderError,
    AssistantQuotaError,
    AssistantRequestError,
)
from .limits import QuotaStore, RateStore, UserLimits, estimated_tokens
from .metrics import AssistantMetrics
from .prompts import (
    SYSTEM_PROMPT,
    build_provider_prompt,
    build_system_prompt,
    cited_evidence,
    command_catalogue,
    no_evidence_text,
    parse_command,
)
from .redaction import environment_snapshot, redact_text
from .reduction import reduce_context_tree_events

#: The whole prompt of a readiness check. Fixed, tiny, and free of report data: the point
#: is to prove the credentials and endpoint work, not to spend a real context on it.
HEALTH_PROBE = "Reply with the single word OK."
HEALTH_SYSTEM = "You are a readiness probe. Reply with the single word OK."
_HEALTH_MAX_TOKENS = 16
_HEALTH_CACHE_SECONDS = 60.0

#: Distinguishes "no user was passed" from "the user is None", which is itself an identity
#: (a viewer running with no auth manager) and must be answered for, not skipped.
_NO_USER = object()

_OUTPUT_LIMIT_REASONS = {
    "length",
    "max_completion_tokens",
    "max_output_tokens",
    "max_tokens",
    "token_limit",
}


def _error_outcome(error: AssistantError) -> str:
    """Name the terminal state of a request that ended in an expected assistant error."""
    if isinstance(error, AssistantForbiddenError):
        return "forbidden"
    if isinstance(error, AssistantRequestError):
        return "bad_request"
    if isinstance(error, AssistantQuotaError):
        return "rate_limited"
    return "error"


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
    #: Assembled per question: the always-on rules plus whichever skills it asked for.
    system: str = SYSTEM_PROMPT
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
        rate_limit: int = 0,
        rate_window_seconds: float = 3_600.0,
        daily_token_quota: int = 0,
        quota_store: QuotaStore | None = None,
        rate_store: RateStore | None = None,
        history: Any = None,
        history_days: int = 0,
        direct_max_summaries: int = MAX_SUMMARIES,
        max_failure_bytes: int = MAX_FAILURE_BYTES,
        max_capture_bytes: int = MAX_CAPTURE_BYTES,
        documentation: DocumentationLibrary | None = None,
        docs_bytes: int = 0,
        unavailable_reason: str | None = None,
        configured: bool = True,
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
        self._configured = configured
        #: Product manuals an operator mounted. Empty unless configured, and the selection
        #: is per question, so a deployment without them pays nothing at all.
        self.documentation = documentation or DocumentationLibrary()
        #: How much documentation one question may carry. Public beside ``documentation``:
        #: the two are meaningless apart, and a test that supplies one must set the other.
        self.docs_bytes = max(0, docs_bytes)
        self._provider: AnswerProvider | None = None
        self._reducer: ContextReducer | None = None
        self._load_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))
        self.metrics = AssistantMetrics()
        self._metrics = self.metrics
        self.limits = UserLimits(
            rate_limit=rate_limit,
            rate_window_seconds=rate_window_seconds,
            daily_token_quota=daily_token_quota,
            store=quota_store,
            rate_store=rate_store,
        )
        self._history = history
        self._history_days = max(0, history_days)
        # ``None`` rather than 0.0: the clock is monotonic and counts from boot, so zero
        # is not "long ago" but "an hour after this host came up", which is when the first
        # sweep would otherwise happen.
        self._purged_at: float | None = None
        self._clock = time.monotonic
        self._health: dict[str, Any] | None = None
        self._health_at = 0.0

    @classmethod
    def disabled(
        cls,
        reason: str,
        *,
        provider_name: str | None = None,
        model_name: str | None = None,
        context_model_name: str | None = None,
        configured: bool = False,
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
            configured=configured,
        )

    @property
    def enabled(self) -> bool:
        """Whether a query can attempt to load the configured models."""
        return self._provider_factory is not None and not self._unavailable_reason

    @property
    def configured(self) -> bool:
        """Whether an operator asked for this feature, working or not.

        Separate from :attr:`enabled` so the viewer can stay silent about an assistant
        nobody installed while still explaining one that was installed wrong.
        """
        return self._configured

    def status(self, user: Any = _NO_USER) -> dict[str, Any]:
        """Return configuration readiness without loading either model.

        ``user`` decides only whether *this* caller gets server-side chats: the tables can
        be there and working while the acting identity still cannot own a row. Announcing
        stored chats to such a viewer puts a chat list in their panel that can only ever be
        empty.
        """
        stored_for_caller = self.history_enabled and (
            user is _NO_USER or self._can_own_history(user)
        )
        return {
            "enabled": self.enabled,
            "configured": self.configured,
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
            "rate_limit": self.limits.rate_limit,
            "rate_window_seconds": self.limits.rate_window_seconds,
            "daily_token_quota": self.limits.daily_token_quota,
            "quota_shared": self.limits.shared,
            "rate_shared": self.limits.rate_shared,
            "commands": command_catalogue(),
            "history_server_side": stored_for_caller,
            "history_days": self._history_days if stored_for_caller else None,
            # Whether the transcript this server stores is encrypted at rest. Only
            # meaningful when it stores one, and it is the operator's answer to "who
            # else can read my team's questions" -- so it is reported rather than
            # assumed.
            "history_encrypted": (chatcrypto.enabled() if stored_for_caller else None),
        }

    def _can_own_history(self, user: Any) -> bool:
        """Whether this identity may own stored rows at all."""
        return bool(
            self._history is not None and self._history.storable(audit.principal(user))
        )

    @property
    def history_enabled(self) -> bool:
        """Whether completed exchanges are stored server-side."""
        return bool(
            self._history is not None and self._history_days and self._history.available
        )

    def history(
        self,
        user: Any,
        *,
        limit: int = MAX_HISTORY_MESSAGES,
        conversation: str | None = None,
        can_read: Callable[[str, Any], bool] | None = None,
    ) -> dict[str, Any]:
        """Return one stored chat for the acting user, plus the list of their chats.

        ``can_read`` re-checks the stored ``[R<n>]`` links. Permissions change after an
        answer is written, and those links name a DAG, task and run: replaying them to
        someone who has since lost access would hand back identifiers they may no longer
        read, and buttons that can only 403. The text of their own conversation is theirs
        either way -- only the report links are filtered.
        """
        who = audit.principal(user)
        if not self.history_enabled:
            return {
                "available": False,
                "messages": [],
                "conversation": None,
                "conversations": [],
            }
        from .. import db

        wanted = db.clean_conversation(conversation) if conversation else None
        storable = self._history.storable(who)
        if not storable:
            return {
                "available": False,
                "messages": [],
                "conversation": None,
                "conversations": [],
            }
        chats = self._history.conversations(who, limit=db.MAX_CONVERSATIONS)
        current = wanted or (chats[0]["id"] if chats else None)
        return {
            "available": True,
            "conversation": current,
            "conversations": chats,
            "messages": (
                self._filtered_history(
                    self._history.load(who, limit=limit, conversation=current),
                    user=user,
                    can_read=can_read,
                )
                if current
                else []
            ),
        }

    @staticmethod
    def _filtered_history(
        messages: list[dict[str, Any]],
        *,
        user: Any,
        can_read: Callable[[str, Any], bool] | None,
    ) -> list[dict[str, Any]]:
        """Drop stored evidence links whose DAG the caller may no longer read."""
        if can_read is None:
            return messages
        allowed: dict[str, bool] = {}

        def readable(dag_id: str) -> bool:
            if dag_id not in allowed:
                try:
                    allowed[dag_id] = bool(can_read(dag_id, user))
                except Exception:  # pragma: no cover - a hostile authorizer denies
                    allowed[dag_id] = False
            return allowed[dag_id]

        for message in messages:
            evidence = message.get("evidence") or []
            if evidence:
                message["evidence"] = [
                    item for item in evidence if readable(str(item.get("dag_id", "")))
                ]
        return messages

    def rename(self, user: Any, *, conversation: str, title: str) -> int:
        """Name one of the acting user's chats. Returns how many were renamed."""
        if self._history is None or not self._history.available:
            return 0
        who = audit.principal(user)
        renamed = int(self._history.rename(who, conversation, title))
        if renamed:
            audit.record(
                event="assistant.history.rename",
                principal=who,
                outcome="renamed",
                conversation=conversation,
            )
        return renamed

    def forget(self, user: Any, *, conversation: str | None = None) -> int:
        """Delete one stored chat, or every one of them. Returns how many rows went."""
        if self._history is None or not self._history.available:
            return 0
        from .. import db

        who = audit.principal(user)
        chat = db.clean_conversation(conversation) if conversation else None
        removed = int(self._history.clear(who, conversation=chat))
        audit.record(
            event="assistant.history.clear",
            principal=who,
            outcome="cleared",
            conversation=chat,
            messages=removed,
        )
        return removed

    def _remember(
        self, user: Any, question: str, reply: AssistantReply, conversation: str
    ) -> None:
        """Store one completed exchange in the chat it belongs to.

        The question is stored the way the model saw it -- redacted. A value scrubbed on
        its way to a provider must not survive in Airflow's metadata database instead,
        where it would be readable for the whole retention period and replayed into every
        later prompt.
        """
        if not self.history_enabled:
            return
        from .. import db

        with environment_snapshot():
            stored_question = redact_text(question)
        self._history.append(
            audit.principal(user),
            stored_question,
            reply.answer,
            [item.to_dict() for item in reply.evidence],
            reply.token_usage.total_tokens if reply.token_usage else 0,
            conversation=db.clean_conversation(conversation),
        )

    def _sweep(self) -> None:
        """Drop rows nothing will read again: expired chats, finished rate windows.

        Called from the audit step so it runs for every outcome, not only for stored
        answers -- rate rows are written by a deployment that keeps no history at all.
        Retention has no scheduler on the reader side, so it rides along with requests at
        most once an hour per process, which is cheap and needs no operator wiring.
        """
        now = self._clock()
        if self._purged_at is not None and now - self._purged_at < 3_600:
            return
        self._purged_at = now
        try:
            from datetime import datetime, timedelta, timezone

            from .. import db

            if self.history_enabled:
                db.purge_history(
                    before=datetime.now(timezone.utc)
                    - timedelta(days=self._history_days)
                )
            if self.limits.rate_shared:
                # One row per principal per window, written by every admitted question.
                # Only the window in progress is still consulted.
                db.purge_rate_windows(
                    before=db.live_rate_window(self.limits.rate_window_seconds)
                )
        except Exception:  # pragma: no cover - retention must never fail a request
            pass

    def health(self, *, force: bool = False) -> dict[str, Any]:
        """Prove the configured models actually answer, without any report data.

        ``status`` only validates configuration, so a wrong key or an unreachable endpoint
        is otherwise discovered by the first user question. This sends one fixed, tiny probe
        instead. It takes the same model slot as a real question -- a readiness check must
        never race a paying request -- and the result is cached, so polling the endpoint
        cannot multiply provider cost.
        """
        if not self.enabled:
            raise AssistantDisabledError(
                self._unavailable_reason or "The report assistant is disabled."
            )
        now = self._clock()
        cached = self._health
        if (
            not force
            and cached is not None
            and now - self._health_at < _HEALTH_CACHE_SECONDS
        ):
            return {**cached, "cached": True}
        if not self._slots.acquire(blocking=False):
            raise AssistantBusyError(
                "The report assistant is busy. Wait for the current answer and try again."
            )
        try:
            result = self._probe()
        finally:
            self._slots.release()
        self._health = result
        self._health_at = self._clock()
        return {**result, "cached": False}

    def _probe(self) -> dict[str, Any]:
        started = self._clock()
        result: dict[str, Any] = {
            "ok": False,
            "provider": self._provider_name,
            "model": self._model_name,
            "context_model": self._context_model_name,
            "context_model_ok": None,
            "detail": None,
            "latency_ms": 0,
            "checked_at": time.time(),
        }
        try:
            provider, reducer = self._models()
            response = provider.answer(
                system=HEALTH_SYSTEM,
                prompt=HEALTH_PROBE,
                max_tokens=_HEALTH_MAX_TOKENS,
            )
            text = (
                response.text
                if isinstance(response, AssistantProviderResponse)
                else response
            )
            result["provider"] = provider.name
            result["model"] = provider.model
            if not text or not text.strip():
                result["detail"] = "The provider returned an empty answer."
                return result
            if reducer.name is not None:
                # Loading the GGUF is the expensive half of a local deployment, so a
                # readiness check that skipped it would miss the usual failure.
                summary = reducer.reduce(question=HEALTH_PROBE, context=HEALTH_PROBE)
                result["context_model"] = reducer.name
                result["context_model_ok"] = bool(summary and summary.strip())
                if not result["context_model_ok"]:
                    result["detail"] = "The local context model returned nothing."
                    return result
            result["ok"] = True
            return result
        except Exception as exc:
            reason = clip_utf8(redact_text(" ".join(str(exc).split())), 300)
            result["detail"] = (
                f"{type(exc).__name__}: {reason}" if reason else type(exc).__name__
            )
            return result
        finally:
            result["latency_ms"] = max(0, int((self._clock() - started) * 1000))

    def ask(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> AssistantReply:
        """Build evidence, locally reduce it, and obtain one provider answer."""
        who = audit.principal(user)
        started = time.monotonic()
        try:
            raw_question = self._admit(query, who)
        except AssistantError as exc:
            self._audit_refusal(exc, who, query, started, streamed=False)
            raise
        prepared: _PreparedRequest | None = None
        audit_reply: AssistantReply | None = None
        outcome = "error"
        try:
            prepared = self._prepare(
                source=source, can_read=can_read, user=user, query=query
            )
            assert prepared.provider is not None
            provider_started = time.monotonic()
            response = prepared.provider.answer(
                system=prepared.system,
                prompt=prepared.prompt,
                max_tokens=self._max_output_tokens,
            )
            if isinstance(response, AssistantProviderResponse):
                reply = self._finish(
                    prepared, response.text, response.token_usage, response.stop_reason
                )
                outcome = "answered" if prepared.has_reports else "empty_scope"
            else:
                reply = self._finish(prepared, response, None, None)
            outcome = "answered" if prepared.has_reports else "empty_scope"
            self._record(
                prepared,
                outcome,
                reply=reply,
                provider_seconds=time.monotonic() - provider_started,
            )
            audit_reply = reply
            return reply
        except AssistantError as exc:
            outcome = _error_outcome(exc)
            raise
        except Exception as exc:
            outcome = "error"
            raise self._provider_failure(exc) from exc
        finally:
            # `audit_reply` is set only where the request already recorded itself. An
            # answer over an empty scope is a completed request whose outcome is not
            # "answered", so keying this on the outcome counted it twice.
            if audit_reply is None:
                self._record(
                    prepared, outcome, provider_seconds=time.monotonic() - started
                )
            self._audit(
                prepared,
                outcome,
                user=user,
                question=raw_question,
                started=started,
                streamed=False,
                reply=audit_reply,
                conversation=query.conversation,
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
        who = audit.principal(user)
        started = time.monotonic()
        try:
            raw_question = self._admit(query, who)
        except AssistantError as exc:
            self._audit_refusal(exc, who, query, started, streamed=True)
            raise
        prepared: _PreparedRequest | None = None
        audit_reply: AssistantReply | None = None
        remembered = False
        outcome = "stopped"
        try:
            # Progress is yielded from inside the local phase, which also makes that
            # phase cancellable: abandoning this generator raises GeneratorExit at the
            # chunk boundary it is suspended on, instead of burning the rest of the
            # budget on an answer nobody is waiting for.
            prepared = yield from self._forward_progress(
                self._prepare_events(
                    source=source, can_read=can_read, user=user, query=query
                )
            )
            assert prepared.provider is not None
            yield "meta", self._stream_meta(prepared)
            provider_started = time.monotonic()
            try:
                text, usage, stop_reason, cut = yield from self._stream_answer(prepared)
            except AssistantError:
                raise
            except Exception as exc:
                raise self._provider_failure(exc) from exc
            reply = self._finish(prepared, text, usage, stop_reason, truncated=cut)
            outcome = "answered" if prepared.has_reports else "empty_scope"
            self._record(
                prepared,
                outcome,
                reply=reply,
                provider_seconds=time.monotonic() - provider_started,
            )
            audit_reply = reply
            # Stored *before* the browser is told the answer is finished. Everything
            # else about this request can settle afterwards, but the transcript cannot:
            # a reader who opens the chat list -- or reloads -- in the moment the answer
            # appears would be shown a chat that does not have it yet.
            if outcome == "answered":
                self._remember(user, raw_question, reply, query.conversation)
                remembered = True
            yield "done", reply.to_dict()
        except AssistantError as exc:
            outcome = _error_outcome(exc)
            raise
        except Exception as exc:
            outcome = "error"
            raise self._provider_failure(exc) from exc
        finally:
            # `audit_reply` is set only where the request already recorded itself. An
            # answer over an empty scope is a completed request whose outcome is not
            # "answered", so keying this on the outcome counted it twice.
            if audit_reply is None:
                self._record(
                    prepared, outcome, provider_seconds=time.monotonic() - started
                )
            self._audit(
                prepared,
                outcome,
                user=user,
                question=raw_question,
                started=started,
                streamed=True,
                reply=audit_reply,
                conversation=query.conversation,
                remember=not remembered,
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
                system=prepared.system,
                prompt=prepared.prompt,
                max_tokens=self._max_output_tokens,
            )
            if isinstance(response, AssistantProviderResponse):
                if response.text:
                    yield "delta", {"text": encodable(response.text)}
                return (
                    response.text,
                    response.token_usage,
                    response.stop_reason,
                    False,
                )
            if response:
                yield "delta", {"text": encodable(response)}
            return response, None, None, False

        parts: list[str] = []
        size = 0
        usage: AssistantTokenUsage | None = None
        stop_reason: str | None = None
        cut_at_cap = False
        for item in stream(
            system=prepared.system,
            prompt=prepared.prompt,
            max_tokens=self._max_output_tokens,
        ):
            if isinstance(item, AssistantProviderResponse):
                usage = item.token_usage
                stop_reason = item.stop_reason
                if item.text and not parts:
                    parts.append(item.text)
                    size += len(item.text.encode("utf-8", "replace"))
                    yield "delta", {"text": encodable(item.text)}
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
            # Sanitised per delta, not only in the finished answer: a stream is already
            # half-written when it reaches the browser, so a chunk that cannot encode
            # would tear the connection instead of returning an error.
            yield "delta", {"text": encodable(item)}
        return "".join(parts), usage, stop_reason, cut_at_cap

    def _admit(self, query: AssistantQuery, who: str) -> str:
        """Validate the request and take a model slot, or raise the right assistant error.

        The per-principal budget is consulted before the slot is taken, so a refused
        request costs no memory, no provider call, and cannot displace a paying one.
        """
        if not self.enabled:
            raise AssistantDisabledError(
                self._unavailable_reason or "The report assistant is disabled."
            )
        raw_question = query.question.strip()
        if not raw_question:
            raise AssistantRequestError("The assistant question must not be empty.")
        decision = self.limits.check(who)
        if not decision.allowed:
            self._metrics.request_finished(mode=self._mode, outcome="rate_limited")
            raise AssistantQuotaError(
                (
                    "You have reached your daily assistant token quota. "
                    "It resets at midnight UTC."
                )
                if decision.reason == "daily_token_quota"
                else (
                    "You are asking the assistant too quickly. "
                    f"Try again in {decision.retry_after} seconds."
                ),
                retry_after=decision.retry_after,
            )
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

    @staticmethod
    def _billable(prepared: _PreparedRequest | None, reply: AssistantReply) -> int:
        """Return the tokens to charge this request against its principal's budget.

        The provider's own count wins whenever it gave one. It is only when a provider
        stays silent -- a gateway that drops ``usage``, a self-hosted OpenAI-compatible
        endpoint -- that the size of the exchange is used instead, so a configured budget
        keeps draining rather than quietly ceasing to apply.
        """
        usage = reply.token_usage
        if usage is not None and usage.total_tokens > 0:
            return usage.total_tokens
        return estimated_tokens(
            prepared.prompt_bytes.total if prepared is not None else 0,
            len(reply.answer.encode("utf-8", "replace")),
        )

    def _audit(
        self,
        prepared: _PreparedRequest | None,
        outcome: str,
        *,
        user: Any,
        question: str,
        started: float,
        streamed: bool,
        reply: AssistantReply | None,
        conversation: str = "",
        remember: bool = True,
    ) -> None:
        """Emit exactly one audit record for this request, whatever its outcome.

        ``remember`` is false where the streaming path has already stored the exchange,
        which it does before announcing completion rather than after.
        """
        usage = reply.token_usage if reply is not None else None
        if reply is not None:
            self.limits.charge(audit.principal(user), self._billable(prepared, reply))
        if reply is not None and outcome == "answered" and remember:
            self._remember(user, question, reply, conversation)
        self._sweep()
        context = prepared.context if prepared is not None else None
        audit.record(
            event="assistant.query",
            principal=audit.principal(user),
            outcome=outcome,
            streamed=streamed,
            mode=self._mode,
            provider=self._provider_name,
            model=self._model_name,
            context_model=self._context_model_name,
            scope=context.scope_label if context is not None else None,
            reports_considered=context.reports_considered if context is not None else 0,
            dags=audit.dag_ids(context.evidence) if context is not None else [],
            question_chars=len(question),
            question_sha256=audit.question_digest(question),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            context_limited=bool(reply is not None and reply.context_limited),
            output_limited=bool(reply is not None and reply.output_limited),
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

    def _audit_refusal(
        self,
        error: AssistantError,
        who: str,
        query: AssistantQuery,
        started: float,
        *,
        streamed: bool,
    ) -> None:
        """Audit a request refused before it ever held a slot."""
        question = query.question.strip()
        audit.record(
            event="assistant.query",
            principal=who,
            outcome=_error_outcome(error),
            streamed=streamed,
            mode=self._mode,
            provider=self._provider_name,
            model=self._model_name,
            reports_considered=0,
            dags=[],
            question_chars=len(question),
            question_sha256=audit.question_digest(question),
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

    def _stream_meta(self, prepared: _PreparedRequest) -> dict[str, Any]:
        assert prepared.provider is not None
        return {
            "provider": prepared.provider.name,
            "model": prepared.provider.model,
            # No reducer is loaded when there was nothing to reduce, so the configured
            # name is the honest answer about which mode this deployment is in.
            "context_model": (
                prepared.reducer.name
                if prepared.reducer is not None
                else self._context_model_name
            ),
            "reports_considered": prepared.context.reports_considered,
            "scope": prepared.context.scope_label,
            "prompt_bytes": prepared.prompt_bytes.to_dict(),
            "provider_input_bytes": prepared.prompt_bytes.total,
            "report_context": self._report_context(prepared).to_dict(),
        }

    @staticmethod
    def _forward_progress(
        events: Generator[dict[str, Any], None, _PreparedRequest],
    ) -> Generator[tuple[str, dict[str, Any]], None, _PreparedRequest]:
        """Re-label preparation progress as stream events and return the result."""
        while True:
            try:
                payload = next(events)
            except StopIteration as stop:
                prepared: _PreparedRequest = stop.value
                return prepared
            yield "progress", payload

    def _prepare(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> _PreparedRequest:
        """Build the exact provider input for one question, ignoring progress."""
        events = self._prepare_events(
            source=source, can_read=can_read, user=user, query=query
        )
        while True:
            try:
                next(events)
            except StopIteration as stop:
                prepared: _PreparedRequest = stop.value
                return prepared

    def _prepare_events(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> Generator[dict[str, Any], None, _PreparedRequest]:
        """Build the provider input, reporting progress through the local phase.

        Both request paths run this one generator, so the blocking and streaming answers
        cannot drift apart. Every step that redacts report fields is wrapped in its own
        environment snapshot and none of them spans a ``yield``: the snapshot is pinned
        per thread, and a generator resumes on whichever worker thread the server picked.
        """
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
        with environment_snapshot():
            if self._context_model_name:
                context = builder.build_complete(
                    source=source, can_read=can_read, user=user, query=query
                )
            else:
                context = builder.build(
                    source=source, can_read=can_read, user=user, query=query
                )
            # A leading /command names the skill outright. It is an instruction to us,
            # so it comes off before the question reaches the model.
            commands, asked = parse_command(query.question.strip())
            question = clip_utf8(redact_text(asked), MAX_QUESTION_CHARS)

        # Nothing to reduce when no report matched, so the local model is not loaded at
        # all: pulling gigabytes of GGUF into memory to answer "no report matched" -- or a
        # question about the product, which needs no evidence -- would be absurd.
        empty = not context.reports_considered
        if self._context_model_name and not empty:
            # Loading a GGUF takes seconds on its own, and it is the first thing that
            # happens after the user presses Send.
            yield {"phase": "loading_model"}
        provider, reducer = self._answer_model() if empty else self._models()
        reduction_truncated = False
        reduction_context_limited = False
        if empty:
            # Which "no evidence" this is depends on what was asked: a question about the
            # user's runs found nothing, while a request to write a test never needed a
            # report at all and must not be answered with "widen your filters".
            reduced = no_evidence_text(commands=commands, question=question)
            reducer = None
        elif self._context_model_name:
            assert reducer is not None
            reduction = yield from reduce_context_tree_events(
                question=question,
                chunks=context.chunks,
                reducer=reducer,
                max_bytes=self._max_context_bytes,
                input_bytes=self._local_input_bytes,
                budget_seconds=self._local_budget_seconds,
                scope=environment_snapshot,
            )
            reduced = reduction.text
            local_reduce_calls = reduction.reducer_calls
            reduction_truncated = (
                reduction.hard_truncated
                or reduction.source_truncated
                or reduction.budget_exhausted
                or reduction.degenerate
            )
            reduction_context_limited = (
                reduction.hard_truncated
                or reduction.budget_exhausted
                or reduction.degenerate
                or bool(getattr(context.chunks, "context_limited", False))
            )
        else:
            assert reducer is not None
            with environment_snapshot():
                reduced = redact_text(
                    reducer.reduce(question=question, context=context.text)
                )
        documentation = self.documentation.select(
            question, budget=self.docs_bytes, forced="docs" in commands
        )
        system = build_system_prompt(
            question, has_documentation=bool(documentation), commands=commands
        )
        provider_prompt = build_provider_prompt(
            question=question,
            history=query.history,
            evidence=reduced,
            locale=query.locale,
            docs=documentation,
        )
        prompt_bytes = AssistantPromptBytes(
            system=len(system.encode("utf-8")),
            user=provider_prompt.user_bytes,
            context=provider_prompt.context_bytes,
            history=provider_prompt.history_bytes,
            docs=provider_prompt.docs_bytes,
            structure=provider_prompt.structure_bytes,
        )
        return _PreparedRequest(
            context=context,
            provider=provider,
            reducer=reducer,
            system=system,
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
        assert prepared.provider is not None
        stripped = encodable(raw_answer).strip()
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
            context_model=(
                prepared.reducer.name
                if prepared.reducer is not None
                else self._context_model_name
            ),
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

    def _answer_model(self) -> tuple[AnswerProvider, ContextReducer | None]:
        """Load only the provider. Used when there is no evidence to reduce."""
        if self._provider is None:
            with self._load_lock:
                if self._provider is None:
                    if self._provider_factory is None:  # pragma: no cover - guarded
                        raise AssistantDisabledError(
                            "The report assistant is disabled."
                        )
                    self._provider = self._provider_factory()
        return self._provider, self._reducer

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
