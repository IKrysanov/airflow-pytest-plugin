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

import dataclasses
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from airflow_pytest_operator import JUnitResultParser, ReportRequest, TestRunResult

from ..compat import get_conf_value, get_current_context
from ..config import get_reports_root
from ..layout import ALLURE_DIRNAME, META_FILENAME, REPORT_FILENAME, ReportLayout
from ..models import ReportRef

_log = logging.getLogger(__name__)

#: Bumped when the meta.json shape changes incompatibly.
META_SCHEMA_VERSION = 1


# The operator base is Any when its package ships without type info, concretely typed
# otherwise, so the misc subclass error fires only sometimes. `unused-ignore` keeps this
# quiet either way.
class ArchivingResultParser(JUnitResultParser):  # type: ignore[misc, unused-ignore]
    """Archive each run under the reports layout: the operator's JUnit result,
    plus (with ``allure=True``) raw Allure results for TestOps export."""

    def __init__(
        self,
        *,
        report_root: str | None = None,
        layout: ReportLayout | None = None,
        allure: bool = False,
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
        # Best-effort alerting: opt-in and isolated -- a mail/config failure must never
        # mask the outcome either. No-ops immediately when disabled (default).
        try:
            self._maybe_notify()
        except Exception:
            _log.exception("Post-archive alert evaluation failed for %s", report_path)
        return result

    # -- internals -------------------------------------------------------

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
