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

"""Producer-side parser: archive each JUnit report under the reports layout.

Subclasses the operator's ``JUnitResultParser`` and overrides two seams:
``report_request`` points pytest at
``{root}/{dag_id}/{run_id}/{task_id}/t{try}[/m{map}]/junit.xml`` (a
parser-supplied directory the runner never deletes -- so ``cleanup="never"`` is
not needed), and ``parse`` writes a ``meta.json`` sidecar that makes the report
self-describing for the reader. Coordinates come from ``get_current_context()``
(the parser runs inside the task's ``execute()``); off-task calls fall back to a
synthetic ref. Airflow is imported only lazily, via the compat shim.

    PytestOperator(task_id="tests", test_path="tests/",
                   parser=ArchivingJUnitResultParser())
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from airflow_pytest_operator import JUnitResultParser, ReportRequest, TestRunResult

from ..compat import get_current_context
from ..config import get_reports_root
from ..layout import META_FILENAME, REPORT_FILENAME, ReportLayout
from ..models import ReportRef

_log = logging.getLogger(__name__)

#: Bumped when the meta.json shape changes incompatibly.
META_SCHEMA_VERSION = 1


class ArchivingJUnitResultParser(JUnitResultParser):  # type: ignore[misc]
    """JUnit parser that lays reports out for the reports UI.

    :param report_root: directory under which reports are archived. Defaults to
        :func:`~airflow_pytest_plugin.config.get_reports_root` (env var /
        Airflow config / built-in default) so producer and reader agree without
        extra wiring.
    :param layout: the :class:`~airflow_pytest_plugin.layout.ReportLayout` that
        maps a report to a directory. Injectable for tests / custom schemes.
    """

    def __init__(
        self,
        *,
        report_root: str | None = None,
        layout: ReportLayout | None = None,
    ) -> None:
        super().__init__()  # base report_dir stays None; we compute per-run
        self._report_root = os.path.abspath(report_root or get_reports_root())
        self._layout = layout or ReportLayout()
        # The ref resolved in report_request, reused by parse() to name the
        # sidecar. One parser instance serves one task (sequential reruns
        # reuse the same context), so a single slot is sufficient.
        self._pending_ref: ReportRef | None = None
        self._pending_context: dict[str, Any] | None = None

    @property
    def report_root(self) -> str:
        return self._report_root

    def report_request(self, report_dir: str) -> ReportRequest:
        # Resolve the Airflow coordinates now (we are inside execute()), pick the
        # archive directory, and hand it to the base parser by pointing its
        # ``report_dir`` at our location. Reusing ``super().report_request``
        # keeps the JUnit CLI flags (``--junitxml`` + ``junit_logging=all``)
        # defined in exactly one place (the operator's parser).
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
        return super().report_request(report_dir)

    def parse(self, report_path: str, *, exit_code: int = 0) -> TestRunResult:
        result = super().parse(report_path, exit_code=exit_code)
        # Best-effort sidecar: a failure to write meta.json must never mask the
        # real test outcome, so we log and move on. The JUnit XML is already on
        # disk; only the index entry would be missing.
        try:
            self._write_meta(report_path, result)
        except Exception:
            _log.exception(
                "Failed to write %s sidecar next to %s", META_FILENAME, report_path
            )
        return result

    # -- internals -------------------------------------------------------

    def _resolve_ref(self, context: dict[str, Any] | None) -> ReportRef:
        """Build a :class:`ReportRef` from the live Airflow context.

        Falls back to a synthetic, collision-free ref when no context is active
        so the parser is still usable off-task (tests, manual runs).
        """
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
        if ref is None:
            # parse() called without a prior report_request (defensive). Try to
            # resolve a ref again; skip the sidecar if there is still no context.
            ref = self._resolve_ref(get_current_context())
        out_dir = os.path.dirname(os.path.abspath(report_path))
        meta = {
            "schema_version": META_SCHEMA_VERSION,
            "dag_id": ref.dag_id,
            "run_id": ref.run_id,
            "task_id": ref.task_id,
            "try_number": ref.try_number,
            "map_index": ref.map_index,
            "logical_date": _logical_date(self._pending_context),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "report_file": REPORT_FILENAME,
            "summary": result.to_xcom(),
        }
        # Atomic write: a reader scanning concurrently never sees a half file.
        tmp = os.path.join(out_dir, f".{META_FILENAME}.{uuid.uuid4().hex}.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, os.path.join(out_dir, META_FILENAME))


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
