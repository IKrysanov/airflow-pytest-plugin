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

"""Failures route — failed/errored cases across the visible runs, flat or clustered."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .common import RouteDeps, ok

TAG = "failures"

#: Upper bound on failed cases returned, to keep the payload bounded.
_FAILURES_CAP = 5000
#: Cap on failing tests listed under a single cluster (the count is still exact).
_CLUSTER_TESTS_CAP = 200

# Volatile bits scrubbed from an error message so messages that differ only by run
# specifics collapse to one signature. Order matters: UUID before the generic digit
# rule (a UUID is mostly digits), hex addresses before digits too.
_RE_UUID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
_RE_HEX = re.compile(r"0x[0-9a-fA-F]+")
_RE_NUM = re.compile(r"\d+")
_RE_WS = re.compile(r"\s+")


def _error_line(message: str | None) -> str:
    """First meaningful line of a case message (skips our ``--- section ---`` headers)."""
    for line in (message or "").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("---"):
            return stripped
    return (message or "").strip()


def normalize_error(message: str | None) -> str:
    """A stable signature for an error message: its first line with volatile bits masked.

    Strips UUIDs, hex addresses and numbers (and collapses whitespace) so that
    ``expected 5 got 7`` and ``expected 8 got 3`` share the signature
    ``expected N got N``. Capped to keep signatures comparable and bounded.
    """
    line = _error_line(message)
    line = _RE_UUID.sub("UUID", line)
    line = _RE_HEX.sub(
        "ADDR", line
    )  # digit-free placeholder so the number rule won't touch it
    line = _RE_NUM.sub("N", line)
    return _RE_WS.sub(" ", line).strip()[:200]


def cluster_failures(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group failing cases by normalized message (pure), most common cluster first.

    Each cluster carries the ``signature``, an exact ``count``, the ``outcomes`` seen,
    a representative raw ``sample`` line, and the (capped) list of failing ``tests``.
    """
    clusters: dict[str, dict[str, Any]] = {}
    for it in items:
        sig = normalize_error(it.get("message"))
        c = clusters.get(sig)
        if c is None:
            c = clusters[sig] = {
                "signature": sig,
                "count": 0,
                "sample": _error_line(it.get("message")),
                "outcomes": set(),
                "tests": [],
            }
        c["count"] += 1
        c["outcomes"].add(it["outcome"])
        if len(c["tests"]) < _CLUSTER_TESTS_CAP:
            c["tests"].append(
                {
                    k: it[k]
                    for k in (
                        "id",
                        "dag_id",
                        "task_id",
                        "run_id",
                        "created_at",
                        "node_id",
                        "outcome",
                    )
                }
            )
    out = [{**c, "outcomes": sorted(c["outcomes"])} for c in clusters.values()]
    out.sort(key=lambda c: (-c["count"], c["signature"]))
    return out


def _collect_failures(
    deps: RouteDeps,
    user: Any,
    *,
    dag_id: str | None,
    run_id: str | None,
    task_q: str,
    latest: bool,
    with_message: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """Collect failed/errored cases across readable runs (newest first).

    When ``latest`` (the default for the views), only each **dag·task's** newest readable
    run is considered — that's the pipeline's current state across all of its run_ids, so
    a fixed test drops off once its next run is green and the list reflects *current*
    breakage rather than every failure ever archived (older run_ids are history). Runs are
    deduped per (dag_id, task_id); a retry wins its run via the scan's created_at/
    try_number ordering. ``latest=False`` walks the full history. Returns ``(items, capped)``.
    """
    src, read_auth = deps.src, deps.read_auth
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    capped = False
    for s in src.list_summaries(dag_id=dag_id, run_id=run_id):  # newest first
        if task_q and task_q not in s.ref.task_id.lower():
            continue
        if not read_auth(s.ref.dag_id, user):
            continue
        key = (s.ref.dag_id, s.ref.task_id)
        if latest:
            if key in seen:  # an older run of a group whose newest we already passed
                continue
            seen.add(
                key
            )  # mark before the green check, so a green newest hides old fails
        if (s.failed + s.errors) <= 0:
            continue
        detail = src.get_detail(s.ref)
        if detail is None:
            continue
        for c in detail.cases:
            if c.outcome not in ("failed", "error"):
                continue
            item = {
                "id": s.ref.token,
                "dag_id": s.ref.dag_id,
                "task_id": s.ref.task_id,
                "run_id": s.ref.run_id,
                "created_at": s.created_at,
                "node_id": c.node_id,
                "outcome": c.outcome,
            }
            if with_message:
                item["message"] = c.message
            items.append(item)
            if len(items) >= _FAILURES_CAP:  # stop mid-run, don't over-read one big run
                capped = True
                break
        if capped:
            break
    return items[:_FAILURES_CAP], capped


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``failures``."""
    router = APIRouter(tags=[TAG])
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
        latest: bool = True,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Currently-failing cases (one flat list), newest run first.

        By default only each dag·task's **latest** readable run is considered, so a
        fixed test drops off once its next run is green — the list reflects what's broken
        *now* and shrinks as code improves. Pass ``latest=0`` for the full history.
        Filters mirror the run list (``dag_id`` / ``run_id`` / ``task_id``); RBAC; capped
        at ``5000`` (``capped`` flags truncation).
        """
        items, capped = _collect_failures(
            deps,
            user,
            dag_id=dag_id,
            run_id=run_id,
            task_q=(task_id or "").lower(),
            latest=latest,
            with_message=False,
        )
        return JSONResponse({"failures": items, "total": len(items), "capped": capped})

    @router.get(
        "/api/failure-clusters",
        summary="Failures grouped by error",
        responses=ok(
            {
                "clusters": [
                    {
                        "signature": "AssertionError: expected N got N",
                        "count": 12,
                        "sample": "AssertionError: expected 5 got 7",
                        "outcomes": ["failed"],
                        "tests": [
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
                    }
                ],
                "total": 12,
                "capped": False,
            }
        ),
    )
    def failure_clusters(
        dag_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        latest: bool = True,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Currently-failing cases grouped by a normalized error signature, biggest first.

        Same scan/filters/RBAC/cap as ``/api/failures``, and likewise defaults to each
        dag·task's **latest** run (``latest=0`` for full history) — so clusters reflect
        what's broken now and shrink as tests are fixed. Instead of a flat list it
        returns clusters, so common root causes surface instead of per-failure spam; each
        has an exact ``count``, a representative ``sample`` message, and the (capped)
        failing ``tests``. Scope to one ``run_id`` for the in-run view.
        """
        items, capped = _collect_failures(
            deps,
            user,
            dag_id=dag_id,
            run_id=run_id,
            task_q=(task_id or "").lower(),
            latest=latest,
            with_message=True,
        )
        return JSONResponse(
            {"clusters": cluster_failures(items), "total": len(items), "capped": capped}
        )

    return router
