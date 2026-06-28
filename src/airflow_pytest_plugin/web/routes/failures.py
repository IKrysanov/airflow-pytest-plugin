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

"""Failures route — failed/errored cases across the visible runs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .common import RouteDeps, ok

TAG = "failures"

#: Upper bound on failed cases returned, to keep the payload bounded.
_FAILURES_CAP = 5000


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``failures``."""
    router = APIRouter(tags=[TAG])
    src = deps.src
    read_auth = deps.read_auth
    user_dep = deps.user_dep

    @router.get(
        "/api/failures",
        summary="Failed cases across runs",
        responses=ok(
            {
                "failures": [
                    {
                        "id": "YXBpX2dhdGV3YXl8...",
                        "dag_id": "api_gateway",
                        "task_id": "integration_tests",
                        "run_id": "scheduled__2026-06-20",
                        "created_at": "2026-06-20T07:00:00+00:00",
                        "node_id": "tests/api.py::test_auth",
                        "outcome": "failed",
                    }
                ],
                "total": 1,
                "capped": False,
            }
        ),
    )
    def failures(
        dag_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Every failed or errored case across the visible runs, newest run first.

        A flat list (each item names its run + node_id + outcome) that the client
        paginates; filters mirror the run list (``dag_id`` / ``run_id`` /
        ``task_id``). Only readable runs are scanned (RBAC). Capped at ``5000`` —
        ``capped`` flags truncation.
        """
        task_q = (task_id or "").lower()
        items: list[dict[str, Any]] = []
        capped = False
        for s in src.list_summaries(dag_id=dag_id, run_id=run_id):
            if task_q and task_q not in s.ref.task_id.lower():
                continue
            if (s.failed + s.errors) <= 0 or not read_auth(s.ref.dag_id, user):
                continue
            detail = src.get_detail(s.ref)
            if detail is None:
                continue
            for c in detail.cases:
                if c.outcome not in ("failed", "error"):
                    continue
                items.append(
                    {
                        "id": s.ref.token,
                        "dag_id": s.ref.dag_id,
                        "task_id": s.ref.task_id,
                        "run_id": s.ref.run_id,
                        "created_at": s.created_at,
                        "node_id": c.node_id,
                        "outcome": c.outcome,
                    }
                )
            if len(items) >= _FAILURES_CAP:
                capped = True
                break
        return JSONResponse(
            {
                "failures": items[:_FAILURES_CAP],
                "total": len(items[:_FAILURES_CAP]),
                "capped": capped,
            }
        )

    return router
