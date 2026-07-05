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

"""Monitoring routes — liveness, readiness, and build info of the reader."""

from __future__ import annotations

import hmac
import os
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ...compat import airflow_auth_available
from ...config import get_metrics_token
from ...version import __version__
from .common import RouteDeps, ok

TAG = "monitoring"
_DIST_NAME = "airflow-pytest-plugin"

#: Caps per-dag·task series so one scrape can't blow up Prometheus cardinality (or our
#: response size), however many dag·tasks have archived runs.
_METRICS_MAX_GROUPS = 2000

#: The Prometheus text exposition content type.
_METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

#: Bearer scheme for /api/metrics. Declared (not a plain header param) so Swagger shows an
#: "Authorize" box that actually sends the Authorization header — Swagger UI drops a plain
#: header field. ``auto_error=False`` keeps our own 404 (disabled) / 401 (bad token) instead
#: of FastAPI's default 403.
_metrics_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="MetricsToken",
    description="The AIRFLOW_PYTEST_METRICS_TOKEN value (the 'Bearer ' prefix is added for you).",
)


def _esc_label(value: str) -> str:
    """Escape a Prometheus label value (backslash, newline, double-quote)."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _fmt(value: float | int) -> str:
    """Render a metric value at full precision — no ``%g`` rounding, so timestamps stay exact.

    Whole numbers (including integer-valued floats like unix timestamps) print without a
    decimal or scientific notation; other floats use the shortest round-trippable repr.
    """
    if isinstance(value, int):
        return str(value)
    f = float(value)
    return str(int(f)) if f.is_integer() else repr(f)


def _run_ts(created_at: str | None) -> float | None:
    """Unix timestamp of an ISO ``created_at``, or ``None`` if absent/unparseable."""
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at).timestamp()
    except (ValueError, TypeError):
        return None


def render_metrics(
    summaries: Iterable[Any],
    *,
    version: str = __version__,
    scrape_seconds: float | None = None,
    max_groups: int = _METRICS_MAX_GROUPS,
) -> str:
    """Build a Prometheus text exposition from run summaries (pure, no I/O).

    Derives everything from the already-scanned summaries (no per-run JUnit parsing), and
    exposes only group-level series — each dag·task's LATEST run — with ``{dag_id, task_id}``
    cardinality capped at ``max_groups``. Flaky / slow signals are deliberately left out:
    they'd force every scrape to read each run. Use the JSON APIs for those.
    """
    summaries = list(summaries)
    latest: dict[tuple[str, str], Any] = {}
    runs_per_group: dict[tuple[str, str], int] = {}
    for s in summaries:
        key = (s.ref.dag_id, s.ref.task_id)
        runs_per_group[key] = runs_per_group.get(key, 0) + 1
        cur = latest.get(key)
        if cur is None or (s.created_at or "") > (cur.created_at or ""):
            latest[key] = s

    keys = sorted(latest)  # deterministic output order
    truncated = len(keys) > max_groups
    keys = keys[:max_groups]
    failures_total = sum((latest[k].failed + latest[k].errors) for k in keys)

    lines: list[str] = []

    def family(name: str, help_: str, samples: list[str]) -> None:
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} gauge")
        lines.extend(samples)

    family(
        "airflow_pytest_up",
        "1 when the reader is serving metrics.",
        ["airflow_pytest_up 1"],
    )
    family(
        "airflow_pytest_build_info",
        "Reader build info (constant 1; carries the version label).",
        [f'airflow_pytest_build_info{{version="{_esc_label(version)}"}} 1'],
    )
    # Gauges, so no `_total` suffix (reserved for counters): these can decrease as runs
    # are pruned or tests get fixed.
    family(
        "airflow_pytest_runs",
        "Archived runs across all dag·tasks.",
        [f"airflow_pytest_runs {len(summaries)}"],
    )
    family(
        "airflow_pytest_dagtasks",
        "Distinct dag·tasks with archived runs.",
        [f"airflow_pytest_dagtasks {len(latest)}"],
    )
    family(
        "airflow_pytest_latest_failures",
        "Failed+errored tests across every dag·task's latest run (current breakage).",
        [f"airflow_pytest_latest_failures {failures_total}"],
    )
    family(
        "airflow_pytest_series_truncated",
        "1 if per-dag·task series were capped at the cardinality limit.",
        [f"airflow_pytest_series_truncated {1 if truncated else 0}"],
    )
    if scrape_seconds is not None:
        family(
            "airflow_pytest_scrape_duration_seconds",
            "Seconds spent gathering the data for this scrape.",
            [f"airflow_pytest_scrape_duration_seconds {scrape_seconds:.6f}"],
        )

    def lbl(key: tuple[str, str]) -> str:
        return f'{{dag_id="{_esc_label(key[0])}",task_id="{_esc_label(key[1])}"}}'

    # Per dag·task, from its LATEST run.
    per_group: list[tuple[str, str, Callable[[Any], float]]] = [
        ("airflow_pytest_latest_tests", "Tests in the latest run.", lambda s: s.total),
        (
            "airflow_pytest_latest_passed",
            "Passed tests in the latest run.",
            lambda s: s.passed,
        ),
        (
            "airflow_pytest_latest_failed",
            "Failed tests in the latest run.",
            lambda s: s.failed,
        ),
        (
            "airflow_pytest_latest_errors",
            "Errored tests in the latest run.",
            lambda s: s.errors,
        ),
        (
            "airflow_pytest_latest_skipped",
            "Skipped tests in the latest run.",
            lambda s: s.skipped,
        ),
        (
            "airflow_pytest_latest_pass_ratio",
            "Pass ratio (0..1) of the latest run.",
            lambda s: (s.passed / s.total) if s.total else 0.0,
        ),
        (
            "airflow_pytest_latest_duration_seconds",
            "Wall time of the latest run.",
            lambda s: float(s.duration),
        ),
        (
            "airflow_pytest_latest_success",
            "1 if the latest run met the success threshold.",
            lambda s: 1 if s.success else 0,
        ),
    ]
    for name, help_, fn in per_group:
        family(name, help_, [f"{name}{lbl(k)} {_fmt(fn(latest[k]))}" for k in keys])
    family(
        "airflow_pytest_dagtask_runs",
        "Archived runs for the dag·task.",
        [f"airflow_pytest_dagtask_runs{lbl(k)} {runs_per_group[k]}" for k in keys],
    )

    ts_samples = [
        f"airflow_pytest_latest_run_timestamp_seconds{lbl(k)} {_fmt(ts)}"
        for k in keys
        if (ts := _run_ts(latest[k].created_at)) is not None
    ]
    if ts_samples:
        family(
            "airflow_pytest_latest_run_timestamp_seconds",
            "Unix time of the dag·task's latest run.",
            ts_samples,
        )

    return "\n".join(lines) + "\n"


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``monitoring``."""
    router = APIRouter(tags=[TAG])
    src = deps.src

    @router.get(
        "/api/health",
        summary="Health & readiness",
        responses=ok(
            {
                "status": "ok",
                "ready": True,
                "reports_root": "/opt/airflow/pytest-reports",
                "reports_root_exists": True,
                "auth": "airflow",
                "secure_xml": True,
            }
        ),
    )
    def health() -> JSONResponse:
        """Liveness + readiness of the reader. No params, no report reads, no auth.

        Fields:

        - ``status`` — ``"ok"`` whenever the app is serving (liveness).
        - ``ready`` / ``reports_root_exists`` — whether the report directory exists and
          is readable; ``ready`` is ``false`` when the reader can't see its store.
        - ``reports_root`` — where the producer writes and the reader reads (``null`` for
          a non-filesystem source).
        - ``auth`` — ``"airflow"`` when Airflow RBAC gates the data routes, else ``"open"``
          (standalone / allow-all).
        - ``secure_xml`` — whether JUnit XML uses the hardened ``defusedxml`` parser (vs
          the stdlib fallback).

        No directory scan, so it's safe for frequent probes.
        """
        root = getattr(src, "report_root", None)
        exists = bool(
            root is not None and os.path.isdir(root) and os.access(root, os.R_OK)
        )
        return JSONResponse(
            {
                "status": "ok",
                "ready": exists,
                "reports_root": root,
                "reports_root_exists": exists,
                "auth": "airflow" if airflow_auth_available() else "open",
                "secure_xml": getattr(src, "secure_xml", None),
            }
        )

    @router.get(
        "/api/version",
        summary="Build info",
        responses=ok({"name": _DIST_NAME, "version": __version__}),
    )
    def version() -> JSONResponse:
        """The plugin's distribution name and version (from package metadata)."""
        return JSONResponse({"name": _DIST_NAME, "version": __version__})

    @router.get(
        "/api/metrics",
        summary="Prometheus metrics",
        response_class=PlainTextResponse,
        responses={
            200: {
                "description": "Prometheus text exposition.",
                "content": {"text/plain": {"example": "airflow_pytest_up 1\n"}},
            },
            401: {"description": "Missing or invalid bearer token."},
            404: {"description": "Metrics endpoint disabled (no token configured)."},
        },
    )
    def metrics(
        creds: HTTPAuthorizationCredentials | None = Depends(_metrics_bearer),  # noqa: B008
    ) -> PlainTextResponse:
        """Prometheus exposition of per-dag·task latest-run gauges (group-level only).

        Secure by default: disabled (``404``) unless ``AIRFLOW_PYTEST_METRICS_TOKEN`` is set;
        when set, the scrape must send ``Authorization: Bearer <token>`` (compared in constant
        time). Cheap: one cached directory scan, summary-derived, cardinality-capped, no
        per-run reads. Point Prometheus at it with ``bearer_token``.
        """
        token = get_metrics_token()
        if not token:
            raise HTTPException(status_code=404, detail="metrics endpoint is disabled")
        provided = creds.credentials if creds else ""
        if not provided or not hmac.compare_digest(provided.encode(), token.encode()):
            raise HTTPException(
                status_code=401, detail="invalid or missing metrics token"
            )
        started = time.perf_counter()
        summaries = src.list_summaries()  # cached scan; no per-run JUnit reads
        text = render_metrics(
            summaries,
            scrape_seconds=time.perf_counter() - started,
            max_groups=_METRICS_MAX_GROUPS,
        )
        return PlainTextResponse(text, media_type=_METRICS_CONTENT_TYPE)

    return router
