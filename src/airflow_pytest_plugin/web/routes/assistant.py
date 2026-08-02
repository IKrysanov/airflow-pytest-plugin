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

"""Read-only report-assistant status and query routes."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ...assistant import (
    MAX_HISTORY_INPUT_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_QUESTION_CHARS,
    MAX_SCOPE_CHARS,
    MAX_SCOPE_REPORTS,
    AssistantError,
    AssistantQuery,
    AssistantRuntime,
    AssistantScope,
    AssistantTurn,
)
from .common import RouteDeps, ok

TAG = "assistant"


class AssistantTurnInput(BaseModel):
    """One previous browser-local chat turn."""

    role: Literal["user", "assistant"]
    # Wider than the prompt clip on purpose: the browser replays the model's own previous
    # answer, which is capped at 64 KiB. The prompt builder trims each turn to
    # MAX_HISTORY_CHARS, so a long replay costs nothing but must not fail the request.
    content: Annotated[str, Field(min_length=1, max_length=MAX_HISTORY_INPUT_CHARS)]


class AssistantScopeInput(BaseModel):
    """Current dashboard filters and selected report ids."""

    dag_id: Annotated[str | None, Field(max_length=MAX_SCOPE_CHARS)] = None
    task_id: Annotated[str | None, Field(max_length=MAX_SCOPE_CHARS)] = None
    run_id: Annotated[str | None, Field(max_length=MAX_SCOPE_CHARS)] = None
    report_ids: list[Annotated[str, Field(min_length=1, max_length=4096)]] = Field(
        default_factory=list, max_length=MAX_SCOPE_REPORTS
    )


class AssistantQueryInput(BaseModel):
    """One bounded, non-persistent question."""

    question: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS)]
    scope: AssistantScopeInput = Field(default_factory=AssistantScopeInput)
    history: list[AssistantTurnInput] = Field(
        default_factory=list, max_length=MAX_HISTORY_MESSAGES
    )


_EX_STATUS = {
    "enabled": True,
    "provider": "anthropic",
    "model": "claude-sonnet-5",
    "context_model": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
    "context_mode": "local-full-tree",
    "storage_namespace": "8f4a55c1f15bf810ae9b8a9d",
    "reason": None,
    "max_question_chars": MAX_QUESTION_CHARS,
    "max_history_messages": MAX_HISTORY_MESSAGES,
    "max_history_chars": 4_000,
    "max_history_bytes": 16_000,
    "max_scope_reports": MAX_SCOPE_REPORTS,
    "direct_max_summaries": 100,
    "direct_max_detail_reports": None,
    "direct_max_failures_per_report": None,
    "max_context_bytes": 49_152,
    "max_output_tokens": 3_072,
    "max_failure_bytes": 3_072,
    "max_capture_bytes": 2_048,
    "local_complete_tree": True,
    "local_input_bytes": 9_000,
}
_EX_REPLY = {
    "answer": "The latest run introduced two assertion failures [R1].",
    "evidence": [
        {
            "key": "R1",
            "report_id": "opaque-report-token",
            "dag_id": "etl_daily",
            "run_id": "scheduled__2026-08-01",
            "task_id": "unit_tests",
            "created_at": "2026-08-01T08:00:00+00:00",
        }
    ],
    "provider": "anthropic",
    "model": "claude-sonnet-5",
    "context_model": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
    "reports_considered": 30,
    "truncated": False,
    "context_limited": False,
    "output_limited": False,
    "scope": "dag~etl_daily · task~unit_tests",
    "provider_input_bytes": 32_768,
    "prompt_bytes": {
        "system": 2_800,
        "user": 48,
        "context": 28_000,
        "history": 1_500,
        "structure": 420,
        "total": 32_768,
    },
    "token_usage": {
        "input_tokens": 8_240,
        "output_tokens": 312,
        "total_tokens": 8_552,
        "cached_input_tokens": 0,
    },
    "report_context": {
        "content": (
            "Scope: dag~etl_daily\n\n"
            'RUN SUMMARIES\n[R1] {"total":8,"passed":6,"failed":2}'
        ),
        "format": "direct-snapshot-jsonl",
        "bytes": 74,
    },
}


def _next_event(
    events: Iterator[tuple[str, dict[str, Any]]],
) -> tuple[str, dict[str, Any]] | None:
    """Pull one event, or ``None`` when the runtime generator is done."""
    return next(events, None)


def _sse(event: str, payload: dict[str, Any]) -> bytes:
    """Render one Server-Sent Event.

    ``json.dumps`` cannot emit a raw newline inside a string, so a single ``data:`` line is
    always enough and no answer text can forge an event boundary.
    """
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n".encode()


def build_router(deps: RouteDeps, runtime: AssistantRuntime) -> APIRouter:
    """Routes tagged ``assistant`` over the app's injected collaborators."""
    router = APIRouter(tags=[TAG])

    @router.get(
        "/api/assistant/status",
        summary="Report assistant status",
        responses=ok(_EX_STATUS),
    )
    def status(
        user: Any = Depends(deps.user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Configuration readiness without loading or calling either model."""
        body = runtime.status()
        body["storage_namespace"] = _storage_namespace(user)
        return JSONResponse(body)

    @router.post(
        "/api/assistant/query",
        summary="Ask about readable reports",
        responses={
            **ok(_EX_REPLY),
            400: {"description": "Malformed report scope."},
            403: {"description": "A selected report belongs to a forbidden DAG."},
            429: {"description": "The bounded assistant worker is busy."},
            502: {"description": "A local or remote model failed."},
            503: {"description": "The assistant is disabled or incomplete."},
        },
    )
    def query(
        body: AssistantQueryInput,
        user: Any = Depends(deps.user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Answer from reports the current user may read.

        The request is read-only. Dashboard filters and selected report ids define the
        scope, but every report is authorized again on the server. With a local reducer the
        complete scope is processed in chunks; direct mode uses a bounded snapshot. Chat
        history is supplied by the browser and is never persisted by the plugin.
        """
        try:
            reply = runtime.ask(
                source=deps.src,
                can_read=deps.read_auth,
                user=user,
                query=_query(body),
            )
        except AssistantError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(reply.to_dict())

    @router.post(
        "/api/assistant/stream",
        summary="Ask about readable reports, streamed",
        responses={
            200: {
                "description": (
                    "Server-Sent Events: one `meta` event with the exact provider input, "
                    "then `delta` events carrying answer fragments, then one `done` event "
                    "with evidence and token usage. A failure after the stream has started "
                    "arrives as an `error` event."
                ),
                "content": {"text/event-stream": {}},
            },
            400: {"description": "Malformed report scope."},
            403: {"description": "A selected report belongs to a forbidden DAG."},
            429: {"description": "The bounded assistant worker is busy."},
            502: {"description": "A local or remote model failed."},
            503: {"description": "The assistant is disabled or incomplete."},
        },
    )
    async def stream(
        body: AssistantQueryInput,
        user: Any = Depends(deps.user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> StreamingResponse:
        """Answer as the model writes, over the same RBAC and limits as ``/query``.

        Everything expensive -- RBAC filtering, redaction, local reduction -- happens before
        the first byte is sent, so a rejected request is still an ordinary HTTP error rather
        than a half-written stream.
        """
        events = runtime.stream(
            source=deps.src,
            can_read=deps.read_auth,
            user=user,
            query=_query(body),
        )
        try:
            first = await run_in_threadpool(_next_event, events)
        except AssistantError as exc:
            await run_in_threadpool(events.close)
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        async def body_iterator() -> AsyncIterator[bytes]:
            # Deliberately an async generator. A sync one would be pulled through a
            # worker thread, and cancelling that await cannot interrupt the thread -- the
            # generator would simply be dropped and its cleanup deferred to garbage
            # collection, leaving the single model slot held long after the browser
            # pressed Stop. Cancellation lands inside an async generator, so ``finally``
            # runs at once and the slot is freed.
            try:
                yield _sse(*(first or ("done", {})))
                while True:
                    item = await run_in_threadpool(_next_event, events)
                    if item is None:
                        return
                    yield _sse(*item)
            except AssistantError as exc:
                yield _sse("error", {"detail": str(exc), "status": exc.status_code})
            finally:
                events.close()

        return StreamingResponse(
            body_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                # Proxies that buffer would defeat the point of streaming.
                "X-Accel-Buffering": "no",
            },
        )

    return router


def _query(body: AssistantQueryInput) -> AssistantQuery:
    scope = body.scope
    return AssistantQuery(
        question=body.question,
        scope=AssistantScope(
            dag_id=_clean(scope.dag_id),
            task_id=_clean(scope.task_id),
            run_id=_clean(scope.run_id),
            report_ids=tuple(scope.report_ids),
        ),
        history=tuple(
            AssistantTurn(role=turn.role, content=turn.content) for turn in body.history
        ),
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _storage_namespace(user: Any) -> str:
    """Return a stable opaque browser-history namespace for the current Airflow user."""
    if user is None:
        identity = "standalone"
    else:
        identity = None
        for attr in ("id", "user_id", "username", "name"):
            value = (
                user.get(attr)
                if isinstance(user, Mapping)
                else getattr(user, attr, None)
            )
            if value is not None and str(value).strip():
                identity = f"{attr}:{value}"
                break
        if identity is None:
            get_id = getattr(user, "get_id", None)
            value = get_id() if callable(get_id) else None
            if value is not None and str(value).strip():
                identity = f"get_id:{value}"
        if identity is None:
            # Do not let two users from an unfamiliar auth-manager user type share one
            # browser transcript. The safe fallback sacrifices refresh persistence for
            # that type instead of risking cross-account history restoration.
            identity = f"unidentified:{secrets.token_hex(16)}"
    payload = f"airflow-pytest-plugin:assistant:{identity}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]
