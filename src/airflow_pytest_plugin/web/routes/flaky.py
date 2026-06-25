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

"""Flaky route — tests that both pass and fail across recent runs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .common import FAIL_OUTCOMES, RouteDeps

TAG = "flaky"

#: Upper bound on flaky tests returned.
_FLAKY_CAP = 1000

#: How many recent outcomes to include in a flaky test's strip (keeps the UI tidy).
_FLAKY_STRIP = 10


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``flaky``."""
    router = APIRouter(tags=[TAG])
    src = deps.src
    read_auth = deps.read_auth
    user_dep = deps.user_dep

    @router.get("/api/flaky", summary="Flaky tests")
    def flaky(
        dag_id: str | None = None,
        task_id: str | None = None,
        window: int = 30,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Tests that BOTH pass and fail within the last ``window`` runs of a dag·task.

        Groups the visible runs by dag·task, looks at the most recent ``window``
        (clamped 2–200) of each, and reports every test that shows both a pass and a
        failure/error there. Per test: ``runs`` seen, ``fails`` count, pass↔fail
        ``flips``, and a ``recent`` outcome strip (last 10). Sorted flakiest-first;
        capped at ``1000`` (``capped`` flags truncation).
        """
        win = max(2, min(window, 200))
        task_q = (task_id or "").lower()
        groups: dict[tuple[str, str], list[Any]] = {}
        for s in src.list_summaries(dag_id=dag_id):
            if task_q and task_q not in s.ref.task_id.lower():
                continue
            if not read_auth(s.ref.dag_id, user):
                continue
            groups.setdefault((s.ref.dag_id, s.ref.task_id), []).append(s)

        items: list[dict[str, Any]] = []
        for (dag, task), summaries in groups.items():
            summaries.sort(key=lambda s: s.created_at or "", reverse=True)
            window_runs = summaries[:win]
            if len(window_runs) < 2:
                continue
            seqs: dict[str, list[str]] = {}
            for s in reversed(window_runs):  # oldest -> newest
                for node, info in (src.test_outcomes(s.ref) or {}).items():
                    seqs.setdefault(node, []).append(info["outcome"])
            for node, seq in seqs.items():
                fails = sum(1 for o in seq if o in FAIL_OUTCOMES)
                if fails and any(o == "passed" for o in seq):  # flaky: both seen
                    flips = sum(
                        1
                        for a, b in zip(seq, seq[1:], strict=False)
                        if (a in FAIL_OUTCOMES) != (b in FAIL_OUTCOMES)
                    )
                    items.append(
                        {
                            "dag_id": dag,
                            "task_id": task,
                            "node_id": node,
                            "runs": len(seq),
                            "fails": fails,
                            "flips": flips,
                            "recent": seq[-_FLAKY_STRIP:],
                        }
                    )
        items.sort(key=lambda x: (-x["flips"], -x["fails"], x["node_id"]))
        return JSONResponse(
            {
                "flaky": items[:_FLAKY_CAP],
                "total": min(len(items), _FLAKY_CAP),
                "capped": len(items) > _FLAKY_CAP,
                "window": win,
            }
        )

    return router
