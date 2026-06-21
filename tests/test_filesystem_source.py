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

from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import write_report


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
    # The detail view carries the full <failure> body (traceback), not just the
    # short message attribute the operator's parser keeps.
    assert failed.message and "boom" in failed.message
    assert "assert False" in failed.message


def test_get_detail_returns_none_when_absent(reports_root):
    src = FileSystemReportSource(report_root=reports_root)
    assert src.get_detail(ReportRef("nope", "nope", "nope", 1)) is None


def test_get_detail_without_meta_falls_back_to_xml(reports_root):
    import os

    from airflow_pytest_plugin.layout import META_FILENAME, ReportLayout

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=3)
    # Drop the sidecar: detail must still work off the XML alone.
    os.remove(os.path.join(ReportLayout().dir_for(reports_root, ref), META_FILENAME))

    detail = FileSystemReportSource(report_root=reports_root).get_detail(ref)
    assert detail is not None
    assert detail.summary.total == 3
    assert detail.summary.created_at is None
