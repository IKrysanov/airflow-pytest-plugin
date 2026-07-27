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

"""Producer-side parser: archive each run under the reports layout (JUnit, plus
optional raw Allure results for TestOps)."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from airflow_pytest_operator import JUnitResultParser, ReportRequest, TestRunResult

from ..compat import get_conf_value, get_current_context
from ..config import get_reports_root
from ..layout import (
    ALLURE_DIRNAME,
    COVERAGE_FILENAME,
    META_FILENAME,
    REPORT_FILENAME,
    TRIAGE_FILENAME,
    VERDICTS_FILENAME,
    ReportLayout,
)
from ..models import ReportRef
from ..triage import TriageArchive, distill_report

_log = logging.getLogger(__name__)

#: Bumped when the meta.json shape changes incompatibly.
META_SCHEMA_VERSION = 1


# The operator base is Any when its package ships without type info, concretely typed
# otherwise, so the misc subclass error fires only sometimes. `unused-ignore` keeps this
# quiet either way.
class ArchivingResultParser(JUnitResultParser):  # type: ignore[misc, unused-ignore]
    """Archive each run under the reports layout: the operator's JUnit result, plus
    (with ``allure=True``) raw Allure results for TestOps export, (with ``coverage=True``)
    the run's coverage, and (with ``triage=True`` / ``triage_provider=...``) an AI verdict
    per failed test."""

    def __init__(
        self,
        *,
        report_root: str | None = None,
        layout: ReportLayout | None = None,
        allure: bool = False,
        coverage: bool = False,
        coverage_source: str | None = None,
        coverage_threshold: float | None = None,
        triage: bool = False,
        triage_provider: str | None = None,
        triage_budget: int | None = None,
        triage_timeout: float | None = None,
        email: bool = False,
        email_only_fail: bool = False,
    ) -> None:
        super().__init__()  # base report_dir stays None; we compute per-run
        self._report_root = os.path.abspath(report_root or get_reports_root())
        self._layout = layout or ReportLayout()
        # When True, also pass pytest ``--alluredir`` (requires allure-pytest in the
        # worker, else pytest errors on the unknown arg) so raw Allure results land
        # beside junit.xml for TestOps export.
        self._allure = allure
        # When True, turn coverage on for this task and archive it: pytest gets ``--cov``
        # plus a JSON report inside the archive dir, which is read at ARCHIVE time and
        # baked into meta.json. Self-contained -- the operator's own ``coverage=True`` is
        # NOT required (the runner appends these flags after the operator has already
        # decided its own, so neither side disturbs the other; setting both is harmless,
        # a duplicate ``--cov`` measures the same thing once). Needs pytest-cov on the
        # worker, else pytest aborts on the unrecognized flag. Unlike the XCom route this
        # also survives a FAILED run: the parser runs before the operator raises.
        self._coverage = coverage
        # Scope for the measurement, i.e. ``--cov=<source>``. Leave unset for a bare
        # ``--cov`` (measure everything, matching what the operator itself splices). Set it
        # when the project already narrows coverage -- e.g. ``addopts = "--cov=src"`` -- since
        # adding a bare ``--cov`` on top would WIDEN the scope (pytest-cov unions them) and
        # silently change the reported percentage, typically by pulling the tests in too.
        self._coverage_source = (coverage_source or "").strip() or None
        # Optional per-task coverage bar (0-1) pinned to every run this parser archives.
        # It travels in meta.json and OUTRANKS the reader's AIRFLOW_PYTEST_SUCCESS_COVERAGE,
        # because "what good coverage looks like" is a property of the suite, not of the
        # viewer -- a core library and a legacy smoke suite deserve different bars, which a
        # single reader-side env var cannot express. Presentational only: like the env var
        # it tints the card and never fails a run (that is the operator's cov_fail_under).
        self._coverage_threshold = _unit_fraction_or_none(coverage_threshold)
        # AI failure triage (pytest-triage on the worker; needs the package installed, else
        # pytest aborts on the unrecognized flags -- exactly like allure/coverage above).
        # Two levels, both opt-in and both self-contained:
        #   triage=True                -> pytest writes its failure report into the archive
        #                                 dir. No provider, no network, every verdict null;
        #                                 the run still gets exc_type + a rerun selector per
        #                                 failure.
        #   triage_provider="anthropic" -> ALSO turns the LLM pass on, so each failure gets a
        #                                 category / hypothesis / suggested fix. Naming a
        #                                 provider implies the report, so one argument is
        #                                 enough for the full feature.
        # The verdicts are read at ARCHIVE time, so (like coverage) they survive a FAILED run
        # -- the parser runs before the operator raises. The roll-up lands in meta.json; the
        # per-test verdicts in their own verdicts.json, which the tree scan never opens.
        self._triage_provider = (triage_provider or "").strip() or None
        self._triage = bool(triage) or self._triage_provider is not None
        # Max provider calls per run (pytest-triage's own default is 10) and the wall-clock
        # cap per call. Left unset, pytest-triage's defaults apply -- which is what a suite
        # with a handful of failures wants; raise the budget for a suite that breaks wide.
        self._triage_budget = _positive_int_or_none(triage_budget)
        self._triage_timeout = _positive_float_or_none(triage_timeout)
        # Per-task switches for automatic email (both need
        # ``AIRFLOW_PYTEST_ALERTS_EMAIL_TO`` recipients + a mail transport):
        #   email=True           -> mail after EVERY run (styled by outcome).
        #   email_only_fail=True -> mail ONLY on fail/flaky, no success mail
        #                           (wins when both flags are set).
        # Both False (default) -> no mail, so a noisy ping/smoke suite can't spam the box.
        self._email = email
        self._email_only_fail = email_only_fail
        # Ref resolved in report_request, reused by parse() to name the sidecar. One
        # parser instance serves one task, so a single slot suffices.
        self._pending_ref: ReportRef | None = None
        self._pending_context: dict[str, Any] | None = None

    @property
    def report_root(self) -> str:
        return self._report_root

    def report_request(self, report_dir: str) -> ReportRequest:
        # Resolve coordinates now (inside execute()) and aim the base parser's
        # report_dir at our archive location; super() keeps the JUnit flags in one place.
        context = get_current_context()
        ref = self._resolve_ref(context)
        self._pending_ref = ref
        self._pending_context = context
        self._report_dir = self._layout.dir_for(self._report_root, ref)
        _log.info(
            "Archiving pytest report for %s/%s/%s (try %d) to %s",
            ref.dag_id,
            ref.run_id,
            ref.task_id,
            ref.try_number,
            self._report_dir,
        )
        req = super().report_request(report_dir)
        if self._allure and req.report_path:
            allure_dir = os.path.join(os.path.dirname(req.report_path), ALLURE_DIRNAME)
            req = dataclasses.replace(
                req, pytest_args=(*req.pytest_args, f"--alluredir={allure_dir}")
            )
        if self._coverage and req.report_path:
            # ``--cov`` switches measurement on; the JSON report is an EXTRA --cov-report,
            # and pytest-cov accepts several, so the operator's own ``term-missing`` (which
            # it parses for its XCom value and the cov_fail_under gate) keeps working. The
            # runner appends these AFTER the operator built its own args, so our ``--cov``
            # is invisible to its `has_flag` check and cannot make it skip its own splice.
            cov_flag = (
                f"--cov={self._coverage_source}" if self._coverage_source else "--cov"
            )
            req = dataclasses.replace(
                req,
                pytest_args=(
                    *req.pytest_args,
                    cov_flag,
                    f"--cov-report=json:{self._coverage_path(req.report_path)}",
                ),
            )
        if self._triage and req.report_path:
            req = dataclasses.replace(
                req, pytest_args=(*req.pytest_args, *self._triage_args(req.report_path))
            )
        return req

    def parse(self, report_path: str, *, exit_code: int = 0) -> TestRunResult:
        result = super().parse(report_path, exit_code=exit_code)
        # Best-effort sidecar: a write failure must never mask the test outcome.
        try:
            self._write_meta(report_path, result)
        except Exception:
            _log.exception(
                "Failed to write %s sidecar next to %s", META_FILENAME, report_path
            )
        # Tracking link into the task log, so the archived run is one click away.
        # Best-effort like everything post-archive: never masks the test outcome.
        try:
            self._log_tracking_url()
        except Exception:
            _log.debug("Could not build the viewer tracking URL", exc_info=True)
        # Best-effort alerting: opt-in and isolated -- a mail/config failure must never
        # mask the outcome either. No-ops immediately when disabled (default).
        try:
            self._maybe_notify()
        except Exception:
            _log.exception("Post-archive alert evaluation failed for %s", report_path)
        return result

    # -- internals -------------------------------------------------------

    @staticmethod
    def _coverage_path(report_path: str) -> str:
        """Where pytest-cov should write the run's JSON coverage report."""
        return os.path.join(os.path.dirname(report_path), COVERAGE_FILENAME)

    @staticmethod
    def _triage_path(report_path: str) -> str:
        """Where pytest-triage should write the run's failure report."""
        return os.path.join(os.path.dirname(report_path), TRIAGE_FILENAME)

    def _triage_args(self, report_path: str) -> tuple[str, ...]:
        """pytest-triage flags for this run, aimed at the archive directory.

        ``--ai-report`` alone gives the report with null verdicts; ``--ai-triage=on``
        plus a provider adds the LLM pass. Budget and timeout are only passed when the
        task pinned them, so pytest-triage's own defaults stay in force otherwise.
        """
        args = [f"--ai-report={self._triage_path(report_path)}"]
        if self._triage_provider:
            args += ["--ai-triage=on", f"--ai-provider={self._triage_provider}"]
            if self._triage_budget is not None:
                args.append(f"--ai-budget={self._triage_budget}")
            if self._triage_timeout is not None:
                args.append(f"--ai-timeout={self._triage_timeout:g}")
        return tuple(args)

    def _read_triage(self, report_path: str) -> dict[str, Any] | None:
        """Archive the run's AI verdicts; return the roll-up for ``meta.json``.

        The per-test verdicts are written to their own ``verdicts.json`` beside the report:
        ``meta.json`` is parsed for every run on every tree scan, so it carries only the
        roll-up (see :data:`~..layout.VERDICTS_FILENAME`).

        ``None`` when triage wasn't requested, pytest-triage wrote nothing (not installed,
        or the run died before its session finished), or the file is unreadable -- the run
        then simply shows no AI analysis. Never raises: an unusable report must not cost
        the archive its ``meta.json``.
        """
        if not self._triage:
            return None
        path = self._triage_path(report_path)
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError, RecursionError):
            # RecursionError, not just ValueError: that is how json.load fails on a nesting
            # bomb, and uncaught it escapes _write_meta -- costing the run the very file that
            # makes it visible in the viewer. Losing the AI section is fine; losing the run
            # is not.
            _log.debug("No readable triage report at %s", path, exc_info=True)
            return None
        archive = distill_report(raw)
        if archive is None:
            # Unreadable: keep it. It is then the only record of what went wrong, and the
            # archive has no distilled copy to fall back on.
            return None
        # Drop the original ONLY once the distilled copy is on disk. It is the LARGEST file
        # in a run's archive (measured: 10.1KB against junit.xml's 8.5KB on a nine-failure
        # suite), it repeats tracebacks junit.xml already stores, and being owner-only the
        # reader can never open it -- but deleting it after a failed write would leave a run
        # that claims to be triaged with nothing behind it and no evidence of why.
        if self._write_verdicts(report_path, archive):
            with contextlib.suppress(OSError):
                os.unlink(path)
        return archive.rollup

    def _write_verdicts(self, report_path: str, archive: TriageArchive) -> bool:
        """Write ``verdicts.json`` atomically beside the report; ``True`` when it landed.

        Atomic (temp + rename) so a reader scanning concurrently never opens a half file,
        and uniquely named so two writers cannot share a temp. Catches ``Exception``, not
        just ``OSError``: this runs while ``meta.json`` is being built, and a failure to
        archive the per-test analysis must never cost the run its identity sidecar -- the
        roll-up still lands, and the run still reads as triaged.
        """
        out_dir = os.path.dirname(os.path.abspath(report_path))
        tmp = os.path.join(out_dir, f".{VERDICTS_FILENAME}.{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(archive.verdicts_document(), fh, ensure_ascii=False)
            os.replace(tmp, os.path.join(out_dir, VERDICTS_FILENAME))
        except Exception:
            _log.warning(
                "Could not archive AI verdicts for %s", report_path, exc_info=True
            )
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            return False
        return True

    def _read_coverage(self, report_path: str) -> float | None:
        """The run's overall line-coverage fraction (0-1) from the archived JSON report.

        ``None`` when coverage wasn't requested, pytest-cov wrote nothing (no ``--cov`` on
        the command line, or the run died before reporting), or the file is unreadable /
        out of range -- the reader then falls back to the operator's XCom value.
        """
        if not self._coverage:
            return None
        path = self._coverage_path(report_path)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            percent = data["totals"]["percent_covered"]
        except (OSError, ValueError, KeyError, TypeError):
            _log.debug("No readable coverage report at %s", path, exc_info=True)
            return None
        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            return None
        fraction = float(percent) / 100.0
        return fraction if 0.0 <= fraction <= 1.0 else None

    def _log_tracking_url(self) -> None:
        """Log a deep link to the archived run in the Pytest Reports viewer.

        With no base URL configured (``[api] base_url`` / ``[webserver] base_url``)
        it still logs the run's coordinates, plus how to get a clickable link.
        """
        # Same resolution as _write_meta, so the link matches the archived location.
        ref = self._pending_ref or self._resolve_ref(get_current_context())
        from ..plugin import run_tracking_url

        url = run_tracking_url(ref)
        if url:
            _log.info("Pytest report archived — view it at %s", url)
        else:
            _log.info(
                "Pytest report archived (dag=%s run=%s task=%s try=%s); set "
                "[api] base_url to get a clickable viewer link here",
                ref.dag_id,
                ref.run_id,
                ref.task_id,
                ref.try_number,
            )

    def _maybe_notify(self) -> None:
        """Email a notification for the run just archived, per the opt-in flags.

        ``email=True`` -> mail for EVERY run (styled by outcome). ``email_only_fail=True``
        -> mail only on fail/flaky (wins over ``email=True``, so success mail can be
        silenced). Both off (default) -> nothing. Imported lazily; the default path does
        no work.
        """
        if not self._email and not self._email_only_fail:
            return
        from ..notifications import notify_after_archive

        ref = self._pending_ref or self._resolve_ref(get_current_context())
        notify_after_archive(
            ref,
            report_root=self._report_root,
            always=self._email and not self._email_only_fail,
        )

    def _resolve_ref(self, context: dict[str, Any] | None) -> ReportRef:
        """Build a :class:`ReportRef` from context, or a synthetic ref off-task."""
        if not context:
            return ReportRef(
                dag_id="_unknown",
                run_id=f"_no-context-{uuid.uuid4().hex[:8]}",
                task_id="_unknown",
                try_number=0,
                map_index=-1,
            )

        ti = context.get("ti") or context.get("task_instance")
        dag_id = _first_str(
            getattr(ti, "dag_id", None),
            getattr(context.get("dag"), "dag_id", None),
            getattr(context.get("dag_run"), "dag_id", None),
            default="_unknown",
        )
        task_id = _first_str(
            getattr(ti, "task_id", None),
            getattr(context.get("task"), "task_id", None),
            default="_unknown",
        )
        run_id = _first_str(
            getattr(ti, "run_id", None),
            context.get("run_id"),
            getattr(context.get("dag_run"), "run_id", None),
            default=f"_no-run-{uuid.uuid4().hex[:8]}",
        )
        try_number = _first_int(getattr(ti, "try_number", None), default=1)
        map_index = _first_int(getattr(ti, "map_index", None), default=-1)
        return ReportRef(
            dag_id=dag_id,
            run_id=run_id,
            task_id=task_id,
            try_number=try_number,
            map_index=map_index,
        )

    def _write_meta(self, report_path: str, result: TestRunResult) -> None:
        ref = self._pending_ref
        context = self._pending_context
        if ref is None:
            # parse() without a prior report_request: resolve from a fresh context.
            context = get_current_context()
            ref = self._resolve_ref(context)
        out_dir = os.path.dirname(os.path.abspath(report_path))
        meta = {
            "schema_version": META_SCHEMA_VERSION,
            "dag_id": ref.dag_id,
            "run_id": ref.run_id,
            "task_id": ref.task_id,
            "try_number": ref.try_number,
            "map_index": ref.map_index,
            "logical_date": _logical_date(context),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "report_file": REPORT_FILENAME,
            "allure": self._archive_allure(out_dir, ref),
            # Baked in at archive time when coverage=True. Survives a failed run (the
            # operator raises AFTER parsing, so its XCom never lands), and spares the
            # reader an Airflow metadata-DB round-trip on first view.
            "coverage": self._read_coverage(report_path),
            # Only written when the task pinned one; absent -> the reader applies its
            # AIRFLOW_PYTEST_SUCCESS_COVERAGE default.
            "coverage_threshold": self._coverage_threshold,
            # The AI triage roll-up (model, duration, category counts) -- small on purpose,
            # since every tree scan parses this file for every run. The per-test verdicts go
            # to verdicts.json; tracebacks stay in junit.xml and in the raw report.
            "triage": self._read_triage(report_path),
            "summary": result.to_xcom(),
            # Compact [node_id, outcome, duration] rows so cross-run views
            # (compare/flaky/history) need not re-parse junit.xml.
            "tests": _test_rows(result),
        }
        # Atomic write: a reader scanning concurrently never sees a half file.
        tmp = os.path.join(out_dir, f".{META_FILENAME}.{uuid.uuid4().hex}.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, os.path.join(out_dir, META_FILENAME))

    def _archive_allure(self, out_dir: str, ref: ReportRef) -> bool:
        """True if Allure results exist here; also drop an executor.json so the
        TestOps launch links back to this Airflow run. Best-effort."""
        allure_dir = os.path.join(out_dir, ALLURE_DIRNAME)
        try:
            if not self._allure or not os.listdir(allure_dir):
                return False
        except OSError:  # no allure-results dir
            return False
        try:
            with open(
                os.path.join(allure_dir, "executor.json"), "w", encoding="utf-8"
            ) as fh:
                json.dump(_executor_json(ref), fh, ensure_ascii=False, indent=2)
        except OSError:
            _log.warning("Could not write Allure executor.json", exc_info=True)
        return True


def _executor_json(ref: ReportRef) -> dict[str, Any]:
    """Allure executor.json: presents the Airflow run as the build, linking the
    TestOps launch back to the task instance when a base URL is configured."""
    data: dict[str, Any] = {
        "name": "Airflow",
        "type": "airflow",
        "reportName": "Pytest Reports",
        "buildName": f"{ref.dag_id} · {ref.task_id} · {ref.run_id} (try {ref.try_number})",
    }
    base = (
        get_conf_value("api", "base_url")
        or get_conf_value("webserver", "base_url")
        or ""
    ).rstrip("/")
    if base:
        data["url"] = base
        data["buildUrl"] = (
            f"{base}/dags/{quote(ref.dag_id, safe='')}"
            f"/runs/{quote(ref.run_id, safe='')}"
            f"/tasks/{quote(ref.task_id, safe='')}"
        )
    return data


def _unit_fraction_or_none(value: float | None) -> float | None:
    """A 0-1 fraction, or ``None`` when unset / not a number / out of range.

    Rejects rather than clamps, and warns: a task that meant ``0.9`` but wrote ``90``
    should fall back to the configured default, not silently pin an absurd bar.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _log.warning("ignoring non-numeric coverage_threshold %r", value)
        return None
    if not 0.0 <= value <= 1.0:
        _log.warning(
            "ignoring out-of-range coverage_threshold %r (expected a 0-1 fraction)",
            value,
        )
        return None
    return float(value)


def _positive_int_or_none(value: int | None) -> int | None:
    """A positive int, or ``None`` when unset / not an int / not positive.

    Rejects rather than clamps, and warns: a task that wrote ``0`` or ``"20"`` should fall
    back to pytest-triage's own default instead of silently disabling the AI pass.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _log.warning("ignoring non-integer triage_budget %r", value)
        return None
    if value <= 0:
        _log.warning("ignoring non-positive triage_budget %r", value)
        return None
    return value


def _positive_float_or_none(value: float | None) -> float | None:
    """A finite, positive number of seconds, or ``None`` when unset / unusable."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _log.warning("ignoring non-numeric triage_timeout %r", value)
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        _log.warning("ignoring non-positive triage_timeout %r", value)
        return None
    return number


def _first_str(*values: Any, default: str) -> str:
    for v in values:
        if isinstance(v, str) and v:
            return v
    return default


def _first_int(*values: Any, default: int) -> int:
    for v in values:
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
    return default


def _test_rows(result: TestRunResult) -> list[list[Any]]:
    """Compact ``[node_id, outcome, duration]`` rows for cross-run views."""
    rows: list[list[Any]] = []
    for c in getattr(result, "cases", ()) or ():
        try:
            dur = round(float(getattr(c, "time", 0.0) or 0.0), 3)
        except (TypeError, ValueError):
            dur = 0.0
        rows.append([c.node_id, c.outcome, dur])
    return rows


def _logical_date(context: dict[str, Any] | None) -> str | None:
    if not context:
        return None
    value = context.get("logical_date")
    if value is None:
        value = getattr(context.get("dag_run"), "logical_date", None)
    if value is None:
        return None
    try:
        return str(value.isoformat())
    except AttributeError:
        return str(value)
