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

"""JSON-serializable view models for the reports UI."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, cast


def _encode_token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_token(token: str) -> dict[str, Any]:
    pad = "=" * (-len(token) % 4)
    # validate=True rejects ANY byte outside the alphabet. The lax default silently
    # skips junk, so a token with e.g. CRLF smuggled in could still decode and carry
    # the raw (log-injectable) string through every ``report_id`` code path.
    raw = base64.b64decode(token + pad, altchars=b"-_", validate=True)
    return cast("dict[str, Any]", json.loads(raw))


@dataclass(frozen=True)
class ReportRef:
    """Airflow coordinates identifying one stored report.

    ``map_index``: ``-1`` for a non-mapped task (Airflow convention), else the
    expanded element's index of a mapped task.
    """

    dag_id: str
    run_id: str
    task_id: str
    try_number: int
    map_index: int = -1

    @property
    def token(self) -> str:
        """Opaque, URL-safe, reversible id for the HTTP API."""
        return _encode_token(
            {
                "d": self.dag_id,
                "r": self.run_id,
                "t": self.task_id,
                "n": self.try_number,
                "m": self.map_index,
            }
        )

    @classmethod
    def from_token(cls, token: str) -> ReportRef:
        """Inverse of :pyattr:`token`. Raises ``ValueError`` on a bad token."""
        try:
            d = _decode_token(token)
            try_number = int(d["n"])
            map_index = int(d["m"])
            if try_number < 0 or map_index < -1:
                raise ValueError("out-of-range try_number/map_index")
            return cls(
                dag_id=str(d["d"]),
                run_id=str(d["r"]),
                task_id=str(d["t"]),
                try_number=try_number,
                map_index=map_index,
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed report token: {token!r}") from exc


@dataclass(frozen=True)
class ReportSummary:
    """Headline numbers for one run, from ``meta.json`` (no XML parse)."""

    ref: ReportRef
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration: float
    success: bool
    created_at: str | None = None
    logical_date: str | None = None
    has_allure: bool = False
    has_triage: bool = False
    #: The producer's own tally of this run's verdicts: ``{category: count}``, the ``model``
    #: that judged them, and ``incomplete`` when the pass itself broke. Read straight from
    #: the roll-up in ``meta.json``, so the list can show a run's MIX -- and which of the
    #: three mark states it is in -- without opening anything else. The detail view recounts
    #: from the verdicts it can actually display, which is why this carries no "N of M"
    #: total that could contradict it.
    triage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.ref.token,
            "dag_id": self.ref.dag_id,
            "run_id": self.ref.run_id,
            "task_id": self.ref.task_id,
            "try_number": self.ref.try_number,
            "map_index": self.ref.map_index,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration": self.duration,
            "success": self.success,
            "created_at": self.created_at,
            "logical_date": self.logical_date,
            "has_allure": self.has_allure,
            "has_triage": self.has_triage,
            "triage": dict(self.triage) if self.triage else None,
        }


def run_succeeds(passed: int, failed: int, errors: int, threshold: float) -> bool:
    """Whether a run passes at pass-rate ``threshold`` (0-1).

    Rate is over *executed* tests -- ``passed / (passed + failed + errors)`` -- so
    skipped tests don't count and a run with nothing executed passes. At
    ``threshold == 1.0`` this means "no failures or errors".
    """
    executed = passed + failed + errors
    if executed <= 0:
        return True
    return passed / executed >= threshold


@dataclass(frozen=True)
class Verdict:
    """One AI triage verdict for a failed test, as produced by ``pytest-triage``.

    ``category`` is the frozen machine-readable judgement -- ``regression`` (the product
    code broke), ``flaky``, ``env`` (the environment, not the code), ``test_bug`` (the
    test itself is wrong) or ``unknown``; ``None`` when the failure was reported but never
    judged (a report-only run, or one past its ``--ai-budget``), which still carries the
    exception type and a rerun selector. ``hypothesis`` and ``suggested_fix`` are the
    model's prose and may be in the provider's own language (GigaChat answers in Russian);
    ``selector`` is the ready-to-run pytest argument for rerunning just this test.
    """

    category: str | None = None
    hypothesis: str | None = None
    confidence: str | None = None  # "low" | "medium" | "high"
    suggested_fix: str | None = None
    exc_type: str | None = None
    selector: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "hypothesis": self.hypothesis,
            "confidence": self.confidence,
            "suggested_fix": self.suggested_fix,
            "exc_type": self.exc_type,
            "selector": self.selector,
        }


@dataclass(frozen=True)
class TriageSummary:
    """Run-level roll-up of an AI triage pass.

    ``model`` and ``duration`` are ``None`` when the run was archived with a report but no
    provider (``triage=True`` alone) -- every failure is described, none is judged.
    ``counts`` holds only the categories actually seen, biggest-first ordering left to the
    UI. ``total_failures`` counts what pytest-triage saw; ``total_verdicts`` how many of
    them are actually judged here.
    ``incomplete``: why the pass produced fewer verdicts than there were failures, when the
    cause was the triage pass itself -- a rejected API key, a timeout, an exhausted budget,
    a provider that kept failing. ``None`` when nothing went wrong.
    """

    model: str | None = None
    duration: float | None = None
    total_failures: int = 0
    total_verdicts: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    incomplete: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "duration": self.duration,
            "total_failures": self.total_failures,
            "total_verdicts": self.total_verdicts,
            "counts": dict(self.counts),
            "incomplete": self.incomplete,
        }


@dataclass(frozen=True)
class CaseView:
    """One test case, flattened for the detail table.

    ``verdict``: the AI triage judgement for this test, when the run was archived with
    ``ArchivingResultParser(triage_provider=...)`` and the provider reached it. Only
    failed/errored cases can carry one.
    """

    node_id: str
    name: str
    classname: str
    outcome: str  # "passed" | "failed" | "error" | "skipped"
    time: float
    message: str | None = None
    verdict: Verdict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "classname": self.classname,
            "outcome": self.outcome,
            "time": self.time,
            "message": self.message,
            "verdict": self.verdict.to_dict() if self.verdict else None,
        }


@dataclass(frozen=True)
class ReportDetail:
    """Summary plus per-case rows -- the detail view's payload.

    ``alerts``: the run's email-notification history (oldest first) from the
    ``meta.json`` sidecar; each entry has ``at``/``kind``/``recipients``/``ok``/``manual``.
    ``coverage``: the run's overall line-coverage fraction (0-1), baked in at archive
    time or from the operator's XCom; ``None`` when unknown.
    ``coverage_threshold``: the bar THIS run's coverage should be read against, when the
    producer pinned one (``ArchivingResultParser(coverage_threshold=...)``); ``None`` lets
    the reader fall back to ``AIRFLOW_PYTEST_SUCCESS_COVERAGE``.
    ``triage``: the run-level AI triage roll-up (the per-test judgements ride on
    :attr:`CaseView.verdict`); ``None`` when the run wasn't triaged.
    """

    summary: ReportSummary
    cases: tuple[CaseView, ...] = field(default_factory=tuple)
    alerts: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    coverage: float | None = None
    coverage_threshold: float | None = None
    triage: TriageSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        data = self.summary.to_dict()
        data["cases"] = [c.to_dict() for c in self.cases]
        data["alerts"] = list(self.alerts)
        data["coverage"] = self.coverage
        data["triage"] = self.triage.to_dict() if self.triage else None
        return data
