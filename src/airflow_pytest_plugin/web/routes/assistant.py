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
import secrets
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...assistant import (
    MAX_HISTORY_CHARS,
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
    content: Annotated[str, Field(min_length=1, max_length=MAX_HISTORY_CHARS)]


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
    "max_scope_reports": MAX_SCOPE_REPORTS,
    "direct_max_summaries": 100,
    "direct_max_detail_reports": None,
    "direct_max_failures_per_report": None,
    "max_context_bytes": 49_152,
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
}


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
        scope = body.scope
        request = AssistantQuery(
            question=body.question,
            scope=AssistantScope(
                dag_id=_clean(scope.dag_id),
                task_id=_clean(scope.task_id),
                run_id=_clean(scope.run_id),
                report_ids=tuple(scope.report_ids),
            ),
            history=tuple(
                AssistantTurn(role=turn.role, content=turn.content)
                for turn in body.history
            ),
        )
        try:
            reply = runtime.ask(
                source=deps.src,
                can_read=deps.read_auth,
                user=user,
                query=request,
            )
        except AssistantError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(reply.to_dict())

    return router


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
