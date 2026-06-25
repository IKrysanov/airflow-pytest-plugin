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

from .common import RouteDeps, ref_from_token

TAG = "reports"

#: Cap on how many (newest) runs /api/unique-tests reads per-test maps from, so the
#: KPI can't trigger an unbounded scan of every archived run on each filter change.
_UNIQUE_SCAN_CAP = 1000


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``reports``."""
    router = APIRouter(tags=[TAG])
    src = deps.src
    read_auth = deps.read_auth
    delete_auth = deps.delete_auth
    user_dep = deps.user_dep

    @router.get("/api/reports", summary="List runs")
    def list_reports(
        dag_id: str | None = None,
        run_id: str | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Run summaries, newest first.

        Each entry carries the pass/fail/skip/error counts, duration, identity
        (dag·run·task·try) and its opaque token. Optional ``dag_id`` / ``run_id``
        narrow by case-insensitive substring. Only runs the caller may read are
        returned (RBAC).
        """
        summaries = src.list_summaries(dag_id=dag_id, run_id=run_id)
        visible = [s for s in summaries if read_auth(s.ref.dag_id, user)]
        return JSONResponse({"reports": [s.to_dict() for s in visible]})

    @router.get("/api/reports/{report_id}", summary="Get a run")
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

    @router.delete("/api/reports/{report_id}", summary="Delete a run")
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
        "/api/reports/{report_id}/allure.zip", summary="Download Allure results"
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

    @router.get("/api/test-history", summary="Test history")
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

    @router.get("/api/unique-tests", summary="Unique tests")
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
