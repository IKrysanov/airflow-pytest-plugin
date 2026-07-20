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
from conftest import write_allure, write_report, write_report_xml, write_tests


def test_missing_root_lists_nothing(reports_root):
    src = FileSystemReportSource(report_root=reports_root)
    assert src.list_summaries() == []


def test_list_summaries_caches_the_scan(reports_root):
    # Within the TTL the scan is reused -- a run added afterwards isn't seen yet.
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=100.0)
    write_tests(reports_root, ReportRef("d", "r1", "t", 1), [["a", "passed"]])
    assert {s.ref.run_id for s in src.list_summaries()} == {"r1"}  # scans + caches
    write_tests(reports_root, ReportRef("d", "r2", "t", 1), [["a", "passed"]])
    assert {s.ref.run_id for s in src.list_summaries()} == {"r1"}  # cached: r2 unseen


def test_scan_cache_ttl_zero_disables_caching(reports_root):
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    write_tests(reports_root, ReportRef("d", "r1", "t", 1), [["a", "passed"]])
    src.list_summaries()
    write_tests(reports_root, ReportRef("d", "r2", "t", 1), [["a", "passed"]])
    assert {s.ref.run_id for s in src.list_summaries()} == {"r1", "r2"}  # always fresh


def test_delete_invalidates_the_scan_cache(reports_root):
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=100.0)
    write_tests(reports_root, ReportRef("d", "r1", "t", 1), [["a", "passed"]])
    write_tests(reports_root, ReportRef("d", "r2", "t", 1), [["a", "passed"]])
    src.list_summaries()  # warm the cache with both
    assert src.delete(ReportRef("d", "r1", "t", 1)) is True
    assert {s.ref.run_id for s in src.list_summaries()} == {"r2"}  # rescanned: r1 gone


def test_list_summaries_filters_the_cached_scan(reports_root):
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=100.0)
    write_tests(reports_root, ReportRef("keep", "r1", "t", 1), [["a", "passed"]])
    write_tests(reports_root, ReportRef("other", "r2", "t", 1), [["b", "passed"]])
    src.list_summaries()  # cache the full scan
    assert {s.ref.dag_id for s in src.list_summaries(dag_id="keep")} == {"keep"}
    assert {s.ref.run_id for s in src.list_summaries(run_id="r2")} == {"r2"}


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


def _write_meta(reports_root, ref: ReportRef, summary) -> None:
    """Write a meta.json with a valid identity but a caller-supplied summary block."""
    out_dir = ReportLayout().dir_for(reports_root, ref)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "dag_id": ref.dag_id,
                "run_id": ref.run_id,
                "task_id": ref.task_id,
                "try_number": ref.try_number,
                "map_index": ref.map_index,
                "created_at": "2026-06-21T10:00:00+00:00",
                "summary": summary,
            },
            fh,
        )


def test_corrupt_summary_counts_do_not_crash_the_scan(reports_root):
    # A single sidecar with a non-numeric count must NOT take down the whole scan
    # (the identity is valid, so the run is kept with the bad count coerced to 0).
    write_report(reports_root, ReportRef("good", "r", "t", 1))
    _write_meta(
        reports_root,
        ReportRef("bad", "r", "t", 1),
        {"total": 3, "passed": "boom", "failed": 1, "errors": 0, "skipped": 0},
    )
    summaries = FileSystemReportSource(report_root=reports_root).list_summaries()
    assert {s.ref.dag_id for s in summaries} == {"good", "bad"}  # neither dropped
    bad = next(s for s in summaries if s.ref.dag_id == "bad")
    assert bad.passed == 0 and bad.failed == 1  # bad value -> 0, good value kept


def test_non_finite_duration_is_sanitized(reports_root):
    # inf/NaN durations would otherwise make the JSON serializer raise (non-spec JSON).
    for i, bad in enumerate(("inf", "-inf", "nan")):
        _write_meta(
            reports_root,
            ReportRef("dg", f"r{i}", "t", 1),
            {"total": 1, "passed": 1, "duration": bad},
        )
    summaries = FileSystemReportSource(report_root=reports_root).list_summaries()
    assert len(summaries) == 3
    import math

    assert all(math.isfinite(s.duration) and s.duration == 0.0 for s in summaries)


def test_summary_not_a_dict_is_tolerated(reports_root):
    # A summary that isn't even an object (a list) must degrade to zero counts, not crash.
    _write_meta(reports_root, ReportRef("dg", "r", "t", 1), [1, 2, 3])
    summaries = FileSystemReportSource(report_root=reports_root).list_summaries()
    assert len(summaries) == 1
    assert summaries[0].total == 0 and summaries[0].passed == 0


def test_get_detail_returns_none_on_corrupt_xml(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report_xml(reports_root, ref, "<not-valid-xml", summary={"total": 0})
    assert FileSystemReportSource(report_root=reports_root).get_detail(ref) is None


def test_get_detail_blocks_xxe_external_entity(reports_root):
    # A junit.xml with an external-entity DOCTYPE must be REJECTED by the hardened parser: the
    # entity is never resolved (no local file read), get_detail returns None, and nothing from
    # the referenced file leaks. Guards the defusedxml protection against XXE.
    ref = ReportRef("dag", "run", "task", 1)
    xxe = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE t [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<testsuites><testsuite name="p" tests="1" failures="1" errors="0" skipped="0" '
        'time="0.1"><testcase classname="x" name="t" time="0.1">'
        '<failure message="leak: &xxe;">body</failure></testcase></testsuite></testsuites>'
    )
    write_report_xml(reports_root, ref, xxe, summary={"total": 1, "failed": 1})
    src = FileSystemReportSource(report_root=reports_root)
    assert src.secure_xml is True  # the hardened (defusedxml) parser is active
    assert (
        src.get_detail(ref) is None
    )  # entity forbidden -> no detail, no leak, no crash


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


def test_allure_archive_zips_results(reports_root):
    import io
    import zipfile

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    write_allure(
        reports_root, ref, files={"a-result.json": '{"x":1}', "b-container.json": "{}"}
    )
    data = FileSystemReportSource(report_root=reports_root).allure_archive(ref)
    assert data is not None
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert set(zf.namelist()) == {"a-result.json", "b-container.json"}


def test_allure_archive_none_when_absent(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)  # no allure-results
    assert FileSystemReportSource(report_root=reports_root).allure_archive(ref) is None


def test_allure_archive_refuses_traversal(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    src = FileSystemReportSource(report_root=str(root))
    assert src.allure_archive(ReportRef("..", ".", ".", 1)) is None


def test_summary_has_allure_from_meta(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    assert (
        FileSystemReportSource(report_root=reports_root).list_summaries()[0].has_allure
        is False
    )
    write_allure(reports_root, ref)
    assert (
        FileSystemReportSource(report_root=reports_root).list_summaries()[0].has_allure
        is True
    )


def test_test_outcomes_from_meta(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_tests(reports_root, ref, [["t::a", "passed", 0.1], ["t::b", "failed", 0.2]])
    out = FileSystemReportSource(report_root=reports_root).test_outcomes(ref)
    assert out == {
        "t::a": {"outcome": "passed", "duration": 0.1},
        "t::b": {"outcome": "failed", "duration": 0.2},
    }


def test_test_outcomes_falls_back_to_junit(reports_root):
    # Older archive: meta carries no per-test map -> parse junit.xml.
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=2, failed=1)
    out = FileSystemReportSource(report_root=reports_root).test_outcomes(ref)
    assert out is not None and len(out) == 3
    assert sorted({v["outcome"] for v in out.values()}) == ["failed", "passed"]


def test_test_outcomes_none_when_absent(reports_root):
    out = FileSystemReportSource(report_root=reports_root).test_outcomes(
        ReportRef("nope", "nope", "nope", 1)
    )
    assert out is None


def test_test_outcomes_tolerates_malformed_rows(reports_root):
    # A semi-trusted meta with junk rows must not crash the read; bad rows are skipped
    # and non-finite durations coerced to 0.0.
    ref = ReportRef("dag", "run", "task", 1)
    out_dir = ReportLayout().dir_for(reports_root, ref)
    os.makedirs(out_dir, exist_ok=True)
    meta = {
        "schema_version": 1,
        "dag_id": "dag",
        "run_id": "run",
        "task_id": "task",
        "try_number": 1,
        "map_index": -1,
        "tests": [
            ["a", "passed", 0.1],
            ["b", "failed"],  # missing duration -> 0.0
            [None, "passed", 0.2],  # falsy node id -> skipped
            "not-a-row",  # not a list -> skipped
            ["c", "passed", float("inf")],  # non-finite -> 0.0
        ],
    }
    with open(os.path.join(out_dir, META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    out = FileSystemReportSource(report_root=reports_root).test_outcomes(ref)
    assert set(out) == {"a", "b", "c"}
    assert out["b"]["duration"] == 0.0 and out["c"]["duration"] == 0.0


def test_record_alert_concurrent_writes_do_not_clobber(reports_root):
    # Two threads recording history for the SAME run (unique tmp names) -> both survive,
    # the sidecar stays valid JSON (no torn write).
    import threading

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)

    def worker(i):
        src.record_alert(ref, {"at": f"t{i}", "kind": "passed", "ok": True})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    alerts = src.get_detail(ref).alerts
    assert (
        1 <= len(alerts) <= 12
    )  # at least one survived; file is valid JSON (parsed OK)


def test_test_outcomes_refuses_traversal(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    src = FileSystemReportSource(report_root=str(root))
    assert src.test_outcomes(ReportRef("..", ".", ".", 1)) is None


def test_test_outcomes_none_on_corrupt_junit(reports_root):
    # No per-test map in meta, and the junit can't be parsed -> None.
    ref = ReportRef("dag", "run", "task", 1)
    write_report_xml(reports_root, ref, "<not-valid", summary={})
    assert FileSystemReportSource(report_root=reports_root).test_outcomes(ref) is None


def test_success_follows_pass_rate_threshold(reports_root, monkeypatch):
    from airflow_pytest_plugin import config

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=9, failed=1)  # 90% pass, one failure
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)

    # Default threshold (0.85): a 90% run counts as successful despite the failure.
    monkeypatch.delenv(config.SUCCESS_THRESHOLD_ENV, raising=False)
    src = FileSystemReportSource(report_root=reports_root)
    assert src.list_summaries()[0].success is True
    assert src.get_detail(ref).summary.success is True

    # Raise the bar above 90% -> the same run is no longer successful.
    monkeypatch.setenv(config.SUCCESS_THRESHOLD_ENV, "0.95")
    strict = FileSystemReportSource(report_root=reports_root)
    assert strict.list_summaries()[0].success is False
    assert strict.get_detail(ref).summary.success is False


def test_report_size_zero_for_traversal_or_missing(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    src = FileSystemReportSource(report_root=str(root))
    assert src.report_size(ReportRef("..", ".", ".", 1)) == 0  # escapes root -> 0
    assert src.report_size(ReportRef("dag", "absent", "task", 1)) == 0  # no dir -> 0


def test_report_size_skips_vanished_files(reports_root, monkeypatch):
    # A file disappearing mid-walk must be skipped, not crash the measurement.
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=1)
    src = FileSystemReportSource(report_root=reports_root)
    assert src.report_size(ref) > 0  # sanity: real bytes before the patch

    def _boom(_path):
        raise OSError("vanished")

    monkeypatch.setattr("os.path.getsize", _boom)
    assert src.report_size(ref) == 0  # every file skipped -> 0, no exception


def test_base_source_optional_capabilities_default_none():
    from airflow_pytest_plugin.sources.base import ReportSource

    class _Min(ReportSource):
        def list_summaries(self, **_k):
            return []

        def get_detail(self, _ref):
            return None

        def delete(self, _ref):
            return False

    m = _Min()
    ref = ReportRef("d", "r", "t", 1)
    assert m.allure_archive(ref) is None
    assert m.test_outcomes(ref) is None
    assert m.report_size(ref) == 0  # size policy stays inert for such sources


def test_record_coverage_bakes_into_report_and_reads_back(reports_root):
    # record_coverage persists the fraction into meta.json so get_detail returns it as
    # a stable report field (no XCom needed on later views).
    from airflow_pytest_plugin.sources import FileSystemReportSource

    write_report(reports_root, ReportRef("d", "r1", "t", 1), passed=3)
    src = FileSystemReportSource(report_root=reports_root)
    ref = ReportRef("d", "r1", "t", 1, -1)

    assert src.get_detail(ref).coverage is None  # not measured yet
    assert src.record_coverage(ref, 0.8734) is True
    assert src.get_detail(ref).coverage == 0.8734  # baked in, read back
    # to_dict surfaces it for the API payload.
    assert src.get_detail(ref).to_dict()["coverage"] == 0.8734


def test_record_coverage_missing_run_is_false(reports_root):
    from airflow_pytest_plugin.sources import FileSystemReportSource

    src = FileSystemReportSource(report_root=reports_root)
    assert src.record_coverage(ReportRef("nope", "r", "t", 1, -1), 0.5) is False


def test_base_record_coverage_default_false():
    from airflow_pytest_plugin.sources.base import ReportSource

    class _Min(ReportSource):
        def list_summaries(self, **_k):
            return []

        def get_detail(self, _ref):
            return None

        def delete(self, _ref):
            return False

    assert _Min().record_coverage(ReportRef("d", "r", "t", 1), 0.9) is False


def test_record_coverage_refuses_traversal_token(tmp_path):
    # record_coverage is a WRITE triggered by a GET on an attacker-controlled token; its
    # _safe_dir guard must refuse a `..`/`.` traversal and write nothing outside the root.
    root = tmp_path / "reports"
    root.mkdir()
    outside = tmp_path / "t1"
    outside.mkdir()
    (outside / META_FILENAME).write_text('{"summary": {}}', encoding="utf-8")
    src = FileSystemReportSource(report_root=str(root))
    ref = ReportRef(dag_id="..", run_id=".", task_id=".", try_number=1)
    assert src.record_coverage(ref, 0.5) is False
    # The out-of-root meta must be byte-for-byte untouched (no coverage injected).
    assert (outside / META_FILENAME).read_text(encoding="utf-8") == '{"summary": {}}'


def test_coverage_from_meta_filters_bad_and_accepts_bounds():
    # _coverage_from_meta is the sanitiser on the read path: record_coverage does float()
    # with no range check, so a bad/hand-edited meta value must be filtered here, and the
    # inclusive [0,1] endpoints must pass.
    from airflow_pytest_plugin.sources.filesystem import _coverage_from_meta

    for bad in (
        {"coverage": 1.5},  # over 1.0
        {"coverage": -0.1},  # negative
        {"coverage": True},  # bool is not coverage
        {"coverage": False},
        {"coverage": "0.9"},  # wrong type
        {"coverage": None},  # unmeasured
        {},  # key absent
        None,  # no meta at all
    ):
        assert _coverage_from_meta(bad) is None, bad
    for frac in (0.0, 0.5, 1.0):
        assert _coverage_from_meta({"coverage": frac}) == frac


def test_record_coverage_write_failure_returns_false(reports_root, monkeypatch):
    # An OSError from the atomic replace must be swallowed (best-effort): record_coverage
    # returns False and never lets the exception escape into the GET route, and the run's
    # meta is left as-is (coverage not baked).
    write_report(reports_root, ReportRef("d", "r1", "t", 1), passed=1)
    src = FileSystemReportSource(report_root=reports_root)
    ref = ReportRef("d", "r1", "t", 1, -1)

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", _boom)
    assert src.record_coverage(ref, 0.5) is False
    assert src.get_detail(ref).coverage is None  # nothing baked


def test_record_coverage_overwrites_in_place(reports_root):
    # Idempotent: re-recording replaces the value (no torn/duplicate key), sidecar stays
    # valid single-object JSON with exactly one coverage entry.
    write_report(reports_root, ReportRef("d", "r1", "t", 1), passed=1)
    src = FileSystemReportSource(report_root=reports_root)
    ref = ReportRef("d", "r1", "t", 1, -1)

    assert src.record_coverage(ref, 0.4) is True
    assert src.record_coverage(ref, 0.9) is True
    assert src.get_detail(ref).coverage == 0.9
    meta_path = ReportLayout().dir_for(reports_root, ref) + "/" + META_FILENAME
    meta = json.loads(
        open(meta_path, encoding="utf-8").read()
    )  # still valid JSON object
    assert meta["coverage"] == 0.9


# --- streamed Allure download ------------------------------------------------------------
def test_allure_stream_matches_the_in_memory_archive(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    allure_dir = write_allure(reports_root, ref, {"a-result.json": '{"x":1}'})
    # A sub-directory too: Allure writes attachments alongside results, and the archive
    # must keep that structure rather than flattening it.
    os.makedirs(os.path.join(allure_dir, "nested"), exist_ok=True)
    with open(
        os.path.join(allure_dir, "nested", "b.json"), "w", encoding="utf-8"
    ) as fh:
        fh.write("{}")
    src = FileSystemReportSource(report_root=reports_root)

    streamed = b"".join(src.allure_stream(ref))
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(streamed))
    assert zf.testzip() is None
    names = set(zf.namelist())
    assert "a-result.json" in names
    assert any(n.endswith("b.json") for n in names)  # nested entries survive
    # Same content as the in-memory path (zip metadata may differ, the payload may not).
    mem = zipfile.ZipFile(io.BytesIO(src.allure_archive(ref)))
    assert {n: mem.read(n) for n in mem.namelist()} == {n: zf.read(n) for n in names}


def test_allure_stream_is_none_without_results(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    src = FileSystemReportSource(report_root=reports_root)
    assert src.allure_stream(ref) is None


def test_allure_stream_uses_no_temp_file_at_all(reports_root, tmp_path, monkeypatch):
    # Staging through a temp file would be a trap: /tmp is a RAM-backed tmpfs on many
    # container images and on a Kubernetes emptyDir{medium: Memory}, which would put the
    # archive right back in memory. Nothing may be written to the temp dir.
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    write_allure(reports_root, ref, {f"r{i}.json": "{}" * 500 for i in range(20)})
    src = FileSystemReportSource(report_root=reports_root)

    for chunk in src.allure_stream(ref):
        assert list(scratch.iterdir()) == [], "the archive was staged to the temp dir"
        assert chunk  # no empty chunks
    assert list(scratch.iterdir()) == []

    gen = src.allure_stream(ref)  # a cancelled download must leave nothing either
    next(gen)
    gen.close()
    assert list(scratch.iterdir()) == []


def test_allure_stream_never_holds_the_whole_archive(reports_root):
    # The point of streaming: peak buffering stays near the chunk size, not the archive
    # size. Several ~1 MB members with a 64 KB chunk must arrive incrementally.
    import random
    import string

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    # Incompressible payload, so the zip can't collapse to a single small chunk.
    payload = "".join(random.choice(string.ascii_letters) for _ in range(1_000_000))
    write_allure(reports_root, ref, {f"big{i}.json": payload for i in range(5)})
    src = FileSystemReportSource(report_root=reports_root)

    sizes = [len(c) for c in src.allure_stream(ref, chunk_size=65536)]
    assert len(sizes) > 20, f"expected many chunks, got {len(sizes)}"
    # A buffered build would emit one lump; no yield may exceed the chunk size.
    assert max(sizes) <= 65536, f"a chunk exceeded the chunk size: {max(sizes)}"


def test_allure_stream_skips_a_file_that_vanishes(reports_root):
    # Retention or a rerun can delete a result between the directory walk and the read.
    # Reproduced exactly: allure_stream lists the files eagerly, so deleting one before the
    # generator is consumed lands in that window. It must degrade to a smaller archive
    # rather than fail the download.
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    allure_dir = write_allure(reports_root, ref, {"keep.json": "{}", "gone.json": "{}"})
    src = FileSystemReportSource(report_root=reports_root)

    stream = src.allure_stream(ref)  # file list captured here...
    os.remove(os.path.join(allure_dir, "gone.json"))  # ...deleted before the first read

    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(b"".join(stream)))
    assert zf.testzip() is None
    assert "keep.json" in zf.namelist() and "gone.json" not in zf.namelist()


def test_allure_stream_survives_being_abandoned_midway(reports_root):
    # A cancelled download closes the generator at a yield. That unwinds through the open
    # ZipFile, whose close() writes the central directory into the sink -- it must not
    # raise or leave the generator complaining about an ignored GeneratorExit.
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    write_allure(reports_root, ref, {f"r{i}.json": "x" * 20000 for i in range(30)})
    src = FileSystemReportSource(report_root=reports_root)

    gen = src.allure_stream(ref, chunk_size=1024)
    next(gen)
    next(gen)
    gen.close()  # must be silent
    # A fresh stream right after still produces a complete, valid archive.
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(b"".join(src.allure_stream(ref))))
    assert zf.testzip() is None and len(zf.namelist()) == 30


def test_allure_stream_handles_a_directory_of_many_small_files(reports_root):
    # The central directory is written in one go on close; with thousands of members it
    # must still come out through the final drain rather than being dropped or truncated.
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    write_allure(
        reports_root, ref, {f"t-{i:04d}.json": f'{{"i":{i}}}' for i in range(2000)}
    )
    src = FileSystemReportSource(report_root=reports_root)

    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(b"".join(src.allure_stream(ref, chunk_size=4096))))
    assert zf.testzip() is None
    assert len(zf.namelist()) == 2000
    assert json.loads(zf.read("t-1999.json")) == {"i": 1999}


def test_allure_refuses_every_symlink(reports_root, tmp_path):
    # Allure results are written ON THE WORKER by arbitrary pytest code. A test that drops a
    # symlink into its own allure-results could otherwise exfiltrate whatever the READER
    # process can read (airflow.cfg, the Fernet key, ssh keys) to anyone allowed to download
    # the run, or by email attachment. Links are refused outright -- Allure never emits them,
    # and allowing "links that stay inside" would leave a swap-after-check window open.
    secret = tmp_path / "fernet.key"
    secret.write_text("AIRFLOW__CORE__FERNET_KEY=super-secret")

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    allure_dir = write_allure(reports_root, ref, {"real-result.json": '{"ok":true}'})
    os.symlink(secret, os.path.join(allure_dir, "escape-result.json"))
    os.symlink(
        os.path.join(allure_dir, "real-result.json"),
        os.path.join(allure_dir, "inside-result.json"),
    )

    src = FileSystemReportSource(report_root=reports_root)
    import io
    import zipfile

    for data in (b"".join(src.allure_stream(ref)), src.allure_archive(ref)):
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = set(zf.namelist())
        assert names == {"real-result.json"}, f"a symlink was archived: {names}"
        assert not any(b"super-secret" in zf.read(n) for n in names)


def test_allure_skips_a_fifo_instead_of_hanging(reports_root):
    # A named pipe passes any path-based check, and open() on it BLOCKS FOREVER waiting for
    # a writer -- pinning a server thread per download until the process is restarted. It
    # must be refused by file type, not by path.
    import threading

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    allure_dir = write_allure(reports_root, ref, {"real-result.json": "{}"})
    os.mkfifo(os.path.join(allure_dir, "pipe-result.json"))

    src = FileSystemReportSource(report_root=reports_root)
    done: list = []

    def build():
        done.append(b"".join(src.allure_stream(ref)))

    t = threading.Thread(target=build, daemon=True)
    t.start()
    t.join(timeout=20)
    assert not t.is_alive(), "the archive build blocked on a FIFO"

    import io
    import zipfile

    assert zipfile.ZipFile(io.BytesIO(done[0])).namelist() == ["real-result.json"]


def test_allure_survives_a_symlink_swapped_in_mid_stream(reports_root, tmp_path):
    # The swap-after-check race: entries are listed up front, so an attacker controlling the
    # directory can replace one with a symlink before it is read. Opening with O_NOFOLLOW
    # closes the window -- the read either gets the real file or nothing.
    secret = tmp_path / "secret.txt"
    secret.write_text("leak-me")

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    allure_dir = write_allure(
        reports_root, ref, {f"f{i}-result.json": "{}" for i in range(20)}
    )
    src = FileSystemReportSource(report_root=reports_root)

    stream = src.allure_stream(ref, chunk_size=512)  # listing happens here
    for i in range(20):  # ...swap every entry before a byte is read
        p = os.path.join(allure_dir, f"f{i}-result.json")
        os.remove(p)
        os.symlink(secret, p)

    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(b"".join(stream)))
    assert zf.testzip() is None
    assert not any(b"leak-me" in zf.read(n) for n in zf.namelist()), "secret leaked"


def test_allure_members_are_written_zip64_ready(reports_root):
    # The member size is unknown when its header goes out, so zipfile would decide "no
    # zip64" and then raise past ~2 GiB -- mid-stream, with bytes already on the wire.
    # force_zip64 avoids that; guard it by shrinking the limit rather than writing 2 GiB.
    import io
    import zipfile

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    write_allure(reports_root, ref, {"big-result.json": "x" * 50_000})
    src = FileSystemReportSource(report_root=reports_root)

    real_limit = zipfile.ZIP64_LIMIT
    zipfile.ZIP64_LIMIT = 1000  # stand in for the 2 GiB boundary
    try:
        data = b"".join(src.allure_stream(ref))  # must not raise
    finally:
        zipfile.ZIP64_LIMIT = real_limit
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.testzip() is None
    assert zf.getinfo("big-result.json").file_size == 50_000


def test_allure_ignores_a_symlinked_directory(reports_root, tmp_path):
    # os.walk does not descend into symlinked directories, so a linked tree contributes
    # nothing -- guard that this stays true rather than relying on a default.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.json").write_text('{"secret":"nope"}')

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    allure_dir = write_allure(reports_root, ref, {"real-result.json": "{}"})
    os.symlink(outside, os.path.join(allure_dir, "linked"))

    src = FileSystemReportSource(report_root=reports_root)
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(b"".join(src.allure_stream(ref))))
    assert zf.namelist() == ["real-result.json"]
