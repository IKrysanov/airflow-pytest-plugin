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
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

from airflow_pytest_operator import JUnitResultParser

from ..config import get_reports_root
from ..layout import ALLURE_DIRNAME, META_FILENAME, REPORT_FILENAME, ReportLayout
from ..models import CaseView, ReportDetail, ReportRef, ReportSummary
from .base import ReportSource

try:  # prefer the hardened parser when present (matches the operator)
    from defusedxml.ElementTree import parse as _xml_parse
except Exception:  # pragma: no cover - fallback path
    from xml.etree.ElementTree import parse as _xml_parse

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
            if dag_id and dag_id.lower() not in summary.ref.dag_id.lower():
                continue
            if run_id and run_id.lower() not in summary.ref.run_id.lower():
                continue
            summaries.append(summary)

        # Newest first: ISO-8601 created_at sorts chronologically; missing sorts last.
        summaries.sort(key=lambda s: s.created_at or "", reverse=True)
        return summaries

    def get_detail(self, ref: ReportRef) -> ReportDetail | None:
        # Token is attacker-controlled: bound the directory before reading.
        report_dir = self._safe_dir(ref)
        if report_dir is None:
            return None
        report_path = os.path.join(report_dir, REPORT_FILENAME)
        if not os.path.exists(report_path):
            return None

        # Prefer the stored summary (exact exit_code/success); fall back to parsed XML.
        meta = self._load_meta(Path(os.path.join(report_dir, META_FILENAME)))
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

        # The parser keeps only the short message; read the XML for each case's full output.
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
        return ReportDetail(summary=summary, cases=cases)

    def delete(self, ref: ReportRef) -> bool:
        target = self._safe_dir(ref)
        if target is None or not os.path.isdir(target):
            return False
        shutil.rmtree(target, ignore_errors=True)
        # Remove now-empty ancestors so the tree doesn't accumulate orphan directories.
        self._prune_empty_parents(
            os.path.dirname(target), os.path.realpath(self._report_root)
        )
        _log.info("Deleted report %s", target)
        return True

    def _safe_dir(self, ref: ReportRef) -> str | None:
        """The report dir for ``ref`` if it resolves under the root, else ``None``.

        Token is attacker-controlled: resolve real paths (``..``, symlinks) and refuse
        any escape -- the boundary both reads and deletes rely on.
        """
        root = os.path.realpath(self._report_root)
        target = os.path.realpath(self._layout.dir_for(self._report_root, ref))
        if target != root and target.startswith(root + os.sep):
            return target
        _log.warning("Refusing report path outside the report root: %r", target)
        return None

    def allure_archive(self, ref: ReportRef) -> bytes | None:
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
                # Element truthiness is child-based, so test ``is not None``.
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
                # Captured logs -- present for passed tests too under junit_logging=all.
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
            has_allure=bool(meta.get("allure")),
        )


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None
