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
    raw = base64.urlsafe_b64decode(token + pad)
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
class CaseView:
    """One test case, flattened for the detail table."""

    node_id: str
    name: str
    classname: str
    outcome: str  # "passed" | "failed" | "error" | "skipped"
    time: float
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "classname": self.classname,
            "outcome": self.outcome,
            "time": self.time,
            "message": self.message,
        }


@dataclass(frozen=True)
class ReportDetail:
    """Summary plus per-case rows -- the detail view's payload.

    ``alerts``: the run's email-notification history (oldest first) from the
    ``meta.json`` sidecar; each entry has ``at``/``kind``/``recipients``/``ok``/``manual``.
    """

    summary: ReportSummary
    cases: tuple[CaseView, ...] = field(default_factory=tuple)
    alerts: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = self.summary.to_dict()
        data["cases"] = [c.to_dict() for c in self.cases]
        data["alerts"] = list(self.alerts)
        return data
