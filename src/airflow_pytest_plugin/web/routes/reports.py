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

"""Report routes: browse runs, per-test detail, history, the test catalogue, and
emailing a run's summary."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ...config import (
    get_flaky_window,
    get_slow_factor,
    get_slow_min_delta,
    get_success_threshold,
)
from ...notifications import (
    AlertPolicy,
    allure_attachment,
    build_mailer,
    build_run_alert,
    dedupe_emails,
    is_valid_email,
    record_sent_alert,
)
from .common import ERR_400, ERR_403, ERR_404, RouteDeps, ok, ref_from_token

_log = logging.getLogger(__name__)

TAG = "reports"

#: Recipient cap per email, so the endpoint can't be used as a mass-mailer.
_MAX_EMAIL_RECIPIENTS = 10


def _email_available() -> bool:
    """Whether a mail transport exists (Airflow SMTP or standalone), so the UI can show
    the Email button. Independent of the recipients config."""
    try:
        return build_mailer() is not None
    except Exception:  # pragma: no cover - defensive: never fail the list on this probe
        return False


def _user_label(user: Any) -> str:
    """A stable-ish id for the acting user, for the audit log (no email/PII)."""
    for attr in ("id", "user_id", "username", "name"):
        value = getattr(user, attr, None)
        if value:
            return str(value)
    return "anonymous"


def _safe_reason(exc: Exception) -> str:
    """One-line send-failure summary (type + message), safe for the RBAC-gated caller:
    no traceback, no password (the mailer never puts it in the exception)."""
    msg = " ".join(str(exc).split())  # collapse whitespace/newlines
    text = f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__
    return text[:200]


async def _json_body(request: Request) -> dict[str, Any]:
    """Parse the JSON object body; tolerate an empty/absent/invalid body."""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _resolve_recipients(body: dict[str, Any]) -> tuple[str, ...]:
    """Validated recipients from the body, or the configured default when omitted.

    Accepts a list or a comma/semicolon string. Each address goes through the alerting
    layer's strict ``is_valid_email``; a bad one raises HTTP ``400`` naming it. The list
    is capped (no mass-mailing) and case-insensitive duplicates collapse to one send.
    """
    raw = body.get("recipients")
    if raw is None or raw == "":
        # Configured default via the policy, so ONE place normalizes it (invalid
        # dropped, deduped, capped) for both the automatic and the manual path.
        return AlertPolicy.from_config().recipients
    if isinstance(raw, str):
        raw = re.split(r"[,;]", raw)
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=400, detail="recipients must be a list of email addresses"
        )
    cleaned = [str(r).strip() for r in raw if str(r).strip()]
    bad = next((r for r in cleaned if not is_valid_email(r)), None)
    if bad is not None:
        raise HTTPException(
            status_code=400,
            detail=f"invalid email address: {bad[:100]!r} — use name@example.com",
        )
    deduped = dedupe_emails(cleaned)
    if len(deduped) > _MAX_EMAIL_RECIPIENTS:
        raise HTTPException(
            status_code=400,
            detail=f"too many recipients (max {_MAX_EMAIL_RECIPIENTS})",
        )
    return deduped


#: Newest runs /api/unique-tests reads per-test maps from, so a filter change can't
#: trigger an unbounded scan of every archived run.
_UNIQUE_SCAN_CAP = 1000

#: Caps on /api/slow output: regressions list and the slowest leaderboard.
_SLOW_CAP = 1000
_SLOW_TOP = 50
#: Read budget: run-meta files /api/slow reads per request. Whole groups are skipped
#: once exceeded (``capped`` flags it), so a broad scan can't read every archive.
_SLOW_SCAN_CAP = 2000

#: /api/heatmap bounds — recent runs (columns) and tests (rows) per request, so one
#: dag·task's matrix can't blow up the payload or the read.
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

    One entry per dag·task: run count, passed count (per the configured success
    threshold), pass rate, average run duration, and the newest run's status/time.
    Sorted by most-recent activity. Lets a grouped view read group stats without
    shipping every run -- how grouping scales past the in-browser approach.
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
    regression (``regressed``) needs at least four runs and the recent half's average
    both ``factor``× the older half AND ≥ ``min_delta`` s slower — the absolute floor
    keeps fast tests with jittery ratios off the list. ``ratio`` is recent÷older
    (``None`` until enough runs, or when the older half averaged 0 — an "appeared from
    nothing" jump). ``durations`` holds only runs where the test actually appeared, so
    the split-half compares the test to itself, split over appearances not calendar slots.
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

    ``runs`` items are ``{"run_id", "created_at", "outcomes": {node_id: outcome}}``. One
    row per distinct test — a ``cells`` list of single-char codes aligned to ``runs``
    (``-`` where the test didn't run) — sorted most-broken first (fail+error count, then
    flip count), capped at ``max_rows`` (``truncated`` flags it). Failing and flaky tests
    bubble up so a regression block or flaky row is seen at a glance.
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
        responses=ok(
            {
                "reports": [_EX_SUMMARY],
                "success_threshold": 0.85,
                "email_available": True,
            }
        ),
    )
    def list_reports(
        dag_id: str | None = None,
        run_id: str | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Run summaries, newest first.

        Each entry carries pass/fail/skip/error counts, duration, identity
        (dag·run·task·try) and its opaque token. Optional ``dag_id`` / ``run_id`` narrow
        by case-insensitive substring. RBAC-filtered to readable runs.
        ``success_threshold`` echoes the configured pass-rate bar (0–1) for the chart.
        """
        summaries = src.list_summaries(dag_id=dag_id, run_id=run_id)
        visible = [s for s in summaries if read_auth(s.ref.dag_id, user)]
        return JSONResponse(
            {
                "reports": [s.to_dict() for s in visible],
                "success_threshold": get_success_threshold(),
                "email_available": _email_available(),
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
        substring; RBAC-filtered. Lets grouped views show group stats without fetching
        every run (scales past in-browser grouping).
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
        ``factor``× the older half AND ≥ ``min_delta`` s), worst-ratio first — one that
        speeds back up drops off. ``slowest`` is the top ``50`` by average duration,
        skipping single-run / zero-time tests so it means *reliably* slow. Optional
        ``dag_id`` / ``task_id`` / ``run_id`` narrow by substring; RBAC-filtered. At most
        ``2000`` run-meta files are read per request; ``capped`` flags skipped groups.
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
            if scanned >= _SLOW_SCAN_CAP:  # past read budget: skip remaining groups
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
                # Reliably-slow only: skip single-run / zero-time noise.
                if stats["runs"] >= 2 and stats["avg"] > 0:
                    slowest.append(item)

        def _ratio_key(x: dict[str, Any]) -> float:
            r = x["ratio"]  # None = was ~0s, now slow: treat as infinite, rank first
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
        runs (oldest→newest), each cell an outcome (``p``/``f``/``e``/``s``; ``-`` = didn't
        run that time). Rows sorted most-broken first (fail+error count, then flakiness) so
        regression blocks and flaky tests surface at the top. ``window`` defaults to the
        flaky window (clamped 2–``100``); rows capped at ``300`` (``truncated`` flags it).
        ``403`` if the dag isn't readable.
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
                    node: info.get("outcome", "")
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

        Includes every case's outcome, duration and captured output. ``400`` malformed
        token, ``403`` dag not readable, ``404`` missing.
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

        Destructive: requires permission to **trigger** the run's DAG (RBAC), not just
        read it. ``400`` bad token, ``403`` not permitted, ``404`` already gone.
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

    @router.post(
        "/api/reports/{report_id}/email",
        summary="Email a run summary",
        responses={
            **ok(
                {
                    "sent": True,
                    "recipients": ["team@example.com"],
                    "kind": "failed",
                }
            ),
            **ERR_400,
            **ERR_403,
            **ERR_404,
            502: {"description": "The mail server rejected the message."},
            503: {"description": "Email is not configured on this server."},
        },
    )
    async def email_report(
        report_id: str,
        request: Request,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Email a summary of one run.

        Requires permission to **read** the run's DAG (RBAC). Recipients may come from the
        JSON body (``{"recipients": ["a@x.io", ...]}`` or a comma/semicolon string) — each
        validated, list capped at ``_MAX_EMAIL_RECIPIENTS``; omit to use the configured
        ``AIRFLOW_PYTEST_ALERTS_EMAIL_TO``. ``400`` bad token / bad or missing recipients,
        ``403`` not readable, ``404`` run gone, ``503`` no mail transport, ``502`` send failed.
        """
        ref = ref_from_token(report_id)
        if not read_auth(ref.dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read this report"
            )
        if src.get_detail(ref) is None:
            raise HTTPException(status_code=404, detail="report not found")

        recipients = _resolve_recipients(await _json_body(request))
        if not recipients:
            raise HTTPException(
                status_code=400, detail="no recipients provided or configured"
            )

        policy = replace(AlertPolicy.from_config(), recipients=recipients)
        mailer = build_mailer()
        if mailer is None:
            raise HTTPException(
                status_code=503, detail="email is not configured on this server"
            )
        # always=True: a manual send emails any run, incl. a clean pass (green template).
        alert = build_run_alert(src, ref, policy, always=True)
        if alert is None:
            raise HTTPException(status_code=404, detail="report not found")
        try:
            mailer.send(
                subject=alert.subject,
                body=alert.body,
                html=alert.html,
                recipients=recipients,
                attachments=allure_attachment(src, ref),
            )
        except Exception as exc:
            # _safe_reason collapses newlines -> the entry stays one log line even if
            # the exception text carries user-influenced content (CodeQL: log injection).
            _log.warning("emailing run %s failed: %s", report_id, _safe_reason(exc))
            record_sent_alert(src, ref, alert, recipients, ok=False, manual=True)
            # Surface a short, safe reason (type + message, no traceback/password) so the
            # caller can act -- e.g. "SMTPAuthenticationError: (535, ...)". Safe because the
            # endpoint is RBAC-gated and the mailer never echoes the password.
            raise HTTPException(status_code=502, detail=_safe_reason(exc)) from exc
        record_sent_alert(src, ref, alert, recipients, ok=True, manual=True)
        # Audit: who emailed which run to how many recipients (count only, no addresses).
        _log.info(
            "emailed run %s·%s·%s to %d recipient(s) (user=%s)",
            ref.dag_id,
            ref.task_id,
            ref.run_id,
            len(recipients),
            _user_label(user),
        )
        return JSONResponse(
            {"sent": True, "recipients": list(recipients), "kind": alert.kind}
        )

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

        Present only when archived with ``ArchivingResultParser(allure=True)``.
        ``400``/``403`` as for the detail; ``404`` when no Allure results were captured.
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

        ``node_id`` is the pytest node id (``file::Class::test``). With both ``dag_id``
        and ``task_id`` given, returns the newest ``limit`` runs of that EXACT dag·task
        (``null`` outcome when the test didn't run that time).

        With dag·task omitted (the *Unique tests* view), history is MERGED across every
        readable dag·task where this node id ran, so the same test triggered from two
        places shows one unified timeline; each entry then also carries its
        ``dag_id``/``task_id``. Newest ``limit`` runs (clamped 1–500).
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
                        "outcome": info.get("outcome") if info else None,
                        "duration": info.get("duration") if info else None,
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
                continue  # test didn't run in this run
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
        count stays cheap (``capped`` flags truncation). The full sorted catalogue is
        included only when ``full`` is set (user opens the list), with per-test stats from
        the SAME scan (no extra I/O): ``runs`` (total appearances), per-outcome counts
        (``passed`` / ``failed`` / ``errors`` / ``skipped``) and ``avg_duration``.
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
