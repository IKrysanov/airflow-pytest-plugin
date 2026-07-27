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

from airflow_pytest_plugin.layout import (
    COVERAGE_FILENAME,
    META_FILENAME,
    REPORT_FILENAME,
    TRIAGE_FILENAME,
    VERDICTS_FILENAME,
    ReportLayout,
)
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.producer import ArchivingResultParser, archiving_parser
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import FakeTI, junit_xml


def _patch_context(monkeypatch, context):
    monkeypatch.setattr(archiving_parser, "get_current_context", lambda: context)


def test_report_request_targets_layout_path(monkeypatch, reports_root):
    ti = FakeTI(dag_id="dag", task_id="task", run_id="run1", try_number=2)
    _patch_context(monkeypatch, {"ti": ti, "run_id": "run1"})

    parser = ArchivingResultParser(report_root=reports_root)
    req = parser.report_request("/runner/tmp")

    expected = ReportLayout().report_path(
        reports_root, ReportRef("dag", "run1", "task", 2)
    )
    assert req.report_path == expected
    assert f"--junitxml={expected}" in req.pytest_args


def test_parse_writes_meta_sidecar(monkeypatch, reports_root):
    ti = FakeTI(dag_id="dag", task_id="task", run_id="run1", try_number=1)
    _patch_context(monkeypatch, {"ti": ti, "run_id": "run1"})

    parser = ArchivingResultParser(report_root=reports_root)
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

    parser = ArchivingResultParser(report_root=reports_root)
    req = parser.report_request("/runner/tmp")
    # Falls back to a synthetic, in-root path rather than raising.
    assert os.path.abspath(req.report_path).startswith(os.path.abspath(reports_root))


def test_report_root_property(reports_root):
    parser = ArchivingResultParser(report_root=reports_root)
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
    parser = ArchivingResultParser(report_root=reports_root)
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
    parser = ArchivingResultParser(report_root=reports_root)
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
    parser = ArchivingResultParser(report_root=reports_root)

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


def test_allure_dir_appended_when_enabled(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="run1", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, allure=True)
    req = parser.report_request("/runner/tmp")
    expected = os.path.join(os.path.dirname(req.report_path), "allure-results")
    assert f"--alluredir={expected}" in req.pytest_args


def test_no_allure_dir_by_default(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="run1", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    req = ArchivingResultParser(report_root=reports_root).report_request("/x")
    assert not any("--alluredir" in a for a in req.pytest_args)


def _run_with_report(parser, reports_root):
    req = parser.report_request("/runner/tmp")
    rd = os.path.dirname(req.report_path)
    os.makedirs(rd, exist_ok=True)
    with open(req.report_path, "w", encoding="utf-8") as fh:
        fh.write(junit_xml(passed=1))
    return rd, req


def test_parse_flags_allure_and_writes_executor(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="run1", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, allure=True)
    rd, req = _run_with_report(parser, reports_root)
    # simulate allure-pytest having written a result into --alluredir
    allure_dir = os.path.join(rd, "allure-results")
    os.makedirs(allure_dir, exist_ok=True)
    with open(os.path.join(allure_dir, "x-result.json"), "w", encoding="utf-8") as fh:
        fh.write("{}")

    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["allure"] is True
    assert os.path.exists(os.path.join(allure_dir, "executor.json"))


def test_parse_allure_false_when_no_results(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="run1", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, allure=True)
    rd, req = _run_with_report(parser, reports_root)
    parser.parse(req.report_path)  # no allure-results dir was created
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["allure"] is False


def test_executor_json_has_buildurl_with_base_url(monkeypatch):
    monkeypatch.setattr(
        archiving_parser,
        "get_conf_value",
        lambda s, k: (
            "http://airflow.example/" if (s, k) == ("api", "base_url") else None
        ),
    )
    ref = ReportRef("dag", "scheduled__2026:01", "task", 2)
    data = archiving_parser._executor_json(ref)
    assert data["type"] == "airflow"
    assert data["buildUrl"].startswith("http://airflow.example/dags/dag/runs/")
    assert "%3A" in data["buildUrl"]  # the run_id ':' is URL-encoded


def test_meta_has_per_test_rows(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root)
    rd, req = _run_with_report(parser, reports_root)
    with open(req.report_path, "w", encoding="utf-8") as fh:
        fh.write(junit_xml(passed=2, failed=1, errors=1, skipped=1))
    parser.parse(req.report_path)
    rows = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))["tests"]
    assert len(rows) == 5
    assert sorted({r[1] for r in rows}) == ["error", "failed", "passed", "skipped"]
    assert all(len(r) == 3 and isinstance(r[2], (int, float)) for r in rows)


# --- archive-side coverage (coverage=True) ------------------------------------------------
def _write_cov_json(report_path, payload):
    """Stand in for pytest-cov writing its JSON report next to the junit file."""
    path = os.path.join(os.path.dirname(report_path), COVERAGE_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    return path


def test_coverage_flag_injects_json_report_into_the_archive(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    req = parser.report_request("/runner/tmp")

    expected = os.path.join(os.path.dirname(req.report_path), COVERAGE_FILENAME)
    assert f"--cov-report=json:{expected}" in req.pytest_args
    # Self-contained: --cov is what actually switches measurement on, so the flag must be
    # here too -- without it the JSON report is never written and the card stays empty
    # unless the operator (or the project's addopts) happens to enable coverage.
    assert "--cov" in req.pytest_args


def test_coverage_source_scopes_the_measurement(monkeypatch, reports_root):
    # A project that already narrows coverage (addopts = "--cov=src") must be able to keep
    # that scope: a bare --cov on top would union the scopes and silently widen the number.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, coverage=True, coverage_source="src"
    )
    req = parser.report_request("/runner/tmp")
    assert "--cov=src" in req.pytest_args
    assert "--cov" not in req.pytest_args  # the scoped form replaces the bare one


def test_blank_coverage_source_falls_back_to_bare_cov(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, coverage=True, coverage_source="   "
    )
    req = parser.report_request("/runner/tmp")
    assert "--cov" in req.pytest_args and "--cov=" not in " ".join(req.pytest_args)


def test_no_coverage_flag_without_the_opt_in(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root)  # coverage defaults False
    req = parser.report_request("/runner/tmp")
    assert not any(a.startswith("--cov") for a in req.pytest_args)


def test_coverage_is_baked_into_meta_at_archive_time(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    rd, req = _run_with_report(parser, reports_root)
    _write_cov_json(req.report_path, {"totals": {"percent_covered": 84.25}})

    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["coverage"] == 0.8425


def test_coverage_survives_a_failed_run(monkeypatch, reports_root):
    # The whole point of the archive route: the operator raises on a red suite, so its
    # return_value XCom never lands -- yet parse() ran first, so coverage is preserved
    # for exactly the runs an engineer most wants to inspect.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    req = parser.report_request("/runner/tmp")
    rd = os.path.dirname(req.report_path)
    os.makedirs(rd, exist_ok=True)
    with open(req.report_path, "w", encoding="utf-8") as fh:
        fh.write(junit_xml(passed=1, failed=2))
    _write_cov_json(req.report_path, {"totals": {"percent_covered": 61.0}})

    result = parser.parse(req.report_path, exit_code=1)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert result.failed == 2 and meta["coverage"] == 0.61


def test_unreadable_or_bogus_coverage_reports_fall_back_to_none(
    monkeypatch, reports_root
):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    rd, req = _run_with_report(parser, reports_root)

    # No file at all (pytest-cov never ran because the operator added no --cov).
    assert parser._read_coverage(req.report_path) is None
    for payload in (
        "{not json",  # corrupt
        {"totals": {}},  # key missing
        {"totals": {"percent_covered": "85"}},  # wrong type
        {"totals": {"percent_covered": True}},  # bool is not a number here
        {"totals": {"percent_covered": 140.0}},  # out of range
        {"totals": {"percent_covered": -1.0}},  # out of range
    ):
        _write_cov_json(req.report_path, payload)
        assert parser._read_coverage(req.report_path) is None, payload

    # ...and a broken report must not stop the run being archived.
    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["coverage"] is None and meta["summary"]["total"] == 1


def test_pinned_coverage_threshold_is_archived_with_the_run(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, coverage=True, coverage_threshold=0.6
    )
    rd, req = _run_with_report(parser, reports_root)
    _write_cov_json(req.report_path, {"totals": {"percent_covered": 55.0}})
    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["coverage"] == 0.55 and meta["coverage_threshold"] == 0.6


def test_unpinned_threshold_leaves_the_reader_default_in_charge(
    monkeypatch, reports_root
):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    rd, req = _run_with_report(parser, reports_root)
    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["coverage_threshold"] is None


def test_bogus_coverage_threshold_is_rejected_not_clamped(monkeypatch, reports_root):
    # A task meaning 90% but writing 90 must fall back to the reader default rather than
    # silently pinning an unreachable bar that paints every run red.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    for bad in (90, -0.1, 1.5, "0.8", True):
        parser = ArchivingResultParser(
            report_root=reports_root, coverage=True, coverage_threshold=bad
        )
        assert parser._coverage_threshold is None, bad
    ok = ArchivingResultParser(
        report_root=reports_root, coverage=True, coverage_threshold=0
    )
    assert ok._coverage_threshold == 0.0  # a 0 bar is legitimate ("never red")


def test_zero_coverage_is_a_value_not_a_missing_one(monkeypatch, reports_root):
    # 0.0 is falsy: a truthiness check anywhere on this path would silently turn "nothing
    # is covered" -- the most alarming reading there is -- into "no coverage measured".
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    rd, req = _run_with_report(parser, reports_root)
    _write_cov_json(req.report_path, {"totals": {"percent_covered": 0}})
    assert parser._read_coverage(req.report_path) == 0.0
    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["coverage"] == 0.0 and meta["coverage"] is not None


def test_full_coverage_reads_as_one(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    _, req = _run_with_report(parser, reports_root)
    _write_cov_json(req.report_path, {"totals": {"percent_covered": 100}})
    assert parser._read_coverage(req.report_path) == 1.0


def test_non_finite_coverage_is_rejected(monkeypatch, reports_root):
    # json.loads accepts bare NaN/Infinity, so a corrupt report really can carry them.
    # They must not reach meta.json: they'd serialize as non-spec JSON and break readers.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    _, req = _run_with_report(parser, reports_root)
    for literal in ("NaN", "Infinity", "-Infinity"):
        _write_cov_json(
            req.report_path, f'{{"totals": {{"percent_covered": {literal}}}}}'
        )
        assert parser._read_coverage(req.report_path) is None, literal


def test_coverage_read_is_stable_across_reparses(monkeypatch, reports_root):
    # A retry re-parses the same archive; the value must not drift or vanish.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    rd, req = _run_with_report(parser, reports_root)
    _write_cov_json(req.report_path, {"totals": {"percent_covered": 73.5}})
    for _ in range(3):
        parser.parse(req.report_path)
        meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
        assert meta["coverage"] == 0.735


def test_coverage_json_lives_inside_the_run_archive(monkeypatch, reports_root):
    # The report must land in THIS run's directory -- next to junit.xml -- so concurrent
    # tasks can't overwrite each other's coverage through a shared path.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, coverage=True)
    req = parser.report_request("/runner/tmp")
    cov_path = parser._coverage_path(req.report_path)
    assert os.path.dirname(cov_path) == os.path.dirname(req.report_path)
    assert os.path.abspath(cov_path).startswith(os.path.abspath(reports_root))


# --- AI triage (triage=True / triage_provider=...) ----------------------------------------
def _write_triage_json(report_path, payload):
    """Stand in for pytest-triage writing its report next to the junit file."""
    path = os.path.join(os.path.dirname(report_path), TRIAGE_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    return path


def _triage_payload(*, category="regression", nodeid="tests/test_x.py::test_f1"):
    return {
        "schema_version": 1,
        "ai_model": "claude-sonnet-5",
        "triage_duration": 4.12,
        "pytest_args": [nodeid],
        "failures": [
            {
                "nodeid": nodeid,
                "pytest_args": [nodeid],
                "phase": "call",
                "outcome": "failed",
                "exc_type": "AssertionError",
                "exc_message": "boom 1 != 2",
                "traceback": "assert 1 == 2",
                "verdict": {
                    "category": category,
                    "hypothesis": "the loader stopped de-duplicating rows",
                    "confidence": "high",
                    "suggested_fix": "restore the DISTINCT clause",
                },
            }
        ],
        "total_failures": 1,
        "total_verdicts": 1,
    }


def test_no_triage_flags_without_the_opt_in(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root)  # triage defaults False
    req = parser.report_request("/runner/tmp")
    assert not any(a.startswith("--ai-") for a in req.pytest_args)


def test_triage_alone_asks_for_the_report_but_no_provider(monkeypatch, reports_root):
    # Report-only: pytest-triage describes every failure (exc type, rerun selector) with
    # no provider, no network and no cost. Turning the LLM on is a separate decision.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage=True)
    req = parser.report_request("/runner/tmp")

    expected = os.path.join(os.path.dirname(req.report_path), TRIAGE_FILENAME)
    assert f"--ai-report={expected}" in req.pytest_args
    assert "--ai-triage=on" not in req.pytest_args
    assert not any(a.startswith("--ai-provider") for a in req.pytest_args)


def test_a_provider_implies_the_report_and_turns_triage_on(monkeypatch, reports_root):
    # One argument is enough for the whole feature: naming a provider without also
    # remembering triage=True must not silently produce a report with no verdicts.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, triage_provider="anthropic"
    )
    req = parser.report_request("/runner/tmp")
    assert "--ai-triage=on" in req.pytest_args
    assert "--ai-provider=anthropic" in req.pytest_args
    assert any(a.startswith("--ai-report=") for a in req.pytest_args)


def test_budget_and_timeout_are_passed_only_when_pinned(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    bare = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    args = bare.report_request("/runner/tmp").pytest_args
    # Unset -> pytest-triage's own defaults stay in force.
    assert not any(a.startswith("--ai-budget") for a in args)
    assert not any(a.startswith("--ai-timeout") for a in args)

    pinned = ArchivingResultParser(
        report_root=reports_root,
        triage_provider="fake",
        triage_budget=25,
        triage_timeout=45.0,
    )
    args = pinned.report_request("/runner/tmp").pytest_args
    assert "--ai-budget=25" in args
    # Formatted without a trailing ".0": pytest-triage parses either, but the command line
    # is echoed into task logs and reads as a number a human wrote.
    assert "--ai-timeout=45" in args


def test_budget_and_timeout_are_only_sent_with_a_provider(monkeypatch, reports_root):
    # They bound the LLM pass; without one there is nothing for them to bound.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, triage=True, triage_budget=25, triage_timeout=45.0
    )
    args = parser.report_request("/runner/tmp").pytest_args
    assert not any(
        a.startswith("--ai-budget") or a.startswith("--ai-timeout") for a in args
    )


def test_bogus_budget_or_timeout_falls_back_to_the_defaults(monkeypatch, reports_root):
    # Rejected, not clamped: a task that meant 20 but wrote "20" (or 0, which would
    # disable the pass entirely) should get pytest-triage's default, not a silent surprise.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    for budget in (0, -5, "20", True, 1.5):
        parser = ArchivingResultParser(
            report_root=reports_root, triage_provider="fake", triage_budget=budget
        )
        assert parser._triage_budget is None, budget
    for timeout in (0, -1, float("nan"), float("inf"), "30", True):
        parser = ArchivingResultParser(
            report_root=reports_root, triage_provider="fake", triage_timeout=timeout
        )
        assert parser._triage_timeout is None, timeout


def test_a_blank_provider_reads_as_no_provider(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="   ")
    assert parser._triage is False
    assert not any(
        a.startswith("--ai-") for a in parser.report_request("/t").pytest_args
    )


def test_triage_report_lives_inside_the_run_archive(monkeypatch, reports_root):
    # Like the coverage report: this run's directory, so concurrent tasks can't overwrite
    # each other's verdicts through a shared path.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    req = parser.report_request("/runner/tmp")
    path = parser._triage_path(req.report_path)
    assert os.path.dirname(path) == os.path.dirname(req.report_path)
    assert os.path.abspath(path).startswith(os.path.abspath(reports_root))


def test_verdicts_are_archived_at_archive_time(monkeypatch, reports_root):
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, triage_provider="anthropic"
    )
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, _triage_payload())

    parser.parse(req.report_path)
    # The roll-up rides in meta.json (which every tree scan parses)...
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["triage"]["model"] == "claude-sonnet-5"
    assert meta["triage"]["counts"] == {"regression": 1}
    assert "verdicts" not in meta["triage"]
    # ...the per-test judgements in their own file, keyed by the reader's dotted node id so
    # the join to a JUnit case needs no guessing.
    doc = json.load(open(os.path.join(rd, VERDICTS_FILENAME), encoding="utf-8"))
    assert doc["schema_version"] == 1
    assert doc["verdicts"]["tests.test_x::test_f1"]["confidence"] == "high"


def test_triage_survives_a_failed_run(monkeypatch, reports_root):
    # The runs worth triaging are exactly the ones the operator raises on, so the verdicts
    # must be archived by parse() -- before that raise -- not pushed through XCom after it.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, triage_provider="anthropic"
    )
    req = parser.report_request("/runner/tmp")
    rd = os.path.dirname(req.report_path)
    os.makedirs(rd, exist_ok=True)
    with open(req.report_path, "w", encoding="utf-8") as fh:
        fh.write(junit_xml(passed=1, failed=1))
    _write_triage_json(req.report_path, _triage_payload(category="env"))

    result = parser.parse(req.report_path, exit_code=1)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert result.failed == 1
    assert meta["triage"]["counts"] == {"env": 1}


def test_a_missing_or_unreadable_triage_report_costs_nothing(monkeypatch, reports_root):
    # pytest-triage not installed, or the run died before its session finished: the archive
    # must still be written, just without an AI section.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, triage_provider="anthropic"
    )
    rd, req = _run_with_report(parser, reports_root)
    assert parser._read_triage(req.report_path) is None  # nothing written at all

    for payload in ("{not json", "[]", '"a string"', "null"):
        _write_triage_json(req.report_path, payload)
        assert parser._read_triage(req.report_path) is None, payload

    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["triage"] is None and meta["summary"]["total"] == 1


def test_a_stale_triage_report_is_ignored_without_the_opt_in(monkeypatch, reports_root):
    # A report left in the archive dir by an earlier, triaged try must not resurrect
    # verdicts for a run whose task no longer asks for them.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root)
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, _triage_payload())

    parser.parse(req.report_path)
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["triage"] is None


def test_meta_stays_small_when_a_run_is_richly_triaged(monkeypatch, reports_root):
    # Every summary endpoint pays `_scan_disk()`, which json.loads EVERY run's meta.json in
    # full -- so anything stored there is parsed on every scan of the whole tree, by every
    # dashboard load. Measured A/B at 3000 runs x 200 verdicts: keeping verdicts in meta.json
    # made a cold scan 4.4x slower (300ms -> 1325ms) and grew the scanned corpus from 48MB to
    # 1.3GB. The verdicts belong beside the run, not in the file the scan reads.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(
        report_root=reports_root, triage_provider="anthropic"
    )
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(
        req.report_path,
        {
            "ai_model": "claude-sonnet-5",
            "failures": [
                {
                    "nodeid": f"tests/test_x.py::test_{i}",
                    "pytest_args": [f"tests/test_x.py::test_{i}"],
                    "exc_type": "AssertionError",
                    "verdict": {
                        "category": "regression",
                        "hypothesis": "h" * 1000,
                        "confidence": "high",
                        "suggested_fix": "f" * 1000,
                    },
                }
                for i in range(200)
            ],
            "total_failures": 200,
            "total_verdicts": 200,
        },
    )
    parser.parse(req.report_path)

    meta_size = os.path.getsize(os.path.join(rd, META_FILENAME))
    assert meta_size < 4096, (
        f"meta.json grew to {meta_size}B -- the scan reads this file"
    )
    # The judgements are still archived in full, just not in the scanned sidecar.
    verdicts = json.load(open(os.path.join(rd, VERDICTS_FILENAME), encoding="utf-8"))
    assert len(verdicts["verdicts"]) == 200


def test_a_failed_verdicts_write_never_costs_the_run_its_meta(
    monkeypatch, reports_root
):
    # verdicts.json is written while meta.json is being built. A full disk, a read-only
    # volume or a serialisation slip must degrade to "no per-test analysis", not to an
    # archive the reader cannot see at all.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, _triage_payload())

    real_open = open

    def explode(path, *a, **kw):
        if VERDICTS_FILENAME in str(path):
            raise OSError("no space left on device")
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", explode)
    parser.parse(req.report_path)
    monkeypatch.undo()

    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["summary"]["total"] == 1  # the archive is intact
    assert meta["triage"]["model"] == "claude-sonnet-5"  # and still reads as triaged
    assert not os.path.exists(os.path.join(rd, VERDICTS_FILENAME))
    # No temp litter left behind in the run's directory.
    assert [n for n in os.listdir(rd) if n.startswith(f".{VERDICTS_FILENAME}")] == []


def test_verdicts_are_written_atomically(monkeypatch, reports_root):
    # A reader scanning the tree concurrently must never open a half-written file, so the
    # bytes land under a temp name and are renamed into place.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, _triage_payload())

    renames = []
    real_replace = os.replace
    monkeypatch.setattr(
        os, "replace", lambda a, b: (renames.append((a, b)), real_replace(a, b))[1]
    )
    parser.parse(req.report_path)

    targets = [os.path.basename(b) for _a, b in renames]
    assert VERDICTS_FILENAME in targets and META_FILENAME in targets
    assert all(
        os.path.basename(a).startswith(".") and a.endswith(".tmp") for a, _b in renames
    )
    # The raw report is gone once distilled, so the archive keeps exactly three files.
    assert sorted(os.listdir(rd)) == sorted(
        [META_FILENAME, REPORT_FILENAME, VERDICTS_FILENAME]
    )


def test_the_raw_report_is_removed_once_it_has_been_distilled(
    monkeypatch, reports_root
):
    # pytest-triage's own report is the LARGEST file in a run's archive (measured: 10.1KB
    # against junit.xml's 8.5KB) and duplicates tracebacks that junit.xml already has. It is
    # written owner-only, so the reader can never open it -- keeping it only grows the tree
    # and eats the retention budget.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, _triage_payload())

    parser.parse(req.report_path)
    assert not os.path.exists(os.path.join(rd, TRIAGE_FILENAME))
    # ...and everything worth keeping was kept.
    doc = json.load(open(os.path.join(rd, VERDICTS_FILENAME), encoding="utf-8"))
    assert doc["verdicts"]["tests.test_x::test_f1"]["category"] == "regression"


def test_an_undistillable_report_is_kept_as_evidence(monkeypatch, reports_root):
    # If we could not read it, deleting it would destroy the only copy of what went wrong.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, "{not json")

    parser.parse(req.report_path)
    assert os.path.exists(os.path.join(rd, TRIAGE_FILENAME))
    meta = json.load(open(os.path.join(rd, META_FILENAME), encoding="utf-8"))
    assert meta["triage"] is None


def test_an_unparseable_triage_report_does_not_cost_the_run_its_meta(
    monkeypatch, reports_root
):
    # json.load raises RecursionError (not ValueError) on a nesting bomb. Uncaught here it
    # escapes _write_meta, whose caller swallows it -- and the run loses meta.json entirely,
    # which is the file that makes it VISIBLE in the viewer at all. Losing the AI section is
    # acceptable; losing the run is not.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, "[" * 60_000 + "]" * 60_000)

    parser.parse(req.report_path)
    meta_path = os.path.join(rd, META_FILENAME)
    assert os.path.exists(meta_path), "the run vanished from the archive"
    meta = json.load(open(meta_path, encoding="utf-8"))
    assert meta["summary"]["total"] == 1 and meta["triage"] is None


def test_the_raw_report_survives_a_failed_verdicts_write(monkeypatch, reports_root):
    # Deleting the original is only safe once the distilled copy is actually on disk.
    # Dropping both leaves a run that claims to be triaged with nothing behind it, and no
    # evidence left to work out why.
    ti = FakeTI(dag_id="d", task_id="t", run_id="r", try_number=1)
    _patch_context(monkeypatch, {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    rd, req = _run_with_report(parser, reports_root)
    _write_triage_json(req.report_path, _triage_payload())

    real_open = open

    def explode(path, *a, **kw):
        if VERDICTS_FILENAME in str(path):
            raise OSError("read-only file system")
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", explode)
    parser.parse(req.report_path)
    monkeypatch.undo()

    assert os.path.exists(os.path.join(rd, TRIAGE_FILENAME)), (
        "the only surviving copy of the verdicts was deleted"
    )
    assert not os.path.exists(os.path.join(rd, VERDICTS_FILENAME))
