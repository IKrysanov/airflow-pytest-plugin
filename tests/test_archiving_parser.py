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

    # Simulate the runner writing the report.
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


def test_report_root_property(reports_root):
    parser = ArchivingJUnitResultParser(report_root=reports_root)
    assert parser.report_root == os.path.abspath(reports_root)


def test_parse_without_report_request_resolves_context(
    monkeypatch, reports_root, tmp_path
):
    # parse() with no prior report_request resolves a fresh ref and logical_date
    # from the live context (defensive path must not drop them).
    ti = FakeTI(dag_id="d", task_id="t", run_id="run9", try_number=1)
    _patch_context(monkeypatch, {"ti": ti, "logical_date": "2026-06-22T00:00:00+00:00"})

    report = tmp_path / "junit.xml"
    report.write_text(junit_xml(passed=1))
    parser = ArchivingJUnitResultParser(report_root=reports_root)
    result = parser.parse(str(report))
    assert result.total == 1
    meta = json.load(open(tmp_path / META_FILENAME, encoding="utf-8"))
    assert meta["run_id"] == "run9"
    assert meta["logical_date"] == "2026-06-22T00:00:00+00:00"


def test_first_str_and_first_int_helpers():
    # _first_str returns the first non-empty str, else the default.
    assert archiving_parser._first_str(None, "", "ok", default="d") == "ok"
    assert archiving_parser._first_str(None, "", default="d") == "d"
    # _first_int returns the first int, skipping bools, else the default.
    assert archiving_parser._first_int(True, False, 7, default=-1) == 7
    assert archiving_parser._first_int(None, True, default=-1) == -1


def test_parse_swallows_meta_write_failure(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingJUnitResultParser(report_root=reports_root)
    req = parser.report_request("/runner/tmp")
    os.makedirs(os.path.dirname(req.report_path), exist_ok=True)
    with open(req.report_path, "w", encoding="utf-8") as fh:
        fh.write(junit_xml(passed=1))

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(parser, "_write_meta", _boom)
    # The real test outcome must survive a sidecar-write failure.
    result = parser.parse(req.report_path)
    assert result.total == 1


def test_resolve_ref_falls_back_to_dag_and_task_objects(reports_root):
    parser = ArchivingJUnitResultParser(report_root=reports_root)

    class Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    context = {
        "ti": None,
        "dag": Obj(dag_id="dag_from_obj"),
        "task": Obj(task_id="task_from_obj"),
        "dag_run": Obj(run_id="run_from_obj"),
    }
    ref = parser._resolve_ref(context)
    assert ref.dag_id == "dag_from_obj"
    assert ref.task_id == "task_from_obj"
    assert ref.run_id == "run_from_obj"
    assert ref.try_number == 1  # default when absent
    assert ref.map_index == -1


def test_logical_date_variants():
    from datetime import datetime, timezone

    assert archiving_parser._logical_date(None) is None
    assert archiving_parser._logical_date({}) is None
    dt = datetime(2026, 6, 21, tzinfo=timezone.utc)
    assert archiving_parser._logical_date({"logical_date": dt}).startswith("2026-06-21")

    class Run:
        logical_date = dt

    assert archiving_parser._logical_date({"dag_run": Run()}).startswith("2026-06-21")
    # A non-datetime value falls back to str().
    assert (
        archiving_parser._logical_date({"logical_date": "2026-06-21"}) == "2026-06-21"
    )
