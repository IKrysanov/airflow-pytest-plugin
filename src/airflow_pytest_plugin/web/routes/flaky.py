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

from ...config import (
    get_flaky_min_score,
    get_flaky_quarantine_score,
    get_flaky_window,
)
from .common import FAIL_OUTCOMES, RouteDeps, ok

TAG = "flaky"

#: Upper bound on flaky tests returned.
_FLAKY_CAP = 1000

#: Max run-meta files read per request (mirrors slow's ``_SLOW_SCAN_CAP``). Flaky work is
#: Σ groups · min(runs, window) outcome reads with no other bound, so many dag·tasks × a
#: large window could otherwise make a single request walk much of the archive.
_FLAKY_SCAN_CAP = 2000

#: How many recent outcomes to include in a flaky test's strip (keeps the UI tidy).
_FLAKY_STRIP = 10


def _flip_rate(seq: list[str]) -> float:
    """Fraction of consecutive runs that switched between pass and fail/error."""
    if len(seq) < 2:
        return 0.0
    flips = sum(
        1
        for a, b in zip(seq, seq[1:], strict=False)
        if (a in FAIL_OUTCOMES) != (b in FAIL_OUTCOMES)
    )
    return flips / (len(seq) - 1)


def _trend(seq: list[str]) -> str:
    """Is the test flipping more lately? ``up`` (worse) / ``down`` (calmer) / ``flat``."""
    if len(seq) < 4:
        return "flat"
    mid = len(seq) // 2
    older, newer = _flip_rate(seq[:mid]), _flip_rate(seq[mid:])
    if newer > older + 1e-9:
        return "up"
    if newer < older - 1e-9:
        return "down"
    return "flat"


def flaky_stats(
    seq: list[str], *, min_score: float = 0.0, quarantine_score: float = 1.0
) -> dict[str, Any] | None:
    """Flakiness stats for one test's outcomes (oldest→newest), or ``None`` if stable.

    A test counts as flaky only if the window holds both a pass and a fail/error AND
    its ``score`` clears ``min_score`` -- so a lone blip in a long history (a near-zero
    flip rate) is filtered out. ``score`` is the flip rate (0–1), normalised by run
    count so it's comparable across histories; ``trend`` compares the recent half to
    the older half; ``quarantined`` marks scores at/above ``quarantine_score``.
    """
    fails = sum(1 for o in seq if o in FAIL_OUTCOMES)
    if not fails or not any(o == "passed" for o in seq):
        return None
    score = round(_flip_rate(seq), 3)
    if score < min_score:  # too steady to count as flaky
        return None
    flips = sum(
        1
        for a, b in zip(seq, seq[1:], strict=False)
        if (a in FAIL_OUTCOMES) != (b in FAIL_OUTCOMES)
    )
    return {
        "runs": len(seq),
        "fails": fails,
        "flips": flips,
        "score": score,
        "trend": _trend(seq),
        "quarantined": score >= quarantine_score,
        "recent": seq[-_FLAKY_STRIP:],
    }


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``flaky``."""
    router = APIRouter(tags=[TAG])
    src = deps.src
    read_auth = deps.read_auth
    user_dep = deps.user_dep

    @router.get(
        "/api/flaky",
        summary="Flaky tests",
        responses=ok(
            {
                "flaky": [
                    {
                        "dag_id": "api_gateway",
                        "task_id": "integration_tests",
                        "node_id": "tests/api.py::test_auth",
                        "runs": 8,
                        "fails": 4,
                        "flips": 7,
                        "score": 1.0,
                        "trend": "flat",
                        "quarantined": True,
                        "recent": ["passed", "failed", "passed", "failed"],
                    }
                ],
                "total": 1,
                "capped": False,
                "window": 30,
                "quarantine_score": 0.5,
                "min_score": 0.1,
            }
        ),
    )
    def flaky(
        dag_id: str | None = None,
        task_id: str | None = None,
        window: int | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Tests that BOTH pass and fail within the last ``window`` runs of a dag·task.

        Groups the visible runs by dag·task, looks at the most recent ``window`` of
        each (defaults to the configured window; clamped 2–200), and reports every
        test that shows both a pass and a fail/error. Per test: ``runs``, ``fails``,
        ``flips``, a ``score`` (flip rate 0–1), a ``trend`` (``up``/``down``/``flat``),
        a ``quarantined`` flag, and a ``recent`` outcome strip (last 10). Sorted
        flakiest-first; capped at ``1000``. At most ``2000`` run-meta files are read per
        request; ``capped`` flags either truncation (output cap or read budget).
        ``quarantine_score`` echoes the threshold.
        """
        chosen = window if window is not None else get_flaky_window()
        win = max(2, min(chosen, 200))
        qscore = get_flaky_quarantine_score()
        min_score = get_flaky_min_score()
        task_q = (task_id or "").lower()
        groups: dict[tuple[str, str], list[Any]] = {}
        for s in src.list_summaries(dag_id=dag_id):
            if task_q and task_q not in s.ref.task_id.lower():
                continue
            if not read_auth(s.ref.dag_id, user):
                continue
            groups.setdefault((s.ref.dag_id, s.ref.task_id), []).append(s)

        items: list[dict[str, Any]] = []
        scanned = 0
        scan_capped = False
        for (dag, task), summaries in groups.items():
            if scanned >= _FLAKY_SCAN_CAP:  # skip whole groups past the read budget
                scan_capped = True
                break
            summaries.sort(key=lambda s: s.created_at or "", reverse=True)
            window_runs = summaries[:win]
            if len(window_runs) < 2:
                continue
            scanned += len(window_runs)
            seqs: dict[str, list[str]] = {}
            for s in reversed(window_runs):  # oldest -> newest
                for node, info in (src.test_outcomes(s.ref) or {}).items():
                    seqs.setdefault(node, []).append(info["outcome"])
            for node, seq in seqs.items():
                stats = flaky_stats(seq, min_score=min_score, quarantine_score=qscore)
                if stats is not None:
                    items.append(
                        {"dag_id": dag, "task_id": task, "node_id": node, **stats}
                    )
        items.sort(key=lambda x: (-x["score"], -x["fails"], x["node_id"]))
        return JSONResponse(
            {
                "flaky": items[:_FLAKY_CAP],
                "total": min(len(items), _FLAKY_CAP),
                "capped": scan_capped or len(items) > _FLAKY_CAP,
                "window": win,
                "quarantine_score": qscore,
                "min_score": min_score,
            }
        )

    return router
