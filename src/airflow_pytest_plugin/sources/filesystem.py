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
import re
import shutil
import stat
import threading
import time
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any, cast

from airflow_pytest_operator import JUnitResultParser

from ..config import get_reports_root, get_scan_cache_ttl, get_success_threshold
from ..layout import (
    ALLURE_DIRNAME,
    META_FILENAME,
    REPORT_FILENAME,
    VERDICTS_FILENAME,
    ReportLayout,
)
from ..models import (
    CaseView,
    ReportDetail,
    ReportRef,
    ReportSummary,
    Verdict,
    run_succeeds,
)
from ..triage import (
    CATEGORIES,
    canonical_node_key,
    triage_rollup,
    triage_view,
    verdicts_from_document,
)
from ..triage import (
    label as triage_label,
)
from .base import ReportSource

try:  # prefer the hardened parser (matches the operator)
    from defusedxml.ElementTree import parse as _xml_parse

    _SECURE_XML = True
except Exception:  # pragma: no cover - fallback path
    from xml.etree.ElementTree import parse as _xml_parse

    _SECURE_XML = False

_log = logging.getLogger(__name__)

#: Cap one case's failure text and captured output (each) so a pathological report can't
#: bloat a response. A test that logs a megabyte is exactly when the viewer must stay usable.
#:
#: All three caps are in UTF-8 BYTES, which is what the response is measured in. Counting
#: Python characters instead lets any non-ASCII text through at up to four times the limit
#: -- a suite printing emoji stayed inside a 2,000,000-"character" budget while sending
#: 8 MB, and the same trick works with Cyrillic or CJK at 2x-3x.
_MAX_OUTPUT = 16000
#: Caps on a WHOLE run's text. The per-case cap still multiplies by the number of tests:
#: 2,000 tests at 16KB each would be a 32MB JSON response either way, which is why the
#: diagnosis gets its own, larger budget rather than none at all.
_MAX_RUN_OUTPUT = 2_000_000
_MAX_RUN_FAILURES = 4_000_000
#: Shown for the cases past those budgets, so a test that printed something -- or broke --
#: is never rendered as one that did neither.
_OUTPUT_BUDGET_SPENT = (
    "…(output omitted: this run's captured output exceeded the limit)"
)
_FAILURE_BUDGET_SPENT = (
    "…(traceback omitted: this run's failure text exceeded the limit)"
)
#: pytest's banner around a captured stream: ``------- Captured Log -------``.
_CAPTURE_RULE = re.compile(r"^-{3,}\s*(Captured [^-]*?)\s*-{3,}$")


def _cap(text: str, limit: int = -1) -> tuple[str, int]:
    """Truncate one block to ``limit`` UTF-8 bytes; return it and the bytes it costs.

    Never splits a character: the tail of a clipped multi-byte sequence is dropped rather
    than emitted as a replacement glyph. ``limit`` defaults to :data:`_MAX_OUTPUT`.
    """
    if not text:
        return "", 0
    cap = _MAX_OUTPUT if limit < 0 else limit
    raw = text.encode("utf-8")
    if len(raw) <= cap:
        return text, len(raw)
    clipped = raw[:cap].decode("utf-8", "ignore") + "\n…(truncated)"
    return clipped, len(clipped.encode("utf-8"))


#: Cap on a run's verdicts sidecar before it is parsed. The producer's own caps put the
#: worst case near 500KB (200 verdicts x two 1000-char fields); anything far past that was
#: not written by us, and this parse happens inside the api-server on every detail request.
_MAX_VERDICTS_BYTES = 4 * 1024 * 1024


class _ZipSink:
    """A write-only file-like ``zipfile`` can target, drained as it fills.

    Has no ``tell``/``seek``, so ``zipfile`` treats it as a non-seekable stream and emits
    data descriptors instead of rewriting sizes into the local headers -- which is what
    lets the archive be produced and sent without ever existing in full.
    """

    def __init__(self) -> None:
        self.buf = bytearray()

    def write(self, data: bytes) -> int:
        self.buf += data
        return len(data)

    def flush(self) -> None:  # zipfile calls this on close
        return None

    def close(self) -> None:
        # Nothing to release: the buffer is drained by the generator, and closing must not
        # discard bytes zipfile has already written (the central directory lands here).
        return None


def _safe_allure_files(allure_dir: str) -> list[str]:
    """Candidate entries under ``allure_dir``. Safety is enforced when each is OPENED.

    Listing alone can't be trusted: results are written on the worker by arbitrary pytest
    code, which can swap an entry between the check and the read. :func:`_open_allure_file`
    is therefore the authority -- this only enumerates. ``os.walk`` does not descend into
    symlinked directories, so a linked tree contributes nothing either way.
    """
    return [
        os.path.join(base, name)
        for base, _dirs, names in os.walk(allure_dir)
        for name in names
    ]


def open_archived_file(path: str, kind: str, *, mode: str = "rb") -> IO[Any] | None:
    """Open a file the WORKER wrote inside a run's archive, or ``None`` if it isn't safe to.

    Every one of these is named by us but created by arbitrary pytest code on the worker,
    so the same three hazards apply to all of them -- Allure results, the verdicts sidecar,
    anything added later. All are closed atomically at ``open`` rather than by a prior check
    an attacker could invalidate in between:

    * ``O_NOFOLLOW`` -- a symlink is never followed, so a test cannot point an entry at the
      Fernet key or ``/etc/passwd`` and have the reader read it out. This also removes the
      swap-after-validation race entirely: there is no window to swap into.
    * ``O_NONBLOCK`` + ``S_ISREG`` -- a FIFO would otherwise block ``open`` FOREVER waiting
      for a writer, pinning a server thread per request; devices and sockets are refused for
      the same reason. Non-blocking has no effect on the regular files we keep.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError:  # symlink (ELOOP), vanished, or unreadable
        _log.warning(
            "skipping %s that is a link or unreadable: %s",
            kind,
            " ".join(str(path).split())[:200],
        )
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            _log.warning(
                "skipping non-regular %s (fifo/device/socket): %s",
                kind,
                " ".join(str(path).split())[:200],
            )
            os.close(fd)
            return None
        return os.fdopen(fd, mode, encoding=None if "b" in mode else "utf-8")
    except OSError:
        os.close(fd)
        return None


def _open_allure_file(path: str) -> IO[bytes] | None:
    """One Allure result, opened under the archive-file guarantees above."""
    handle = open_archived_file(path, "Allure entry")
    return cast("IO[bytes] | None", handle)


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

        # The parser keeps only the short message; read the XML for the full traceback and
        # whatever the test printed or logged.
        details = self._case_details(report_path)
        # AI verdicts are keyed by the canonical dotted node id, which is the form the JUnit
        # parser already reconstructs -- re-canonicalizing here costs nothing and keeps the
        # join working for a source whose cases arrive in pytest's native slash form.
        rollup = triage_rollup(meta)
        verdicts = self._load_verdicts(report_dir, rollup) if rollup is not None else {}
        cases = tuple(
            CaseView(
                node_id=c.node_id,
                name=c.name,
                classname=c.classname,
                outcome=c.outcome,
                time=c.time,
                message=details.get((c.classname, c.name), (c.message or "", ""))[0]
                or c.message,
                output=details.get((c.classname, c.name), ("", ""))[1] or None,
                verdict=verdicts.get(canonical_node_key(c.node_id)),
            )
            for c in result.cases
        )
        return ReportDetail(
            summary=summary,
            cases=cases,
            alerts=_alerts_from_meta(meta),
            coverage=_coverage_from_meta(meta),
            coverage_threshold=_coverage_threshold_from_meta(meta),
            # Summarised over the verdicts actually attached, so the run-level card can
            # never advertise a category the case table has no row for.
            triage=triage_view(rollup, [c.verdict for c in cases if c.verdict]),
        )

    def verdicts(self, ref: ReportRef) -> dict[str, Verdict]:
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return {}
        # verdicts.json first, and usually last: it is self-sufficient. Reading meta.json
        # here as well would double the parse for every run of a heatmap window -- and that
        # file, not this one, is the expensive read (it carries a row per test). Measured at
        # 100 runs x 300 tests: 14ms -> 26ms. Only an archive written before the split, which
        # keeps its verdicts inline in the roll-up, pays for the meta parse -- and it is the
        # sidecar's PRESENCE that decides, not its contents: a triaged run with nothing to
        # judge has an empty one, and reading meta for it would put the cost right back.
        if os.path.exists(os.path.join(report_dir, VERDICTS_FILENAME)):
            return self._load_verdicts(report_dir, None)
        rollup = triage_rollup(
            self._load_meta(Path(os.path.join(report_dir, META_FILENAME)))
        )
        return self._load_verdicts(report_dir, rollup) if rollup else {}

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
        """Remove one run's directory. ``True`` only when it is really gone.

        Storage errors are reported, not swallowed: the viewer drops a deleted run from
        the list, and a delete that silently failed would leave the user believing space
        was reclaimed while the files stay behind -- on a read-only mount or an NFS share
        that lost its lock, for every run they picked. A partial ``rmtree`` also counts as
        a failure, since what is left behind is a truncated run.
        """
        target = self._safe_dir(ref)
        if target is None or not os.path.isdir(target):
            return False
        failure: OSError | None = None
        try:
            shutil.rmtree(target)
        except OSError as exc:
            # Logged below, and only if it mattered: two callers deleting the same run --
            # a retention sweep while someone clicks delete -- race here constantly, and
            # the loser's FileNotFoundError is a non-event, not a page of traceback.
            failure = exc
        # The tree walk can fail per entry, so confirm rather than trust the return.
        if os.path.exists(target):
            self._invalidate_scan()  # a partial delete still changed the run
            # rmtree is not atomic: by the time it hits an entry it may not remove, it has
            # already unlinked the rest. Saying only "storage refused" would leave an
            # operator looking for a run that no longer exists -- the two outcomes need
            # different actions, so name which one happened.
            if os.path.exists(os.path.join(target, META_FILENAME)):
                _log.error(
                    "Report %s still exists after delete: storage refused the removal "
                    "and the run is intact",
                    target,
                    exc_info=failure,
                )
            else:
                _log.error(
                    "Report %s was only partially deleted: storage refused part of the "
                    "removal and the run is no longer readable. Its directory is now "
                    "invisible to the viewer and to retention -- remove it by hand",
                    target,
                    exc_info=failure,
                )
            return False
        if failure is not None:
            # Gone, but not by us: another deleter finished first. Nothing to report.
            _log.debug("Report %s vanished while being deleted: %s", target, failure)
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

    def record_coverage(self, ref: ReportRef, coverage: float) -> bool:
        """Bake a run's overall coverage fraction into its ``meta.json`` (idempotent).

        Called once by the reader when it first pulls coverage from the operator's XCom,
        so the value becomes a persistent part of the report (shown immediately on every
        later view, no XCom round-trip). Atomic write like :meth:`record_alert`; never
        raises on storage problems.
        """
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return False
        meta_file = Path(os.path.join(report_dir, META_FILENAME))
        meta = self._load_meta(meta_file)
        if meta is None:
            return False
        try:
            meta["coverage"] = float(coverage)
            tmp = f"{meta_file}.{uuid.uuid4().hex}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False)
            os.replace(tmp, meta_file)
            return True
        except Exception:
            _log.exception("Failed to record coverage in %s", meta_file)
            return False

    def exists(self, ref: ReportRef) -> bool:
        """Whether the run's directory is still there (one stat, no parsing)."""
        target = self._safe_dir(ref)
        return target is not None and os.path.isdir(target)

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
        files = _safe_allure_files(allure_dir)
        if not files:
            return None
        # ``max_bytes`` (the email path) bounds peak memory: if raw results exceed the
        # budget, skip building the zip in RAM -- the caller sends without it.
        if max_bytes is not None:
            raw = 0
            for full in files:
                try:
                    # lstat, not getsize: a symlink's own size, never its target's, so a
                    # link to a huge file can't slip past the budget.
                    raw += os.lstat(full).st_size
                except OSError:  # a file vanished mid-walk; ignore it
                    continue
                if raw > max_bytes:
                    return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for full in files:
                # Same guarantees as the streamed path: never follow a link, never open a
                # fifo/device. zf.write() would do both, so read through our own handle.
                src = _open_allure_file(full)
                if src is None:
                    continue
                with src, zf.open(os.path.relpath(full, allure_dir), "w") as dest:
                    shutil.copyfileobj(src, dest, 65536)
        return buf.getvalue()

    def allure_stream(
        self, ref: ReportRef, *, chunk_size: int = 65536
    ) -> Iterator[bytes] | None:
        """Stream the run's Allure zip, compressed straight into the response, not built in RAM.

        The in-memory :meth:`allure_archive` holds the whole archive per request, so a few
        concurrent downloads of a large results tree multiply into gigabytes inside the
        Airflow api-server -- which serves the rest of Airflow too. Compressing into a
        drained sink and yielding chunks (never a temp file -- see :meth:`_zip_chunks`) keeps
        peak memory flat and independent of both the archive size and the number of downloads
        in flight.
        """
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return None
        allure_dir = os.path.join(report_dir, ALLURE_DIRNAME)
        files = _safe_allure_files(allure_dir)
        if not files:
            return None
        return self._zip_chunks(files, allure_dir, chunk_size)

    @staticmethod
    def _zip_chunks(
        files: list[str], allure_dir: str, chunk_size: int
    ) -> Iterator[bytes]:
        """Compress straight into the response, holding at most a chunk or two at a time.

        Deliberately NOT staged through a temp file: ``/tmp`` is a RAM-backed tmpfs on many
        container images (and on a Kubernetes ``emptyDir: {medium: Memory}``), which would
        quietly put the archive back in memory -- the very thing this avoids. ``zipfile``
        accepts a write-only sink and switches to data descriptors for it, which every
        mainstream unzip reads.
        """
        sink = _ZipSink()

        def drain(final: bool = False) -> Iterator[bytes]:
            while len(sink.buf) >= chunk_size or (final and sink.buf):
                out = bytes(sink.buf[:chunk_size])
                del sink.buf[:chunk_size]
                yield out

        with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as zf:
            for full in files:
                arcname = os.path.relpath(full, allure_dir)
                src = _open_allure_file(full)
                if src is None:  # link, fifo/device, vanished mid-walk: skip it
                    continue
                # force_zip64: the member size is unknown when the header goes out, so
                # zipfile would otherwise decide "no zip64" and then raise past ~2 GiB --
                # mid-stream, after bytes are already on the wire. Costs 20 bytes/entry.
                with src, zf.open(arcname, "w", force_zip64=True) as dest:
                    while True:
                        piece = src.read(chunk_size)
                        if not piece:
                            break
                        dest.write(piece)
                        yield from drain()  # keep the sink from growing with the file
                yield from drain()
        yield from drain(final=True)  # the central directory written on close

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
    def _clean_capture(text: str) -> str:
        """Trim pytest's banner rules out of a captured stream.

        pytest brackets each stream with a full-width rule
        (``------- Captured Log -------``). The viewer gives the block its own heading, so
        the rule is redundant width -- on a phone it is the widest line on the page. The
        stream NAME is kept: one ``system-out`` can hold both log and stdout, and the
        boundary between them is the only thing separating them.
        """
        # [heading or None, body lines] per stream. pytest emits a rule for every stream it
        # was asked to capture, including the ones nothing wrote to -- a heading with an
        # empty body under it is noise the reader has to scroll past on every single test.
        sections: list[tuple[str | None, list[str]]] = [(None, [])]
        for line in text.splitlines():
            m = _CAPTURE_RULE.match(line)
            if m:
                sections.append((f"--- {m.group(1).strip()} ---", []))
            else:
                sections[-1][1].append(line)
        kept: list[str] = []
        for heading, body in sections:
            if not any(ln.strip() for ln in body):
                continue
            if heading:
                kept.append(heading)
            kept.append("\n".join(body).strip("\n"))
        return "\n".join(kept).strip()

    @classmethod
    def _case_details(cls, report_path: str) -> dict[tuple[str, str], tuple[str, str]]:
        """Map ``(classname, name) -> (failure text, captured output)`` (best-effort).

        Kept apart on purpose: the failure is the diagnosis and the capture is the
        evidence, they are read in that order, and only the first should decide how
        failures cluster.

        Both halves are bounded twice: :data:`_MAX_OUTPUT` per case, and a run-wide budget
        (:data:`_MAX_RUN_OUTPUT` / :data:`_MAX_RUN_FAILURES`). The per-case cap alone still
        multiplies by the number of tests, so without the second one a chatty suite -- or a
        suite that broke wide -- is a JSON response of tens of megabytes for the browser to
        hold. The diagnosis gets the larger budget and is spent last.
        """
        budget = _MAX_RUN_OUTPUT
        fail_budget = _MAX_RUN_FAILURES
        try:
            tree = _xml_parse(report_path)
        except Exception:
            return {}
        root = tree.getroot()
        suites = list(root.iter("testsuite")) if root.tag == "testsuites" else [root]
        out: dict[tuple[str, str], tuple[str, str]] = {}
        for suite in suites:
            for tc in suite.findall("testcase"):
                failure = ""
                # Element truthiness is child-based, so test ``is not None`` explicitly.
                for tag in ("failure", "error", "skipped"):
                    node = tc.find(tag)
                    if node is None:
                        continue
                    parts = [
                        p for p in (node.get("message"), (node.text or "").strip()) if p
                    ]
                    failure = "\n".join(parts).strip()
                    break
                # Captured streams -- present for passed tests too, but only when the run
                # was archived with ``junit_logging`` on (which the parser guarantees).
                sections: list[str] = []
                for tag, label in (
                    ("system-out", "Captured stdout / log"),
                    ("system-err", "Captured stderr"),
                ):
                    node = tc.find(tag)
                    # Slice before cleaning: past the per-case cap the text is discarded
                    # anyway, and splitting a megabyte into lines to throw it away is the
                    # expensive half of parsing a chatty report.
                    raw = (
                        (node.text or "")[: _MAX_OUTPUT + 1] if node is not None else ""
                    )
                    body = cls._clean_capture(raw) if raw.strip() else ""
                    if not body:
                        continue
                    # pytest names each stream itself ("Captured Log", "Captured Out"),
                    # and one system-out can hold both. Adding our own heading on top of
                    # that stacks three titles over one block, so label only what arrived
                    # unlabelled.
                    sections.append(
                        body
                        if body.startswith("--- Captured")
                        else f"--- {label} ---\n{body}"
                    )
                failure, cost = _cap(failure)
                if failure:
                    if fail_budget <= 0:
                        failure = _FAILURE_BUDGET_SPENT
                    elif cost > fail_budget:
                        failure, _ = _cap(failure, fail_budget)
                        fail_budget = 0
                    else:
                        fail_budget -= cost
                captured, cost = _cap("\n\n".join(sections))
                if captured:
                    if budget <= 0:
                        # Say it rather than showing an empty block: a test that printed
                        # something must not look like a test that printed nothing.
                        captured = _OUTPUT_BUDGET_SPENT
                    elif cost > budget:
                        captured, _ = _cap(captured, budget)
                        budget = 0
                    else:
                        budget -= cost
                if not failure and not captured:
                    continue
                out[(tc.get("classname", ""), tc.get("name", ""))] = (failure, captured)
        return out

    @staticmethod
    def _load_verdicts(
        report_dir: str, rollup: dict[str, Any] | None
    ) -> dict[str, Verdict]:
        """The run's per-test AI verdicts from its ``verdicts.json``.

        The file is named by us but written on the worker by the tested project's own
        process, and this parse happens per detail request inside the Airflow api-server --
        so it is opened under the archive-file guarantees (never a symlink, never a FIFO;
        see :func:`open_archived_file`), sized on the descriptor already held rather than on
        the path, and parsed defensively. Falls back to verdicts stored inline in the
        roll-up, which is where archives written before the split keep them.
        """
        path = os.path.join(report_dir, VERDICTS_FILENAME)
        document: Any = None
        handle = open_archived_file(path, VERDICTS_FILENAME, mode="r")
        if handle is not None:
            try:
                with handle:
                    size = os.fstat(handle.fileno()).st_size
                    if size > _MAX_VERDICTS_BYTES:
                        _log.warning(
                            "Ignoring oversized %s (%d bytes) in %s",
                            VERDICTS_FILENAME,
                            size,
                            report_dir,
                        )
                    else:
                        # RecursionError, not ValueError: a nesting bomb ("[[[[…") is how
                        # json.load fails on one, and it would otherwise 500 the endpoint.
                        document = json.load(handle)
            except (OSError, ValueError, RecursionError):
                _log.debug(
                    "No readable %s in %s", VERDICTS_FILENAME, report_dir, exc_info=True
                )
        return verdicts_from_document(document, fallback=rollup)

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
            # A triaged run, even one whose provider produced nothing: the list marks it so
            # "which runs were analysed" is answerable without opening each of them.
            has_triage=isinstance(meta.get("triage"), dict),
            triage=_triage_mix_from_meta(meta),
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


def _unit_fraction(value: Any) -> float | None:
    """``value`` as a 0-1 float, or ``None`` when absent / not a number / out of range."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if 0.0 <= value <= 1.0 else None
    return None


def _triage_mix_from_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """The run's verdict mix for the LIST view, straight from the stored roll-up.

    Deliberately tiny -- categories with a count, plus whether the pass broke. The scan
    parses every run's meta, so anything bigger here is paid on every dashboard load.
    """
    rollup = triage_rollup(meta)
    if rollup is None:
        return None
    raw = rollup.get("counts")
    counts = (
        {
            name: int(raw[name])
            for name in CATEGORIES
            if isinstance(raw, dict)
            and isinstance(raw.get(name), int)
            and raw[name] > 0
        }
        if isinstance(raw, dict)
        else {}
    )
    incomplete = rollup.get("incomplete")
    # The model name distinguishes the three states the list marks: a provider judged this
    # run (named model), the pass broke (incomplete), or it was report-only (neither).
    # Normalised through the same clip the detail view uses -- this string is echoed once
    # per triaged run in a response that already carries thousands of them.
    return {
        "model": triage_label(rollup.get("model")),
        "counts": counts,
        "incomplete": bool(incomplete),
    }


def _coverage_from_meta(meta: dict[str, Any] | None) -> float | None:
    """The baked-in coverage fraction (0-1) from a run's meta, or ``None``."""
    if not isinstance(meta, dict):
        return None
    return _unit_fraction(meta.get("coverage"))


def _coverage_threshold_from_meta(meta: dict[str, Any] | None) -> float | None:
    """The coverage bar the producer pinned to this run (0-1), or ``None`` for the default."""
    if not isinstance(meta, dict):
        return None
    return _unit_fraction(meta.get("coverage_threshold"))


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
