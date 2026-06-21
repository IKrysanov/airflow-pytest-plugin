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
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import write_report, write_report_xml


def test_missing_root_lists_nothing(reports_root):
    src = FileSystemReportSource(report_root=reports_root)
    assert src.list_summaries() == []


def test_list_returns_newest_first(reports_root):
    write_report(
        reports_root,
        ReportRef("dag_a", "run_old", "t", 1),
        created_at="2026-06-20T10:00:00+00:00",
    )
    write_report(
        reports_root,
        ReportRef("dag_b", "run_new", "t", 1),
        created_at="2026-06-21T10:00:00+00:00",
    )
    src = FileSystemReportSource(report_root=reports_root)
    summaries = src.list_summaries()
    assert [s.ref.run_id for s in summaries] == ["run_new", "run_old"]


def test_list_filters_by_dag_and_run(reports_root):
    write_report(reports_root, ReportRef("dag_a", "r1", "t", 1))
    write_report(reports_root, ReportRef("dag_b", "r2", "t", 1))
    src = FileSystemReportSource(report_root=reports_root)
    assert [s.ref.dag_id for s in src.list_summaries(dag_id="dag_a")] == ["dag_a"]
    assert [s.ref.run_id for s in src.list_summaries(run_id="r2")] == ["r2"]


def test_list_filter_is_case_insensitive_substring(reports_root):
    write_report(reports_root, ReportRef("etl_daily", "r1", "t", 1))
    write_report(reports_root, ReportRef("etl_hourly", "r2", "t", 1))
    write_report(reports_root, ReportRef("ml_train", "r3", "t", 1))
    src = FileSystemReportSource(report_root=reports_root)
    assert {s.ref.dag_id for s in src.list_summaries(dag_id="etl")} == {
        "etl_daily",
        "etl_hourly",
    }
    assert {s.ref.dag_id for s in src.list_summaries(dag_id="ETL")} == {
        "etl_daily",
        "etl_hourly",
    }


def test_get_detail_parses_cases(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=2, failed=1, skipped=1)
    src = FileSystemReportSource(report_root=reports_root)

    detail = src.get_detail(ref)
    assert detail is not None
    assert detail.summary.total == 4
    assert detail.summary.failed == 1
    assert not detail.summary.success
    assert len(detail.cases) == 4
    outcomes = {c.outcome for c in detail.cases}
    assert outcomes == {"passed", "failed", "skipped"}
    failed = [c for c in detail.cases if c.outcome == "failed"][0]
    # Detail carries the full <failure> body (traceback), not just the short message.
    assert failed.message and "boom" in failed.message
    assert "assert False" in failed.message


def test_get_detail_returns_none_when_absent(reports_root):
    src = FileSystemReportSource(report_root=reports_root)
    assert src.get_detail(ReportRef("nope", "nope", "nope", 1)) is None


def test_get_detail_without_meta_falls_back_to_xml(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=3)
    # Drop the sidecar: detail must still work off the XML alone.
    os.remove(os.path.join(ReportLayout().dir_for(reports_root, ref), META_FILENAME))

    detail = FileSystemReportSource(report_root=reports_root).get_detail(ref)
    assert detail is not None
    assert detail.summary.total == 3
    assert detail.summary.created_at is None


def test_report_root_is_absolute(reports_root):
    src = FileSystemReportSource(report_root=reports_root)
    assert src.report_root == os.path.abspath(reports_root)


def test_list_skips_malformed_meta(reports_root, caplog):
    # Broken sidecars (non-object JSON, missing identity keys) are skipped.
    write_report(reports_root, ReportRef("good", "r", "t", 1))
    layout = ReportLayout()
    bad1 = layout.dir_for(reports_root, ReportRef("b1", "r", "t", 1))
    os.makedirs(bad1, exist_ok=True)
    with open(os.path.join(bad1, META_FILENAME), "w") as fh:
        fh.write("[1, 2, 3]")  # not a JSON object
    bad2 = layout.dir_for(reports_root, ReportRef("b2", "r", "t", 1))
    os.makedirs(bad2, exist_ok=True)
    with open(os.path.join(bad2, META_FILENAME), "w") as fh:
        json.dump({"summary": {}}, fh)  # missing dag_id/run_id/task_id/try_number

    summaries = FileSystemReportSource(report_root=reports_root).list_summaries()
    assert [s.ref.dag_id for s in summaries] == ["good"]


def test_get_detail_returns_none_on_corrupt_xml(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report_xml(reports_root, ref, "<not-valid-xml", summary={"total": 0})
    assert FileSystemReportSource(report_root=reports_root).get_detail(ref) is None


def test_case_output_includes_captured_stdout_for_passed(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites><testsuite name="pytest" tests="1" failures="0" errors="0" '
        'skipped="0" time="0.1">'
        '<testcase classname="tests.test_x" name="test_logs" time="0.05">'
        "<system-out>hello from stdout\nsecond line</system-out>"
        "<system-err>a warning</system-err>"
        "</testcase></testsuite></testsuites>"
    )
    write_report_xml(reports_root, ref, xml)

    detail = FileSystemReportSource(report_root=reports_root).get_detail(ref)
    assert detail is not None
    case = detail.cases[0]
    assert case.outcome == "passed"
    # Captured output is surfaced even for a passing test.
    assert "Captured stdout / log" in case.message
    assert "hello from stdout" in case.message
    assert "Captured stderr" in case.message


def test_delete_removes_report_and_prunes_empty_ancestors(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    out_dir = write_report(reports_root, ref)
    src = FileSystemReportSource(report_root=reports_root)
    assert os.path.isdir(out_dir)

    assert src.delete(ref) is True
    assert not os.path.exists(out_dir)
    # Empty dag/run/task ancestors are pruned, but the root survives.
    assert not os.path.exists(os.path.join(reports_root, "dag"))
    assert os.path.isdir(reports_root)
    assert src.list_summaries() == []


def test_delete_keeps_sibling_reports(reports_root):
    keep = ReportRef("dag", "run", "keep", 1)
    drop = ReportRef("dag", "run", "drop", 1)
    write_report(reports_root, keep)
    write_report(reports_root, drop)
    src = FileSystemReportSource(report_root=reports_root)

    assert src.delete(drop) is True
    remaining = [s.ref.task_id for s in src.list_summaries()]
    assert remaining == ["keep"]
    # The shared dag/run dir is preserved while a sibling still lives there.
    assert os.path.isdir(ReportLayout().dir_for(reports_root, keep))


def test_delete_returns_false_when_absent(reports_root):
    src = FileSystemReportSource(report_root=reports_root)
    assert src.delete(ReportRef("nope", "nope", "nope", 1)) is False


def test_case_outputs_empty_on_parse_error():
    # A missing/unparseable file yields no outputs (best-effort).
    assert FileSystemReportSource._case_outputs("/no/such/report.xml") == {}


def test_case_output_is_truncated(reports_root, monkeypatch):
    from airflow_pytest_plugin.sources import filesystem

    monkeypatch.setattr(filesystem, "_MAX_OUTPUT", 40)
    ref = ReportRef("dag", "run", "task", 1)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites><testsuite name="pytest" tests="1" failures="0" errors="0" '
        'skipped="0" time="0.1">'
        '<testcase classname="tests.test_x" name="test_big" time="0.05">'
        "<system-out>" + ("x" * 500) + "</system-out>"
        "</testcase></testsuite></testsuites>"
    )
    write_report_xml(reports_root, ref, xml)

    detail = FileSystemReportSource(report_root=reports_root).get_detail(ref)
    assert detail is not None
    assert detail.cases[0].message.endswith("…(truncated)")


def test_case_with_empty_skipped_body_adds_no_output(reports_root):
    # A <skipped/> with no message/text adds no captured-output section.
    ref = ReportRef("dag", "run", "task", 1)
    xml = (
        '<testsuite name="s" tests="1" failures="0" errors="0" skipped="1">'
        '<testcase classname="tests.x" name="test_a" time="0.0"><skipped/></testcase>'
        "</testsuite>"
    )
    write_report_xml(reports_root, ref, xml)
    detail = FileSystemReportSource(report_root=reports_root).get_detail(ref)
    assert detail is not None and len(detail.cases) == 1


def test_safe_neutralises_dot_components():
    from airflow_pytest_plugin.layout import _safe

    # Dot-only components must be neutralised or they become traversal segments.
    assert _safe("..") == "_"
    assert _safe(".") == "_"
    assert _safe("...") == "_"
    assert _safe("ok.xml") == "ok.xml"  # legitimate dots are kept


def test_get_detail_and_delete_refuse_traversal_token(tmp_path):
    # A file outside the root must never be read/deleted via a `..`/`.` traversal token.
    root = tmp_path / "reports"
    root.mkdir()
    outside = tmp_path / "t1"
    outside.mkdir()
    (outside / "junit.xml").write_text(
        '<testsuite><testcase classname="x" name="y"/></testsuite>', encoding="utf-8"
    )
    src = FileSystemReportSource(report_root=str(root))
    # Without the boundary this resolves to {root}/../././t1 == tmp_path/t1.
    ref = ReportRef(dag_id="..", run_id=".", task_id=".", try_number=1)
    assert src.get_detail(ref) is None
    assert src.delete(ref) is False
    assert (outside / "junit.xml").exists()  # untouched


def test_get_detail_refuses_symlink_escape(tmp_path):
    # The realpath guard must refuse a symlinked report dir pointing outside the root.
    root = tmp_path / "reports"
    target = root / "dag" / "run" / "task" / "t1"
    target.mkdir(parents=True)
    outside = tmp_path / "secret"
    outside.mkdir()
    (outside / "junit.xml").write_text("<testsuite/>", encoding="utf-8")
    target.rmdir()
    target.symlink_to(outside)

    src = FileSystemReportSource(report_root=str(root))
    ref = ReportRef(dag_id="dag", run_id="run", task_id="task", try_number=1)
    assert src.get_detail(ref) is None


def test_from_token_rejects_out_of_range_indices():
    import base64
    import json

    import pytest

    def tok(payload):
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    # Negative try_number or map_index < -1 are rejected (no `t-3`/`m-5` dirs).
    with pytest.raises(ValueError):
        ReportRef.from_token(tok({"d": "x", "r": "y", "t": "z", "n": -3, "m": 0}))
    with pytest.raises(ValueError):
        ReportRef.from_token(tok({"d": "x", "r": "y", "t": "z", "n": 1, "m": -5}))


def test_from_token_accepts_unmapped_sentinel():
    # map_index == -1 is the "not mapped" sentinel and must round-trip.
    ref = ReportRef("d", "r", "t", 1)  # default map_index = -1
    assert ref.map_index == -1
    assert ReportRef.from_token(ref.token).map_index == -1
    mapped = ReportRef("d", "r", "t", 1, map_index=0)
    assert ReportRef.from_token(mapped.token).map_index == 0
