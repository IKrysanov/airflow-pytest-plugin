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

from __future__ import annotations

import json
import os

from airflow_pytest_plugin.layout import META_FILENAME, ReportLayout
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.producer import ArchivingJUnitResultParser, archiving_parser
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import FakeTI, junit_xml


def _patch_context(monkeypatch, context):
    monkeypatch.setattr(archiving_parser, "get_current_context", lambda: context)


def test_report_request_targets_layout_path(monkeypatch, reports_root):
    ti = FakeTI(dag_id="dag", task_id="task", run_id="run1", try_number=2)
    _patch_context(monkeypatch, {"ti": ti, "run_id": "run1"})

    parser = ArchivingJUnitResultParser(report_root=reports_root)
    req = parser.report_request("/runner/tmp")

    expected = ReportLayout().report_path(
        reports_root, ReportRef("dag", "run1", "task", 2)
    )
    assert req.report_path == expected
    assert f"--junitxml={expected}" in req.pytest_args


def test_parse_writes_meta_sidecar(monkeypatch, reports_root):
    ti = FakeTI(dag_id="dag", task_id="task", run_id="run1", try_number=1)
    _patch_context(monkeypatch, {"ti": ti, "run_id": "run1"})

    parser = ArchivingJUnitResultParser(report_root=reports_root)
    req = parser.report_request("/runner/tmp")

    # Simulate the runner writing the report pytest would have produced.
    os.makedirs(os.path.dirname(req.report_path), exist_ok=True)
    with open(req.report_path, "w", encoding="utf-8") as fh:
        fh.write(junit_xml(passed=2, failed=1))

    result = parser.parse(req.report_path, exit_code=1)
    assert result.total == 3 and result.failed == 1

    meta_path = os.path.join(os.path.dirname(req.report_path), META_FILENAME)
    meta = json.load(open(meta_path, encoding="utf-8"))
    assert meta["dag_id"] == "dag"
    assert meta["run_id"] == "run1"
    assert meta["task_id"] == "task"
    assert meta["summary"]["failed"] == 1
    assert meta["summary"]["success"] is False

    # End-to-end: the reader sees what the producer wrote.
    detail = FileSystemReportSource(report_root=reports_root).get_detail(
        ReportRef("dag", "run1", "task", 1)
    )
    assert detail is not None and detail.summary.total == 3


def test_no_context_still_archives_under_synthetic_ref(monkeypatch, reports_root):
    _patch_context(monkeypatch, None)

    parser = ArchivingJUnitResultParser(report_root=reports_root)
    req = parser.report_request("/runner/tmp")
    # Falls back to a synthetic, in-root path rather than raising.
    assert os.path.abspath(req.report_path).startswith(os.path.abspath(reports_root))
