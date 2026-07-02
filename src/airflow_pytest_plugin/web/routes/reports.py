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

from ...config import (
    get_flaky_window,
    get_slow_factor,
    get_slow_min_delta,
    get_success_threshold,
)
from .common import ERR_400, ERR_403, ERR_404, RouteDeps, ok, ref_from_token

TAG = "reports"

#: Cap on how many (newest) runs /api/unique-tests reads per-test maps from, so the
#: KPI can't trigger an unbounded scan of every archived run on each filter change.
_UNIQUE_SCAN_CAP = 1000

#: Caps on /api/slow output: regressions list and the slowest leaderboard.
_SLOW_CAP = 1000
_SLOW_TOP = 50
#: Safety cap on how many run-meta files /api/slow reads per request (whole groups are
#: skipped once exceeded; ``capped`` flags it), so a broad scan can't read every archive.
_SLOW_SCAN_CAP = 2000

#: /api/heatmap bounds: at most this many recent runs (columns) and tests (rows) per
#: request, so one dag·task's matrix can't blow up the payload or the read.
_HEATMAP_MAX_WINDOW = 100
_HEATMAP_MAX_ROWS = 300

#: Compact single-char cell codes for the heatmap (missing run -> "-").
_OUTCOME_CODE = {"passed": "p", "failed": "f", "error": "e", "skipped": "s"}
_FAIL_CODES = ("f", "e")

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
_EX_SLOW = {
    "dag_id": "api_gateway",
    "task_id": "integration_tests",
    "node_id": "tests/api.py::test_bulk_import",
    "runs": 8,
    "avg": 4.1,
    "last": 6.2,
    "old_avg": 2.0,
    "new_avg": 6.1,
    "ratio": 3.05,
    "regressed": True,
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


def slow_stats(
    durations: list[float], *, factor: float, min_delta: float
) -> dict[str, Any]:
    """Duration stats for one test's run history (oldest→newest), pure.

    Always reports ``avg`` and ``last`` so the caller can rank the slowest tests. A
    test counts as a regression (``regressed``) only with at least four runs, when the
    recent half's average duration is both ``factor``× the older half's AND at least
    ``min_delta`` seconds slower — the absolute floor keeps fast tests with jittery
    ratios off the list. ``ratio`` is recent÷older (``None`` until enough runs, or when
    the older half averaged 0 — an "appeared from nothing" jump). ``durations`` holds
    only the runs where the test actually appeared, so the split-half compares the test
    to itself; an intermittently-run test is split over appearances, not calendar slots.
    """
    n = len(durations)
    avg = sum(durations) / n if n else 0.0
    last = durations[-1] if n else 0.0
    old_avg: float | None = None
    new_avg: float | None = None
    ratio: float | None = None
    regressed = False
    if n >= 4:
        mid = n // 2
        older, newer = durations[:mid], durations[mid:]
        old_avg = sum(older) / len(older)
        new_avg = sum(newer) / len(newer)
        if old_avg > 0:
            ratio = round(new_avg / old_avg, 2)
        regressed = new_avg >= old_avg * factor and (new_avg - old_avg) >= min_delta
    return {
        "runs": n,
        "avg": round(avg, 3),
        "last": round(last, 3),
        "old_avg": round(old_avg, 3) if old_avg is not None else None,
        "new_avg": round(new_avg, 3) if new_avg is not None else None,
        "ratio": ratio,
        "regressed": regressed,
    }


def build_heatmap(
    runs: list[dict[str, Any]], *, max_rows: int = _HEATMAP_MAX_ROWS
) -> dict[str, Any]:
    """Build a test×run outcome matrix (pure) from a dag·task's runs (oldest→newest).

    ``runs`` items are ``{"run_id", "created_at", "outcomes": {node_id: outcome}}``. Returns
    one row per distinct test — a ``cells`` list of single-char codes aligned to ``runs``
    (``-`` where the test didn't run) — sorted most-broken first (fail+error count, then
    flakiness/flips), capped at ``max_rows`` (``truncated`` flags it). The most-failing and
    flakiest tests bubble to the top so a regression block or a flaky row is seen at a glance.
    """
    n = len(runs)
    rows: dict[str, list[str]] = {}
    for ci, r in enumerate(runs):
        for node, outcome in (r.get("outcomes") or {}).items():
            row = rows.setdefault(node, ["-"] * n)
            row[ci] = _OUTCOME_CODE.get(str(outcome), "?")

    def rank(codes: list[str]) -> tuple[int, int]:
        bad = sum(1 for c in codes if c in _FAIL_CODES)
        present = [c for c in codes if c != "-"]
        flips = sum(
            1
            for a, b in zip(present, present[1:], strict=False)
            if (a in _FAIL_CODES) != (b in _FAIL_CODES)
        )
        return (bad, flips)

    ranked = {node: rank(codes) for node, codes in rows.items()}
    ordered = sorted(
        rows.items(), key=lambda kv: (-ranked[kv[0]][0], -ranked[kv[0]][1], kv[0])
    )
    truncated = len(ordered) > max_rows
    tests = [{"node_id": node, "cells": cells} for node, cells in ordered[:max_rows]]
    return {
        "runs": [
            {"run_id": r["run_id"], "created_at": r.get("created_at")} for r in runs
        ],
        "tests": tests,
        "total_tests": len(rows),
        "truncated": truncated,
    }


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
        "/api/slow",
        summary="Slow tests & duration regressions",
        responses=ok(
            {
                "regressed": [_EX_SLOW],
                "slowest": [_EX_SLOW],
                "total_regressed": 1,
                "capped": False,
                "window": 30,
                "factor": 1.3,
                "min_delta": 0.5,
            }
        ),
    )
    def slow(
        dag_id: str | None = None,
        task_id: str | None = None,
        window: int | None = None,
        run_id: str | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Slowest tests and duration regressions across the last ``window`` runs.

        Groups readable runs by dag·task, takes each group's most recent ``window``
        (default = the flaky window; clamped 2–200), and per test builds a duration
        sequence. ``regressed`` lists tests that got slower (recent-half avg ≥
        ``factor``× the older half AND ≥ ``min_delta`` s), sorted worst-ratio first;
        ``slowest`` is the top ``50`` by average duration (single-run / zero-time tests
        are skipped so it means *reliably* slow). A test that speeds back up drops off
        ``regressed`` (its recent half is no longer slower). Optional ``dag_id`` /
        ``task_id`` / ``run_id`` narrow by substring (mirroring the run list);
        RBAC-filtered. At most ``2000`` run-meta files are read per request; ``capped``
        flags that some groups were skipped.
        """
        chosen = window if window is not None else get_flaky_window()
        win = max(2, min(chosen, 200))
        factor = get_slow_factor()
        min_delta = get_slow_min_delta()
        task_q = (task_id or "").lower()

        groups: dict[tuple[str, str], list[Any]] = {}
        for s in src.list_summaries(dag_id=dag_id, run_id=run_id):
            if task_q and task_q not in s.ref.task_id.lower():
                continue
            if not read_auth(s.ref.dag_id, user):
                continue
            groups.setdefault((s.ref.dag_id, s.ref.task_id), []).append(s)

        regressed: list[dict[str, Any]] = []
        slowest: list[dict[str, Any]] = []
        scanned = 0
        capped = False
        for (dag, task), summaries in groups.items():
            if scanned >= _SLOW_SCAN_CAP:  # skip whole groups past the read budget
                capped = True
                break
            summaries.sort(key=lambda s: s.created_at or "", reverse=True)
            window_runs = summaries[:win]
            scanned += len(window_runs)
            seqs: dict[str, list[float]] = {}
            for s in reversed(window_runs):  # oldest -> newest
                for node, info in (src.test_outcomes(s.ref) or {}).items():
                    seqs.setdefault(node, []).append(float(info.get("duration") or 0.0))
            for node, durs in seqs.items():
                stats = slow_stats(durs, factor=factor, min_delta=min_delta)
                item = {"dag_id": dag, "task_id": task, "node_id": node, **stats}
                if stats["regressed"]:
                    regressed.append(item)
                # Leaderboard wants reliably-slow tests: skip single-run / zero-time noise.
                if stats["runs"] >= 2 and stats["avg"] > 0:
                    slowest.append(item)

        def _ratio_key(x: dict[str, Any]) -> float:
            r = x["ratio"]  # None = was ~0s, now slow -> infinite increase, rank first
            return float("inf") if r is None else r

        regressed.sort(key=lambda x: (-_ratio_key(x), -(x["new_avg"] or 0)))
        slowest.sort(key=lambda x: (-x["avg"], x["node_id"]))
        return JSONResponse(
            {
                "regressed": regressed[:_SLOW_CAP],
                "slowest": slowest[:_SLOW_TOP],
                "total_regressed": len(regressed),
                "capped": capped,
                "window": win,
                "factor": factor,
                "min_delta": min_delta,
            }
        )

    @router.get(
        "/api/heatmap",
        summary="Test×run outcome matrix",
        responses={
            **ok(
                {
                    "dag_id": "api_gateway",
                    "task_id": "integration_tests",
                    "window": 30,
                    "runs": [
                        {
                            "run_id": "scheduled__2026-06-20",
                            "created_at": "2026-06-20T07:00:00+00:00",
                        }
                    ],
                    "tests": [
                        {
                            "node_id": "tests/api.py::test_auth",
                            "cells": ["p", "f", "-", "e"],
                        }
                    ],
                    "total_tests": 1,
                    "truncated": False,
                }
            ),
            **ERR_403,
        },
    )
    def heatmap(
        dag_id: str,
        task_id: str,
        window: int | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """A test×run outcome matrix for one dag·task: rows = tests, columns = its recent
        runs (oldest→newest), each cell the test's outcome (``p``/``f``/``e``/``s``; ``-`` =
        didn't run that time). Rows are sorted most-broken first (fail+error count, then
        flakiness) so regression blocks and flaky tests surface at the top. ``window``
        defaults to the flaky window (clamped 2–``100``); rows are capped at ``300``
        (``truncated`` flags it). ``403`` if the dag isn't readable.
        """
        if not read_auth(dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read this dag"
            )
        chosen = window if window is not None else get_flaky_window()
        win = max(2, min(chosen, _HEATMAP_MAX_WINDOW))
        runs = [
            s
            for s in src.list_summaries(dag_id=dag_id)
            if s.ref.dag_id == dag_id and s.ref.task_id == task_id
        ]
        runs.sort(key=lambda s: s.created_at or "", reverse=True)
        runs = runs[:win]
        runs.reverse()  # oldest -> newest, so columns read left (old) to right (new)
        rdata = [
            {
                "run_id": s.ref.run_id,
                "created_at": s.created_at,
                "outcomes": {
                    node: info["outcome"]
                    for node, info in (src.test_outcomes(s.ref) or {}).items()
                },
            }
            for s in runs
        ]
        body = build_heatmap(rdata, max_rows=_HEATMAP_MAX_ROWS)
        return JSONResponse(
            {"dag_id": dag_id, "task_id": task_id, "window": win, **body}
        )

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
        node_id: str,
        dag_id: str | None = None,
        task_id: str | None = None,
        limit: int = 50,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """One test's outcome and duration across runs.

        ``node_id`` is the pytest node id (``file::Class::test``). With both
        ``dag_id`` and ``task_id`` given, returns the newest ``limit`` runs of that
        EXACT dag·task (``null`` outcome when the test didn't run that time).

        With dag·task omitted (the *Unique tests* view), the history is MERGED across
        every readable dag·task where this node id ran — the same test triggered from
        two places shows a single, unified timeline. Each entry then also carries the
        ``dag_id``/``task_id`` it came from. Newest ``limit`` runs (clamped 1–500).
        """
        lim = max(1, min(limit, 500))
        history: list[dict[str, Any]] = []

        if dag_id is not None and task_id is not None:
            if not read_auth(dag_id, user):
                raise HTTPException(
                    status_code=403, detail="not authorized to read this dag"
                )
            runs = [
                s
                for s in src.list_summaries(dag_id=dag_id)
                if s.ref.dag_id == dag_id and s.ref.task_id == task_id
            ]
            runs.sort(key=lambda s: s.created_at or "", reverse=True)
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

        # Merged: newest runs across ALL readable dag·tasks where this node id ran.
        scanned = 0
        capped = False
        for s in src.list_summaries():  # newest first, every dag
            if not read_auth(s.ref.dag_id, user):
                continue
            if scanned >= _UNIQUE_SCAN_CAP:
                capped = True
                break
            scanned += 1
            info = (src.test_outcomes(s.ref) or {}).get(node_id)
            if info is None:
                continue  # this test didn't run in this run
            history.append(
                {
                    "run_id": s.ref.run_id,
                    "created_at": s.created_at,
                    "outcome": info.get("outcome"),
                    "duration": info.get("duration"),
                    "dag_id": s.ref.dag_id,
                    "task_id": s.ref.task_id,
                }
            )
            if len(history) >= lim:
                break
        return JSONResponse(
            {
                "node_id": node_id,
                "dag_id": None,
                "task_id": None,
                "history": history,
                "capped": capped,
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
                        "runs": 12,
                        "passed": 10,
                        "failed": 1,
                        "errors": 0,
                        "skipped": 1,
                        "avg_duration": 0.42,
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
        sorted catalogue only when ``full`` is set — i.e. when the user opens the list —
        with per-test stats aggregated from the SAME scan (no extra I/O): ``runs`` (total
        appearances), per-outcome counts (``passed`` / ``failed`` / ``errors`` /
        ``skipped``) and ``avg_duration`` over those runs.
        """
        task_q = (task_id or "").lower()
        seen: dict[str, dict[str, Any]] = {}  # node_id -> first-seen identity + tallies
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
            for node, info in (src.test_outcomes(s.ref) or {}).items():
                st = seen.get(node)
                if st is None:
                    st = seen[node] = {
                        "dag_id": s.ref.dag_id,
                        "task_id": s.ref.task_id,
                        "runs": 0,
                        "passed": 0,
                        "failed": 0,
                        "errors": 0,
                        "skipped": 0,
                        "_dur": 0.0,
                    }
                st["runs"] += 1
                outcome = info.get("outcome")
                if outcome == "passed":
                    st["passed"] += 1
                elif outcome == "failed":
                    st["failed"] += 1
                elif outcome == "error":
                    st["errors"] += 1
                elif outcome == "skipped":
                    st["skipped"] += 1
                st["_dur"] += float(info.get("duration") or 0.0)
        body: dict[str, Any] = {"count": len(seen), "capped": capped}
        if full:
            body["tests"] = [
                {
                    "node_id": n,
                    "dag_id": st["dag_id"],
                    "task_id": st["task_id"],
                    "runs": st["runs"],
                    "passed": st["passed"],
                    "failed": st["failed"],
                    "errors": st["errors"],
                    "skipped": st["skipped"],
                    "avg_duration": round(st["_dur"] / st["runs"], 3)
                    if st["runs"]
                    else 0.0,
                }
                for n, st in sorted(seen.items())
            ]
        return JSONResponse(body)

    return router
