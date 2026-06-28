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

"""Report routes — browse runs, per-test detail, history, and the test catalogue."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response

from ...config import get_success_threshold
from .common import ERR_400, ERR_403, ERR_404, RouteDeps, ok, ref_from_token

TAG = "reports"

#: Cap on how many (newest) runs /api/unique-tests reads per-test maps from, so the
#: KPI can't trigger an unbounded scan of every archived run on each filter change.
_UNIQUE_SCAN_CAP = 1000

# -- OpenAPI examples (illustrative; Swagger shows these instead of a bare "string") --
_EX_SUMMARY = {
    "id": "ZXRsX2RhaWx5fHNjaGVkdWxlZF8yMDI2LTA2LTEwfHVuaXRfdGVzdHN8MXwtMQ",
    "dag_id": "etl_daily",
    "run_id": "scheduled__2026-06-10",
    "task_id": "unit_tests",
    "try_number": 1,
    "map_index": -1,
    "total": 4,
    "passed": 3,
    "failed": 1,
    "skipped": 0,
    "errors": 0,
    "duration": 1.2,
    "success": False,
    "created_at": "2026-06-10T23:00:00+00:00",
    "logical_date": None,
    "has_allure": False,
}
_EX_CASE = {
    "node_id": "tests/test_etl.py::test_load",
    "name": "test_load",
    "classname": "tests/test_etl.py",
    "outcome": "failed",
    "time": 0.3,
    "message": "AssertionError: row count mismatch",
}
_EX_GROUP = {
    "dag_id": "api_gateway",
    "task_id": "integration_tests",
    "runs": 8,
    "passed": 2,
    "pass_rate": 0.25,
    "avg_duration": 1.6,
    "last_status": "failed",
    "last_created_at": "2026-06-20T07:00:00+00:00",
}


def summarize_groups(summaries: list[Any]) -> list[dict[str, Any]]:
    """Aggregate run summaries by dag·task (pure).

    One entry per dag·task with the run count, how many passed (per the configured
    success threshold), the pass rate, the average run duration, and the newest run's
    status/time. Sorted by most-recent activity. Lets a grouped view or dashboard read
    group stats without shipping every run -- the basis for scaling past in-browser
    grouping.
    """
    order: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], list[Any]] = {}
    for s in summaries:
        key = (s.ref.dag_id, s.ref.task_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(s)

    out: list[dict[str, Any]] = []
    for dag, task in order:
        runs = groups[(dag, task)]
        newest = max(runs, key=lambda s: s.created_at or "")
        passed = sum(1 for s in runs if s.success)
        last = "passed" if newest.success else ("error" if newest.errors else "failed")
        out.append(
            {
                "dag_id": dag,
                "task_id": task,
                "runs": len(runs),
                "passed": passed,
                "pass_rate": round(passed / len(runs), 3),
                "avg_duration": round(sum(s.duration for s in runs) / len(runs), 3),
                "last_status": last,
                "last_created_at": newest.created_at,
            }
        )
    out.sort(key=lambda g: g["last_created_at"] or "", reverse=True)
    return out


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``reports``."""
    router = APIRouter(tags=[TAG])
    src = deps.src
    read_auth = deps.read_auth
    delete_auth = deps.delete_auth
    user_dep = deps.user_dep

    @router.get(
        "/api/reports",
        summary="List runs",
        responses=ok({"reports": [_EX_SUMMARY], "success_threshold": 0.85}),
    )
    def list_reports(
        dag_id: str | None = None,
        run_id: str | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Run summaries, newest first.

        Each entry carries the pass/fail/skip/error counts, duration, identity
        (dag·run·task·try) and its opaque token. Optional ``dag_id`` / ``run_id``
        narrow by case-insensitive substring. Only runs the caller may read are
        returned (RBAC). ``success_threshold`` echoes the configured pass-rate bar
        (0–1) so the UI can draw it on the chart.
        """
        summaries = src.list_summaries(dag_id=dag_id, run_id=run_id)
        visible = [s for s in summaries if read_auth(s.ref.dag_id, user)]
        return JSONResponse(
            {
                "reports": [s.to_dict() for s in visible],
                "success_threshold": get_success_threshold(),
            }
        )

    @router.get(
        "/api/groups",
        summary="Run groups by dag·task",
        responses=ok({"groups": [_EX_GROUP], "total": 1}),
    )
    def groups(
        dag_id: str | None = None,
        task_id: str | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Runs aggregated by dag·task: count, pass-rate, and the newest run's
        status/time. Optional ``dag_id`` / ``task_id`` narrow by case-insensitive
        substring; RBAC-filtered. Built for grouped views and dashboards so they can
        show group stats without fetching every run (scales past in-browser grouping).
        """
        task_q = (task_id or "").lower()
        visible = [
            s
            for s in src.list_summaries(dag_id=dag_id)
            if (not task_q or task_q in s.ref.task_id.lower())
            and read_auth(s.ref.dag_id, user)
        ]
        items = summarize_groups(visible)
        return JSONResponse({"groups": items, "total": len(items)})

    @router.get(
        "/api/reports/{report_id}",
        summary="Get a run",
        responses={
            **ok({**_EX_SUMMARY, "cases": [_EX_CASE]}),
            **ERR_400,
            **ERR_403,
            **ERR_404,
        },
    )
    def get_report(
        report_id: str,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Full detail for one run, addressed by its opaque ``report_id`` token.

        Includes every case's outcome, duration and captured output. ``400`` if the
        token is malformed, ``403`` if the dag isn't readable, ``404`` if missing.
        """
        ref = ref_from_token(report_id)
        if not read_auth(ref.dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read this report"
            )
        detail = src.get_detail(ref)
        if detail is None:
            raise HTTPException(status_code=404, detail="report not found")
        return JSONResponse(detail.to_dict())

    @router.delete(
        "/api/reports/{report_id}",
        summary="Delete a run",
        responses={**ok({"deleted": True}), **ERR_400, **ERR_403, **ERR_404},
    )
    def delete_report(
        report_id: str,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Permanently delete one archived run and prune now-empty parent dirs.

        Destructive: requires permission to **trigger** the run's DAG (RBAC),
        not just read it. ``400`` on a bad token, ``403`` if not permitted, ``404``
        if the run is already gone.
        """
        ref = ref_from_token(report_id)
        if not delete_auth(ref.dag_id, user):
            raise HTTPException(
                status_code=403,
                detail="deleting a report requires permission to trigger its DAG",
            )
        if not src.delete(ref):
            raise HTTPException(status_code=404, detail="report not found")
        return JSONResponse({"deleted": True})

    @router.get(
        "/api/reports/{report_id}/allure.zip",
        summary="Download Allure results",
        responses={
            200: {
                "description": "Allure results archive.",
                "content": {"application/zip": {}},
            },
            **ERR_400,
            **ERR_403,
            **ERR_404,
        },
    )
    def allure_zip(
        report_id: str,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> Response:
        """The run's raw Allure results as a zip attachment.

        Present only when the run was archived with ``ArchivingResultParser(allure=
        True)``. ``400``/``403`` as for the detail; ``404`` when no Allure results
        were captured.
        """
        ref = ref_from_token(report_id)
        if not read_auth(ref.dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read this report"
            )
        data = src.allure_archive(ref)
        if data is None:
            raise HTTPException(status_code=404, detail="no Allure results")
        return Response(
            data,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="allure-results.zip"'
            },
        )

    @router.get(
        "/api/test-history",
        summary="Test history",
        responses={
            **ok(
                {
                    "node_id": "tests/test_etl.py::test_load",
                    "dag_id": "etl_daily",
                    "task_id": "unit_tests",
                    "history": [
                        {
                            "run_id": "scheduled__2026-06-13",
                            "created_at": "2026-06-13T23:00:00+00:00",
                            "outcome": "passed",
                            "duration": 0.3,
                        },
                        {
                            "run_id": "scheduled__2026-06-12",
                            "created_at": "2026-06-12T23:00:00+00:00",
                            "outcome": "failed",
                            "duration": 0.31,
                        },
                    ],
                }
            ),
            **ERR_403,
        },
    )
    def test_history(
        dag_id: str,
        task_id: str,
        node_id: str,
        limit: int = 50,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """One test's outcome and duration across the runs of an exact dag·task.

        ``node_id`` is the pytest node id (``file::Class::test``). Returns the
        newest ``limit`` runs (clamped 1–500), each with the test's outcome and
        duration (``null`` if it didn't run that time). ``403`` if the dag isn't
        readable.
        """
        if not read_auth(dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read this dag"
            )
        lim = max(1, min(limit, 500))
        runs = [
            s
            for s in src.list_summaries(dag_id=dag_id)
            if s.ref.dag_id == dag_id and s.ref.task_id == task_id
        ]
        runs.sort(key=lambda s: s.created_at or "", reverse=True)
        history: list[dict[str, Any]] = []
        for s in runs[:lim]:
            info = (src.test_outcomes(s.ref) or {}).get(node_id)
            history.append(
                {
                    "run_id": s.ref.run_id,
                    "created_at": s.created_at,
                    "outcome": info["outcome"] if info else None,
                    "duration": info["duration"] if info else None,
                }
            )
        return JSONResponse(
            {
                "node_id": node_id,
                "dag_id": dag_id,
                "task_id": task_id,
                "history": history,
            }
        )

    @router.get(
        "/api/unique-tests",
        summary="Unique tests",
        responses=ok(
            {
                "count": 189,
                "capped": False,
                "tests": [
                    {
                        "node_id": "tests/test_etl.py::test_load",
                        "dag_id": "etl_daily",
                        "task_id": "unit_tests",
                    },
                ],
            }
        ),
    )
    def unique_tests(
        dag_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        full: bool = False,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Distinct test node_ids across the visible (readable) runs, with a count.

        Powers the *Unique tests* KPI. Reads at most the ``1000`` newest runs so the
        count stays cheap (``capped`` flags truncation). The body carries the full,
        sorted catalogue (each test with a representative dag·task) only when
        ``full`` is set — i.e. when the user actually opens the list.
        """
        task_q = (task_id or "").lower()
        seen: dict[str, tuple[str, str]] = {}  # node_id -> (dag, task) first seen
        scanned = 0
        capped = False
        for s in src.list_summaries(dag_id=dag_id, run_id=run_id):  # newest first
            if task_q and task_q not in s.ref.task_id.lower():
                continue
            if not read_auth(s.ref.dag_id, user):
                continue
            if scanned >= _UNIQUE_SCAN_CAP:
                capped = True
                break
            scanned += 1
            for node in src.test_outcomes(s.ref) or {}:
                seen.setdefault(node, (s.ref.dag_id, s.ref.task_id))
        body: dict[str, Any] = {"count": len(seen), "capped": capped}
        if full:
            body["tests"] = [
                {"node_id": n, "dag_id": d, "task_id": ta}
                for n, (d, ta) in sorted(seen.items())
            ]
        return JSONResponse(body)

    return router
