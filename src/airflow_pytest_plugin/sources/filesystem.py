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

"""Filesystem-backed report source."""

from __future__ import annotations

import io
import json
import logging
import math
import os
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

from airflow_pytest_operator import JUnitResultParser

from ..config import get_reports_root, get_scan_cache_ttl, get_success_threshold
from ..layout import ALLURE_DIRNAME, META_FILENAME, REPORT_FILENAME, ReportLayout
from ..models import (
    CaseView,
    ReportDetail,
    ReportRef,
    ReportSummary,
    run_succeeds,
)
from .base import ReportSource

try:  # prefer the hardened parser (matches the operator)
    from defusedxml.ElementTree import parse as _xml_parse

    _SECURE_XML = True
except Exception:  # pragma: no cover - fallback path
    from xml.etree.ElementTree import parse as _xml_parse

    _SECURE_XML = False

_log = logging.getLogger(__name__)

#: Cap one case's captured output so a pathological report can't bloat a response.
_MAX_OUTPUT = 16000


class FileSystemReportSource(ReportSource):
    """Read archived reports from a directory tree on disk."""

    def __init__(
        self,
        *,
        report_root: str | None = None,
        layout: ReportLayout | None = None,
        parser: JUnitResultParser | None = None,
        scan_cache_ttl: float | None = None,
    ) -> None:
        self._report_root = os.path.abspath(report_root or get_reports_root())
        self._layout = layout or ReportLayout()
        self._parser = parser or JUnitResultParser()
        self._scan_ttl = (
            get_scan_cache_ttl() if scan_cache_ttl is None else scan_cache_ttl
        )
        # (monotonic_timestamp, summaries); locked so a cold cache does a single
        # tree walk instead of one per concurrent request (single-flight).
        self._scan_cache: tuple[float, list[ReportSummary]] | None = None
        self._scan_lock = threading.Lock()

    @property
    def report_root(self) -> str:
        return self._report_root

    @property
    def secure_xml(self) -> bool:
        """Whether JUnit XML is parsed with the hardened ``defusedxml`` parser."""
        return _SECURE_XML

    def _scan_disk(self) -> list[ReportSummary]:
        """Walk the tree and build every summary, newest first (uncached)."""
        root = Path(self._report_root)
        if not root.is_dir():
            return []
        out: list[ReportSummary] = []
        threshold = get_success_threshold()  # once per scan
        for meta_file in root.rglob(META_FILENAME):
            meta = self._load_meta(meta_file)
            if meta is None:
                continue
            summary = self._summary_from_meta(meta, threshold)
            if summary is not None:
                out.append(summary)
        # Newest first: ISO-8601 created_at sorts chronologically; missing sorts last.
        # Deterministic tiebreak (try_number, run_id, map_index) picks a stable "latest"
        # on equal/missing created_at -- e.g. a retry wins over its earlier try.
        out.sort(
            key=lambda s: (
                s.created_at or "",
                s.ref.try_number,
                s.ref.run_id,
                s.ref.map_index,
            ),
            reverse=True,
        )
        return out

    def _all_summaries(self) -> list[ReportSummary]:
        """Full scan, reused within the TTL so a page's several summary endpoints
        share one tree walk. ``ttl <= 0`` disables caching."""
        if self._scan_ttl <= 0:
            return self._scan_disk()
        cached = self._scan_cache
        if cached is not None and (time.monotonic() - cached[0]) < self._scan_ttl:
            return cached[1]
        with self._scan_lock:
            # Re-check: another thread may have refreshed while we waited on the lock.
            cached = self._scan_cache
            if cached is not None and (time.monotonic() - cached[0]) < self._scan_ttl:
                return cached[1]
            fresh = self._scan_disk()
            self._scan_cache = (time.monotonic(), fresh)
            return fresh

    def _invalidate_scan(self) -> None:
        self._scan_cache = None

    def list_summaries(
        self,
        *,
        dag_id: str | None = None,
        run_id: str | None = None,
    ) -> list[ReportSummary]:
        d = dag_id.lower() if dag_id else None
        r = run_id.lower() if run_id else None
        summaries = self._all_summaries()
        # Filter into a fresh list -- never hand back the cached one.
        return [
            s
            for s in summaries
            if (not d or d in s.ref.dag_id.lower())
            and (not r or r in s.ref.run_id.lower())
        ]

    def get_detail(self, ref: ReportRef) -> ReportDetail | None:
        # Token is attacker-controlled: bound the directory before reading.
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return None
        report_path = os.path.join(report_dir, REPORT_FILENAME)
        if not os.path.exists(report_path):
            return None

        # Prefer stored counts; success is re-derived from the pass-rate threshold.
        threshold = get_success_threshold()
        meta = self._load_meta(Path(os.path.join(report_dir, META_FILENAME)))
        summary = self._summary_from_meta(meta, threshold) if meta is not None else None

        try:
            result = self._parser.parse(report_path)
        except Exception:
            _log.exception("Failed to parse JUnit report %s", report_path)
            return None

        if summary is None:
            summary = ReportSummary(
                ref=ref,
                total=result.total,
                passed=result.passed,
                failed=result.failed,
                skipped=result.skipped,
                errors=result.errors,
                duration=result.duration,
                success=run_succeeds(
                    result.passed, result.failed, result.errors, threshold
                ),
                created_at=None,
            )

        # The parser keeps only the short message; read the XML for full per-case output.
        outputs = self._case_outputs(report_path)
        cases = tuple(
            CaseView(
                node_id=c.node_id,
                name=c.name,
                classname=c.classname,
                outcome=c.outcome,
                time=c.time,
                message=outputs.get((c.classname, c.name), c.message),
            )
            for c in result.cases
        )
        return ReportDetail(
            summary=summary, cases=cases, alerts=_alerts_from_meta(meta)
        )

    def test_outcomes(self, ref: ReportRef) -> dict[str, dict[str, Any]] | None:
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return None
        meta = self._load_meta(Path(os.path.join(report_dir, META_FILENAME)))
        rows = meta.get("tests") if isinstance(meta, dict) else None
        if isinstance(rows, list):
            out: dict[str, dict[str, Any]] = {}
            for row in rows:
                if isinstance(row, (list, tuple)) and len(row) >= 2 and row[0]:
                    dur = (
                        float(row[2])
                        if len(row) > 2 and isinstance(row[2], int | float)
                        else 0.0
                    )
                    # Guard NaN/Infinity from corrupt meta: json.dumps emits them
                    # non-spec, so they must not reach a JSON response.
                    if not math.isfinite(dur):
                        dur = 0.0
                    out[str(row[0])] = {"outcome": str(row[1]), "duration": dur}
            return out
        # Older archive lacking the per-test map: parse junit.xml on demand.
        report_path = os.path.join(report_dir, REPORT_FILENAME)
        if not os.path.isfile(report_path):
            return None
        try:
            result = self._parser.parse(report_path)
        except Exception:
            _log.exception("Failed to parse JUnit report %s", report_path)
            return None

        def _dur(c: Any) -> float:
            d = float(getattr(c, "time", 0.0) or 0.0)
            return d if math.isfinite(d) else 0.0

        return {
            c.node_id: {"outcome": c.outcome, "duration": _dur(c)} for c in result.cases
        }

    def delete(self, ref: ReportRef) -> bool:
        target = self._safe_dir(ref)
        if target is None or not os.path.isdir(target):
            return False
        shutil.rmtree(target, ignore_errors=True)
        # Remove now-empty ancestors so the tree doesn't accumulate orphan dirs.
        self._prune_empty_parents(
            os.path.dirname(target), os.path.realpath(self._report_root)
        )
        self._invalidate_scan()  # deleted run must drop out of the list at once
        _log.info("Deleted report %s", target)
        return True

    def record_alert(self, ref: ReportRef, entry: dict[str, Any]) -> bool:
        """Append one sanitized email-notification record to the run's ``meta.json``.

        Best-effort and bounded: the entry is reduced to known fields, history is capped
        at the newest ``_ALERTS_CAP`` (so repeated sends can't grow the sidecar without
        limit), and the write is atomic (tmp + ``os.replace``) so a concurrent scan never
        sees a half-written file. Never raises on storage problems.
        """
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return False
        meta_file = Path(os.path.join(report_dir, META_FILENAME))
        meta = self._load_meta(meta_file)
        if meta is None:
            return False
        try:
            history = [a for a in meta.get("alerts", []) if isinstance(a, dict)]
            history.append(_sanitize_alert_entry(entry))
            meta["alerts"] = history[-_ALERTS_CAP:]
            # Unique tmp name (uuid, not pid): two threads writing the same run's history
            # must not share a tmp file and clobber each other.
            tmp = f"{meta_file}.{uuid.uuid4().hex}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False)
            os.replace(tmp, meta_file)
            return True
        except Exception:
            _log.exception("Failed to record an alert in %s", meta_file)
            return False

    def report_size(self, ref: ReportRef) -> int:
        """Total bytes of the report's directory (``0`` if it resolves nowhere)."""
        target = self._safe_dir(ref)
        if target is None or not os.path.isdir(target):
            return 0
        total = 0
        for base, _dirs, names in os.walk(target):
            for name in names:
                try:
                    total += os.path.getsize(os.path.join(base, name))
                except OSError:  # a file vanished mid-walk; skip it
                    continue
        return total

    def _safe_dir(self, ref: ReportRef) -> str | None:
        """The report dir for ``ref`` if it resolves under the root, else ``None``.

        Token is attacker-controlled: resolve real paths (``..``, symlinks) and refuse any
        escape -- the boundary both reads and deletes rely on.
        """
        root = os.path.realpath(self._report_root)
        target = os.path.realpath(self._layout.dir_for(self._report_root, ref))
        if target != root and target.startswith(root + os.sep):
            return target
        _log.warning("Refusing report path outside the report root: %r", target)
        return None

    def allure_archive(
        self, ref: ReportRef, *, max_bytes: int | None = None
    ) -> bytes | None:
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return None
        allure_dir = os.path.join(report_dir, ALLURE_DIRNAME)
        files = [
            os.path.join(base, name)
            for base, _dirs, names in os.walk(allure_dir)
            for name in names
        ]
        if not files:
            return None
        # ``max_bytes`` (the email path) bounds peak memory: if raw results exceed the
        # budget, skip building the zip in RAM -- the caller sends without it.
        if max_bytes is not None:
            raw = 0
            for full in files:
                try:
                    raw += os.path.getsize(full)
                except OSError:  # a file vanished mid-walk; ignore it
                    continue
                if raw > max_bytes:
                    return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for full in files:
                zf.write(full, os.path.relpath(full, allure_dir))
        return buf.getvalue()

    @staticmethod
    def _prune_empty_parents(start: str, root: str) -> None:
        cur = os.path.realpath(start)
        while cur != root and cur.startswith(root + os.sep):
            try:
                os.rmdir(cur)  # raises if the directory is not empty
            except OSError:
                break
            cur = os.path.dirname(cur)

    # -- internals -------------------------------------------------------

    @staticmethod
    def _case_outputs(report_path: str) -> dict[tuple[str, str], str]:
        """Map ``(classname, name) -> full captured output`` from the XML (best-effort)."""
        try:
            tree = _xml_parse(report_path)
        except Exception:
            return {}
        root = tree.getroot()
        suites = list(root.iter("testsuite")) if root.tag == "testsuites" else [root]
        out: dict[tuple[str, str], str] = {}
        for suite in suites:
            for tc in suite.findall("testcase"):
                sections: list[str] = []
                # Element truthiness is child-based, so test ``is not None`` explicitly.
                for tag in ("failure", "error", "skipped"):
                    node = tc.find(tag)
                    if node is None:
                        continue
                    parts = [
                        p for p in (node.get("message"), (node.text or "").strip()) if p
                    ]
                    body = "\n".join(parts).strip()
                    if body:
                        sections.append(body)
                    break
                # Captured logs -- present even for passed tests under junit_logging=all.
                for tag, label in (
                    ("system-out", "Captured stdout / log"),
                    ("system-err", "Captured stderr"),
                ):
                    node = tc.find(tag)
                    body = (node.text or "").strip() if node is not None else ""
                    if body:
                        sections.append(f"--- {label} ---\n{body}")
                if not sections:
                    continue
                text = "\n\n".join(sections)
                if len(text) > _MAX_OUTPUT:
                    text = text[:_MAX_OUTPUT] + "\n…(truncated)"
                out[(tc.get("classname", ""), tc.get("name", ""))] = text
        return out

    @staticmethod
    def _load_meta(meta_file: Path) -> dict[str, Any] | None:
        try:
            with meta_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            _log.warning("Skipping unreadable %s: %s", meta_file, exc)
            return None
        if not isinstance(data, dict):
            _log.warning("Skipping %s: not a JSON object", meta_file)
            return None
        return data

    @staticmethod
    def _summary_from_meta(
        meta: dict[str, Any], threshold: float
    ) -> ReportSummary | None:
        try:
            ref = ReportRef(
                dag_id=str(meta["dag_id"]),
                run_id=str(meta["run_id"]),
                task_id=str(meta["task_id"]),
                try_number=int(meta["try_number"]),
                map_index=int(meta.get("map_index", -1)),
            )
        except (KeyError, ValueError, TypeError):
            _log.warning("Skipping meta with missing/invalid identity: %r", meta)
            return None

        # Counts/duration come from a semi-trusted sidecar (written by the operator's test
        # code). One corrupt value (non-numeric count, inf/NaN duration) must NOT crash the
        # scan or leak non-spec JSON -- coerce defensively and keep the run, mirroring the
        # identity skip above and test_outcomes' finite guard.
        summary = meta.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        passed = _safe_int(summary.get("passed"))
        failed = _safe_int(summary.get("failed"))
        errors = _safe_int(summary.get("errors"))
        return ReportSummary(
            ref=ref,
            total=_safe_int(summary.get("total")),
            passed=passed,
            failed=failed,
            skipped=_safe_int(summary.get("skipped")),
            errors=errors,
            duration=_safe_finite_float(summary.get("duration")),
            # success is reader-derived from the pass-rate threshold, not the stored flag.
            success=run_succeeds(passed, failed, errors, threshold),
            created_at=_opt_str(meta.get("created_at")),
            logical_date=_opt_str(meta.get("logical_date")),
            has_allure=bool(meta.get("allure")),
        )


#: Newest email-notification records kept per run (older ones are dropped on append).
_ALERTS_CAP = 50


def _sanitize_alert_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Reduce an alert record to its known, bounded fields -- never trust the caller."""
    recipients = entry.get("recipients") or []
    if not isinstance(recipients, (list, tuple)):
        recipients = []
    return {
        "at": str(entry.get("at") or "")[:64],
        "kind": str(entry.get("kind") or "")[:32],
        "recipients": [str(r)[:200] for r in list(recipients)[:20]],
        "ok": bool(entry.get("ok")),
        "manual": bool(entry.get("manual")),
    }


def _alerts_from_meta(meta: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    """The sanitized alert history stored in a run's meta (empty when absent/corrupt)."""
    if not isinstance(meta, dict) or not isinstance(meta.get("alerts"), list):
        return ()
    return tuple(
        _sanitize_alert_entry(a)
        for a in meta["alerts"][-_ALERTS_CAP:]
        if isinstance(a, dict)
    )


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _safe_int(value: Any) -> int:
    """A summary count coerced to a non-negative int; ``0`` for anything unparseable."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_finite_float(value: Any) -> float:
    """A summary duration coerced to a finite float; ``0.0`` for bad/inf/NaN values
    (non-finite floats aren't JSON-spec and would 500 the serializer)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0
