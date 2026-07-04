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

"""Retention: delete old archived runs by age / count / size.

Split so the decision stays pure and testable, apart from the I/O:

- ``RetentionPolicy`` — value object (limits, ``from_config``).
- ``select_expired`` — pure: run facts + policy -> which runs to delete.
- ``prune`` — orchestrator: list + measure via a ``ReportSource``, then delete.

Every policy **always keeps the newest run of each dag·task**, so a task's latest
result never disappears.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .config import (
    get_retention_max_age_days,
    get_retention_max_runs,
    get_retention_max_total_mb,
)
from .models import ReportRef

if TYPE_CHECKING:
    from .sources import ReportSource

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention limits; ``None`` on a field means that dimension is unbounded."""

    max_age_days: int | None = None
    max_runs_per_task: int | None = None
    max_total_bytes: int | None = None

    def __post_init__(self) -> None:
        # A non-positive limit would break the keep-newest invariant
        # (e.g. max_runs_per_task=0 would mark a group's newest run).
        for name in ("max_age_days", "max_runs_per_task", "max_total_bytes"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(
                    f"{name} must be a positive int or None, got {value!r}"
                )

    @property
    def is_active(self) -> bool:
        """True if any limit is set; an inactive policy deletes nothing."""
        return any(
            v is not None
            for v in (self.max_age_days, self.max_runs_per_task, self.max_total_bytes)
        )

    @property
    def needs_sizes(self) -> bool:
        """True if evaluation needs report sizes measured (the size policy)."""
        return self.max_total_bytes is not None

    @classmethod
    def from_config(cls) -> RetentionPolicy:
        """Build from env vars / Airflow cfg (all opt-in; default = keep all)."""
        mb = get_retention_max_total_mb()
        return cls(
            max_age_days=get_retention_max_age_days(),
            max_runs_per_task=get_retention_max_runs(),
            max_total_bytes=mb * 1024 * 1024 if mb is not None else None,
        )


@dataclass(frozen=True)
class RunEntry:
    """What ``select_expired`` needs to know about one run -- no I/O."""

    ref: ReportRef
    created_at: str | None  # ISO-8601, as stored in meta.json
    size: int = 0  # bytes; 0 unless the size policy needs it


@dataclass(frozen=True)
class RetentionResult:
    """What a prune did (or would do, under ``dry_run``)."""

    deleted: tuple[str, ...]  # tokens of the (would-be-)deleted runs
    freed_bytes: int
    scanned: int
    dry_run: bool

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deleted": list(self.deleted),
            "deleted_count": self.deleted_count,
            "freed_bytes": self.freed_bytes,
            "scanned": self.scanned,
            "dry_run": self.dry_run,
        }


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO timestamp to an aware datetime (naive -> UTC), else None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def select_expired(
    entries: list[RunEntry], policy: RetentionPolicy, *, now: datetime
) -> list[ReportRef]:
    """Pure decision: which runs to delete under ``policy`` as of ``now``.

    Never selects a dag·task's newest run. Age and count act per dag·task; size
    trims oldest-first across all tasks until the tree fits the budget. The
    dimensions combine as a union.
    """
    if not policy.is_active:
        return []

    groups: dict[tuple[str, str], list[RunEntry]] = {}
    for entry in entries:
        groups.setdefault((entry.ref.dag_id, entry.ref.task_id), []).append(entry)
    for group in groups.values():
        group.sort(key=lambda e: e.created_at or "", reverse=True)  # newest first

    marked: dict[str, RunEntry] = {}  # token -> entry; dedups, keeps insertion order

    def mark(entry: RunEntry) -> None:
        marked.setdefault(entry.ref.token, entry)

    # Count: keep only the newest N per dag·task.
    if policy.max_runs_per_task is not None:
        for group in groups.values():
            for entry in group[policy.max_runs_per_task :]:
                mark(entry)

    # Age: drop runs past the cutoff, but never a group's newest (hence group[1:]).
    if policy.max_age_days is not None:
        cutoff = now - timedelta(days=policy.max_age_days)
        for group in groups.values():
            for entry in group[1:]:
                dt = _parse_dt(entry.created_at)
                if dt is not None and dt < cutoff:
                    mark(entry)

    # Size: while the tree exceeds the budget, delete oldest-first (never a
    # group's newest) until it fits or only protected runs remain.
    if policy.max_total_bytes is not None:
        remaining = sum(e.size for e in entries) - sum(e.size for e in marked.values())
        if remaining > policy.max_total_bytes:
            candidates = [e for group in groups.values() for e in group[1:]]
            candidates.sort(key=lambda e: e.created_at or "")  # oldest first
            for entry in candidates:
                if remaining <= policy.max_total_bytes:
                    break
                if entry.ref.token in marked:
                    continue
                mark(entry)
                remaining -= entry.size

    return [entry.ref for entry in marked.values()]


def prune(
    source: ReportSource,
    policy: RetentionPolicy | None = None,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
) -> RetentionResult:
    """Apply ``policy`` (default: from config) to ``source``, deleting expired runs.

    Under ``dry_run`` nothing is deleted, but the result still lists what would go.
    Pass ``now`` for deterministic age handling; defaults to the current UTC time.
    """
    resolved = policy if policy is not None else RetentionPolicy.from_config()
    if not resolved.is_active:
        return RetentionResult(deleted=(), freed_bytes=0, scanned=0, dry_run=dry_run)

    entries = [
        RunEntry(
            ref=s.ref,
            created_at=s.created_at,
            size=source.report_size(s.ref) if resolved.needs_sizes else 0,
        )
        for s in source.list_summaries()
    ]
    when = now if now is not None else datetime.now(timezone.utc)
    to_delete = select_expired(entries, resolved, now=when)

    sizes = {e.ref.token: e.size for e in entries}
    freed = sum(sizes.get(ref.token, 0) for ref in to_delete)
    if not dry_run:
        for ref in to_delete:
            source.delete(ref)

    _log.info(
        "retention: %s %d of %d run(s), %d bytes (dry_run=%s)",
        "would delete" if dry_run else "deleted",
        len(to_delete),
        len(entries),
        freed,
        dry_run,
    )
    return RetentionResult(
        deleted=tuple(ref.token for ref in to_delete),
        freed_bytes=freed,
        scanned=len(entries),
        dry_run=dry_run,
    )


def prune_reports(
    policy: RetentionPolicy | None = None,
    *,
    source: ReportSource | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> RetentionResult:
    """Entry point for a scheduled maintenance task (e.g. a ``PythonOperator``).

    Defaults to the filesystem source and the config policy, so a bare
    ``prune_reports`` callable Just Works once the env/cfg limits are set.
    """
    if source is None:
        from .sources import FileSystemReportSource

        source = FileSystemReportSource()
    return prune(source, policy, now=now, dry_run=dry_run)
