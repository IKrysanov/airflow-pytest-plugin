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

"""Filesystem-backed report source.

Lists by scanning ``meta.json`` sidecars (no XML parse); parses ``junit.xml`` on
demand for per-case detail with the operator's ``JUnitResultParser``. The
directory mapping is owned by :class:`ReportLayout`, shared with the producer.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from airflow_pytest_operator import JUnitResultParser

from ..config import get_reports_root
from ..layout import META_FILENAME, ReportLayout
from ..models import CaseView, ReportDetail, ReportRef, ReportSummary
from .base import ReportSource

try:  # prefer the hardened parser when present (matches the operator)
    from defusedxml.ElementTree import parse as _xml_parse
except Exception:  # pragma: no cover - fallback path
    from xml.etree.ElementTree import parse as _xml_parse

_log = logging.getLogger(__name__)

#: Cap a single case's traceback so a pathological report can't bloat a response.
_MAX_MESSAGE = 16000


class FileSystemReportSource(ReportSource):
    """Read archived reports from a directory tree on disk.

    :param report_root: the archive root. Defaults to
        :func:`~airflow_pytest_plugin.config.get_reports_root`.
    :param layout: directory mapping (shared with the producer).
    :param parser: parser used to read per-case detail. Defaults to the
        operator's :class:`JUnitResultParser`; inject a configured one (e.g.
        with ``defusedxml``) or a fake in tests.
    """

    def __init__(
        self,
        *,
        report_root: str | None = None,
        layout: ReportLayout | None = None,
        parser: JUnitResultParser | None = None,
    ) -> None:
        self._report_root = os.path.abspath(report_root or get_reports_root())
        self._layout = layout or ReportLayout()
        self._parser = parser or JUnitResultParser()

    @property
    def report_root(self) -> str:
        return self._report_root

    def list_summaries(
        self,
        *,
        dag_id: str | None = None,
        run_id: str | None = None,
    ) -> list[ReportSummary]:
        root = Path(self._report_root)
        if not root.is_dir():
            return []

        summaries: list[ReportSummary] = []
        for meta_file in root.rglob(META_FILENAME):
            meta = self._load_meta(meta_file)
            if meta is None:
                continue
            summary = self._summary_from_meta(meta)
            if summary is None:
                continue
            # Case-insensitive substring match (``in``), mirroring the UI.
            if dag_id and dag_id.lower() not in summary.ref.dag_id.lower():
                continue
            if run_id and run_id.lower() not in summary.ref.run_id.lower():
                continue
            summaries.append(summary)

        # Newest first. created_at is an ISO-8601 string, so it sorts
        # lexicographically in chronological order; missing values sort last.
        summaries.sort(key=lambda s: s.created_at or "", reverse=True)
        return summaries

    def get_detail(self, ref: ReportRef) -> ReportDetail | None:
        report_path = self._layout.report_path(self._report_root, ref)
        if not os.path.exists(report_path):
            return None

        # Prefer the stored summary (it records exit_code / success exactly as
        # the run saw them); fall back to re-deriving from the parsed XML.
        meta = self._load_meta(Path(self._layout.meta_path(self._report_root, ref)))
        summary = self._summary_from_meta(meta) if meta is not None else None

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
                success=result.success,
                created_at=None,
            )

        # The operator's parser keeps only the short ``message`` attribute; for
        # the detail view we want the full ``<failure>``/``<error>`` body (the
        # traceback). Read it straight from the XML and prefer it per case.
        tracebacks = self._full_messages(report_path)
        cases = tuple(
            CaseView(
                node_id=c.node_id,
                name=c.name,
                classname=c.classname,
                outcome=c.outcome,
                time=c.time,
                message=tracebacks.get((c.classname, c.name), c.message),
            )
            for c in result.cases
        )
        return ReportDetail(summary=summary, cases=cases)

    # -- internals -------------------------------------------------------

    @staticmethod
    def _full_messages(report_path: str) -> dict[tuple[str, str], str]:
        """Map ``(classname, name) -> full failure/error/skip text`` from the XML.

        Combines the ``message`` attribute with the element body (the traceback
        pytest writes there), capped per case. Best-effort: a parse failure
        yields an empty map and the caller falls back to the short message.
        """
        try:
            tree = _xml_parse(report_path)
        except Exception:
            return {}
        root = tree.getroot()
        suites = list(root.iter("testsuite")) if root.tag == "testsuites" else [root]
        out: dict[tuple[str, str], str] = {}
        for suite in suites:
            for tc in suite.findall("testcase"):
                # Element truthiness is child-based, so test ``is not None``.
                node = tc.find("failure")
                if node is None:
                    node = tc.find("error")
                if node is None:
                    node = tc.find("skipped")
                if node is None:
                    continue
                parts = [
                    p for p in (node.get("message"), (node.text or "").strip()) if p
                ]
                text = "\n".join(parts).strip()
                if not text:
                    continue
                if len(text) > _MAX_MESSAGE:
                    text = text[:_MAX_MESSAGE] + "\n…(truncated)"
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
    def _summary_from_meta(meta: dict[str, Any]) -> ReportSummary | None:
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

        summary = meta.get("summary") or {}
        return ReportSummary(
            ref=ref,
            total=int(summary.get("total", 0)),
            passed=int(summary.get("passed", 0)),
            failed=int(summary.get("failed", 0)),
            skipped=int(summary.get("skipped", 0)),
            errors=int(summary.get("errors", 0)),
            duration=float(summary.get("duration", 0.0)),
            success=bool(summary.get("success", False)),
            created_at=_opt_str(meta.get("created_at")),
            logical_date=_opt_str(meta.get("logical_date")),
        )


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None
