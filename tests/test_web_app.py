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

import re
import shutil
import subprocess

import pytest

from airflow_pytest_plugin.compat import airflow_auth_available
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import write_allure, write_report, write_report_xml, write_tests

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from airflow_pytest_plugin.web import create_app  # noqa: E402

_TEST_USER = object()


def make_app(reports_root, *, authorizer=None, read_authorizer=None):
    """App with a stub user + injectable authz, so routing/filtering stay Airflow-independent."""
    return create_app(
        FileSystemReportSource(report_root=reports_root),
        authorizer=authorizer or (lambda dag_id, user: True),
        read_authorizer=read_authorizer or (lambda dag_id, user: True),
        user_dependency=lambda: _TEST_USER,
    )


@pytest.fixture
def client(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=2, failed=1)
    return TestClient(make_app(reports_root))


def test_health(client, reports_root):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # The report root (where the producer writes and the reader reads) is reported,
    # and the fixture wrote a report there so it exists -> ready.
    assert body["reports_root"] == reports_root
    assert body["ready"] is True and body["reports_root_exists"] is True
    assert body["auth"] == ("airflow" if airflow_auth_available() else "open")
    assert isinstance(body["secure_xml"], bool)


def test_health_not_ready_when_root_missing(tmp_path):
    body = TestClient(make_app(str(tmp_path / "absent"))).get("/api/health").json()
    assert body["status"] == "ok"  # liveness still ok...
    assert (
        body["ready"] is False and body["reports_root_exists"] is False
    )  # ...not ready


def test_version_endpoint(client):
    body = client.get("/api/version").json()
    assert body["name"] == "airflow-pytest-plugin"
    assert isinstance(body["version"], str) and body["version"]


@pytest.mark.skipif(
    airflow_auth_available(), reason="exercises the no-Airflow standalone path"
)
def test_standalone_app_without_injected_user(reports_root):
    # No injected user and no Airflow auth -> the "_no_user" path works with None user.
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=1)
    c = TestClient(create_app(FileSystemReportSource(report_root=reports_root)))
    token = c.get("/api/reports").json()["reports"][0]["id"]
    assert c.get(f"/api/reports/{token}").status_code == 200


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Pytest Reports" in r.text


def test_index_has_feature_markers(client):
    # Regression guard that the UI feature markers are all present in the page.
    html = client.get("/").text
    for marker in (
        "data-i18n",
        'id="chart"',
        'id="d-copy"',
        "setReportParam",
        "ru:",
        'id="confirm"',
        'id="d-delete"',
        "row-del",
        "data-status",
        "#017cee",
        'id="chart-nav"',
        "chart-bars",
        "af-link",
        "bindTip",
        "downloadAllure",
        "CHART_VISIBLE",
        "bars-strip",
        "enableChartDrag",
        "assignSeq",
        "closeOnBackdrop",
        "PAGE_SIZE",
        'id="f-task"',
        'id="d-allure"',
        "openFailures",
        "kpi-failures",
        "setParentDim",
        "openCompare",
        'id="cmp-prev"',
        "previousRun",
        "openFlaky",
        "openHistory",
        "flakyMeta",
        "quarantineBadge",
        "trendArrow",
        'id="flk-win"',
        "flkScoreTip",
        'id="flk-board-q"',
        'id="flk-board-qonly"',
        "flkSearch",
        "flkNoMatch",
        'id="chart-filter"',
        "renderChartFilterNote",
        "clearSelection",
        "chartSelected",
        "fillCases",
        'id="case-q"',
        'id="links-btn"',
        'id="links-menu"',
        "ofWord",
        "renderFlakyBoard",
        "fillBench",
        'id="board"',
        "bench-scroll",
        "refreshUniqueTests",
        "Unique tests",
        "openUnique",
        "fillUnique",
        "kpi-unique",
        "forbidden",
    ):
        assert marker in html


def test_inline_script_is_syntactically_valid(client, tmp_path):
    # The viewer's JS lives in a Python string; syntax-check each inline <script> with Node.
    node = shutil.which("node")
    if not node:
        pytest.skip("node unavailable to syntax-check the inline JS")
    html = client.get("/").text
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts, "no inline <script> found in the page"
    for i, code in enumerate(scripts):
        script = tmp_path / f"viewer_{i}.js"
        script.write_text(code, encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(script)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"script #{i}: {result.stderr}"


def test_openapi_and_docs_serve(client):
    # The header's docs link opens these; future annotations once 500'd the schema.
    assert client.get("/api/docs").status_code == 200
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    doc = spec.json()
    paths = doc["paths"]
    assert "/api/flaky" in paths and "/api/test-history" in paths
    # Routes are grouped into the documented sections; the UI assets stay out of it.
    assert [t["name"] for t in doc["tags"]] == [
        "monitoring",
        "reports",
        "failures",
        "compare",
        "flaky",
    ]
    assert paths["/api/flaky"]["get"]["tags"] == ["flaky"]
    assert paths["/api/compare"]["get"]["tags"] == ["compare"]
    assert paths["/api/health"]["get"]["tags"] == ["monitoring"]
    assert paths["/api/version"]["get"]["tags"] == ["monitoring"]
    assert "/icon.svg" not in paths and "/" not in paths  # icons + viewer hidden
    assert paths["/api/flaky"]["get"]["summary"]  # every method has a summary


def test_icon_routes(client):
    for path in ("/icon.svg", "/icon-dark.svg"):
        r = client.get(path)
        assert r.status_code == 200
        assert "image/svg+xml" in r.headers["content-type"]
        assert "<svg" in r.text


def test_list_endpoint(client):
    r = client.get("/api/reports")
    assert r.status_code == 200
    reports = r.json()["reports"]
    assert len(reports) == 1
    assert reports[0]["dag_id"] == "dag"
    assert reports[0]["failed"] == 1


def test_reports_success_reflects_pass_rate_threshold(reports_root):
    # A run with a failure but a 90% pass rate counts as successful at the default
    # 0.85 bar -> drives the "Passing runs" KPI and the PASS status badge.
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=9, failed=1)
    r = TestClient(make_app(reports_root)).get("/api/reports").json()["reports"][0]
    assert r["failed"] == 1 and r["success"] is True


def test_detail_endpoint_round_trips_token(client):
    token = client.get("/api/reports").json()["reports"][0]["id"]
    r = client.get(f"/api/reports/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["cases"]) == 3


def test_detail_bad_token_is_400(client):
    assert client.get("/api/reports/%21%21bad").status_code == 400


def test_detail_unknown_report_is_404(client):
    token = ReportRef("nope", "nope", "nope", 9).token
    assert client.get(f"/api/reports/{token}").status_code == 404


def test_delete_endpoint_removes_report(client):
    token = client.get("/api/reports").json()["reports"][0]["id"]
    r = client.delete(f"/api/reports/{token}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    # Gone from both list and detail.
    assert client.get("/api/reports").json()["reports"] == []
    assert client.get(f"/api/reports/{token}").status_code == 404


def test_delete_unknown_is_404(client):
    token = ReportRef("nope", "nope", "nope", 9).token
    assert client.delete(f"/api/reports/{token}").status_code == 404


def test_delete_bad_token_is_400(client):
    assert client.delete("/api/reports/%21%21bad").status_code == 400


def test_delete_forbidden_when_authorizer_denies(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=1)
    c = TestClient(make_app(reports_root, authorizer=lambda dag_id, user: False))
    token = c.get("/api/reports").json()["reports"][0]["id"]
    assert c.delete(f"/api/reports/{token}").status_code == 403
    # The report survives a denied delete.
    assert len(c.get("/api/reports").json()["reports"]) == 1


def test_delete_allowed_when_authorizer_permits(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=1)
    c = TestClient(make_app(reports_root, authorizer=lambda dag_id, user: True))
    token = c.get("/api/reports").json()["reports"][0]["id"]
    assert c.delete(f"/api/reports/{token}").status_code == 200
    assert c.get("/api/reports").json()["reports"] == []


def test_list_hides_reports_the_user_cannot_read(reports_root):
    write_report(reports_root, ReportRef("seen", "r", "t", 1), passed=1)
    write_report(reports_root, ReportRef("hidden", "r", "t", 1), passed=1)
    c = TestClient(
        make_app(reports_root, read_authorizer=lambda dag_id, user: dag_id != "hidden")
    )
    dags = [r["dag_id"] for r in c.get("/api/reports").json()["reports"]]
    assert dags == ["seen"]


def test_detail_forbidden_when_read_denied(reports_root):
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=1)
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag_id, user: False))
    token = ReportRef("dag", "r", "t", 1).token
    assert c.get(f"/api/reports/{token}").status_code == 403


def test_read_and_delete_authz_are_independent(reports_root):
    # Read and delete are separate permissions: a viewer may open but not delete.
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=1)
    c = TestClient(
        make_app(
            reports_root,
            authorizer=lambda dag_id, user: False,  # may not delete
            read_authorizer=lambda dag_id, user: True,  # may read
        )
    )
    token = c.get("/api/reports").json()["reports"][0]["id"]
    assert c.get(f"/api/reports/{token}").status_code == 200
    assert c.delete(f"/api/reports/{token}").status_code == 403
    assert len(c.get("/api/reports").json()["reports"]) == 1


def test_allure_zip_endpoint(reports_root):
    import io
    import zipfile

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=1)
    write_allure(reports_root, ref)
    c = TestClient(make_app(reports_root))
    token = c.get("/api/reports").json()["reports"][0]["id"]
    r = c.get(f"/api/reports/{token}/allure.zip")
    assert r.status_code == 200
    assert "application/zip" in r.headers["content-type"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert "abc-result.json" in zf.namelist()


def test_allure_zip_404_when_absent(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=1)
    c = TestClient(make_app(reports_root))
    token = c.get("/api/reports").json()["reports"][0]["id"]
    assert c.get(f"/api/reports/{token}/allure.zip").status_code == 404


def test_allure_zip_403_when_read_denied(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=1)
    write_allure(reports_root, ref)
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag_id, user: False))
    assert c.get(f"/api/reports/{ref.token}/allure.zip").status_code == 403


def test_allure_zip_bad_token_is_400(client):
    assert client.get("/api/reports/%21%21bad/allure.zip").status_code == 400


def test_list_exposes_has_allure(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=1)
    write_allure(reports_root, ref)
    c = TestClient(make_app(reports_root))
    assert c.get("/api/reports").json()["reports"][0]["has_allure"] is True


def test_failures_lists_failed_and_error_cases(reports_root):
    write_report(
        reports_root,
        ReportRef("dag", "run", "task", 1),
        passed=2,
        failed=3,
        errors=1,
        skipped=1,
    )
    write_report(
        reports_root, ReportRef("dag2", "run", "task", 1), passed=4
    )  # excluded
    c = TestClient(make_app(reports_root))
    d = c.get("/api/failures").json()
    assert d["total"] == 4 and d["capped"] is False
    assert sorted({f["outcome"] for f in d["failures"]}) == ["error", "failed"]
    assert all(
        f["dag_id"] == "dag" for f in d["failures"]
    )  # the all-pass run is skipped


def test_failures_respects_task_filter(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "alpha", 1), passed=1, failed=2)
    write_report(reports_root, ReportRef("dag", "run", "beta", 1), passed=1, failed=3)
    c = TestClient(make_app(reports_root))
    d = c.get("/api/failures?task_id=alpha").json()
    assert d["total"] == 2 and all(f["task_id"] == "alpha" for f in d["failures"])


def test_failures_hides_unreadable_runs(reports_root):
    write_report(reports_root, ReportRef("seen", "r", "t", 1), passed=1, failed=2)
    write_report(reports_root, ReportRef("hidden", "r", "t", 1), passed=1, failed=2)
    c = TestClient(
        make_app(reports_root, read_authorizer=lambda dag_id, user: dag_id != "hidden")
    )
    d = c.get("/api/failures").json()
    assert {f["dag_id"] for f in d["failures"]} == {"seen"}


def test_failures_empty_when_all_pass(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=5)
    c = TestClient(make_app(reports_root))
    assert c.get("/api/failures").json() == {
        "failures": [],
        "total": 0,
        "capped": False,
    }


def test_failures_skips_runs_with_unreadable_xml(reports_root):
    # meta marks the run as failing, but its junit.xml can't be parsed -> no cases.
    write_report_xml(
        reports_root,
        ReportRef("dag", "r", "t", 1),
        "<not-valid-xml",
        summary={
            "total": 2,
            "passed": 0,
            "failed": 2,
            "errors": 0,
            "skipped": 0,
            "success": False,
        },
    )
    c = TestClient(make_app(reports_root))
    assert c.get("/api/failures").json() == {
        "failures": [],
        "total": 0,
        "capped": False,
    }


def test_failures_capped(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.failures as failures_mod

    monkeypatch.setattr(failures_mod, "_FAILURES_CAP", 3)
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=1, failed=5)
    d = TestClient(make_app(reports_root)).get("/api/failures").json()
    assert d["capped"] is True and d["total"] == 3 and len(d["failures"]) == 3


def test_compare_diff_categories(reports_root):
    base, head = ReportRef("dag", "base", "t", 1), ReportRef("dag", "head", "t", 1)
    write_tests(
        reports_root,
        base,
        [["a", "passed"], ["b", "failed"], ["c", "failed"], ["d", "passed"]],
    )
    write_tests(
        reports_root,
        head,
        [["a", "failed"], ["b", "passed"], ["c", "failed"], ["e", "passed"]],
    )
    c = TestClient(make_app(reports_root))
    d = c.get(f"/api/compare?base={base.token}&head={head.token}").json()
    assert [x["node_id"] for x in d["newly_failed"]] == ["a"]
    assert [x["node_id"] for x in d["fixed"]] == ["b"]
    assert [x["node_id"] for x in d["still_failing"]] == ["c"]
    assert [x["node_id"] for x in d["added"]] == ["e"]
    assert [x["node_id"] for x in d["removed"]] == ["d"]
    assert d["counts"] == {
        "newly_failed": 1,
        "fixed": 1,
        "still_failing": 1,
        "added": 1,
        "removed": 1,
    }


def test_compare_bad_token_is_400(client):
    assert client.get("/api/compare?base=%21%21bad&head=%21%21bad").status_code == 400


def test_compare_missing_run_is_404(reports_root):
    base = ReportRef("dag", "base", "t", 1)
    write_tests(reports_root, base, [["a", "passed"]])
    head = ReportRef("dag", "gone", "t", 1).token
    c = TestClient(make_app(reports_root))
    assert c.get(f"/api/compare?base={base.token}&head={head}").status_code == 404


def test_compare_forbidden_when_read_denied(reports_root):
    base, head = ReportRef("dag", "base", "t", 1), ReportRef("dag", "head", "t", 1)
    write_tests(reports_root, base, [["a", "passed"]])
    write_tests(reports_root, head, [["a", "failed"]])
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag_id, user: False))
    assert c.get(f"/api/compare?base={base.token}&head={head.token}").status_code == 403


def test_flaky_finds_flipping_tests(reports_root):
    t = "task"
    write_tests(
        reports_root,
        ReportRef("dag", "r1", t, 1),
        [["a", "passed"], ["b", "passed"]],
        created_at="2026-06-01T00:00:00+00:00",
    )
    write_tests(
        reports_root,
        ReportRef("dag", "r2", t, 1),
        [["a", "failed"], ["b", "passed"]],
        created_at="2026-06-02T00:00:00+00:00",
    )
    write_tests(
        reports_root,
        ReportRef("dag", "r3", t, 1),
        [["a", "passed"], ["b", "passed"]],
        created_at="2026-06-03T00:00:00+00:00",
    )
    d = TestClient(make_app(reports_root)).get("/api/flaky").json()
    assert d["window"] == 30 and d["quarantine_score"] == 0.5
    assert {f["node_id"] for f in d["flaky"]} == {"a"}  # b is stable
    a = d["flaky"][0]
    assert a["runs"] == 3 and a["fails"] == 1 and a["flips"] == 2
    assert a["recent"] == ["passed", "failed", "passed"]
    # flaky-deeper fields: flip rate 2/2 = 1.0 -> quarantined; <4 runs -> flat trend
    assert a["score"] == 1.0 and a["quarantined"] is True and a["trend"] == "flat"


def test_flaky_stats_score_trend_quarantine():
    from airflow_pytest_plugin.web.routes.flaky import flaky_stats

    assert (
        flaky_stats(["passed"] * 5, quarantine_score=0.5) is None
    )  # stable -> not flaky
    alt = flaky_stats(["passed", "failed"] * 3, quarantine_score=0.5)
    assert alt["score"] == 1.0 and alt["quarantined"] is True  # flips every run
    # calm older half, flips concentrated late -> trend up; score below threshold
    blip = flaky_stats(["passed"] * 5 + ["failed", "passed"], quarantine_score=0.5)
    assert blip["flips"] == 2 and blip["trend"] == "up" and blip["quarantined"] is False


def test_flip_rate_and_trend_edges():
    from airflow_pytest_plugin.web.routes.flaky import _flip_rate, _trend

    assert _flip_rate([]) == 0.0 and _flip_rate(["passed"]) == 0.0  # len < 2
    assert _trend(["passed", "failed", "passed"]) == "flat"  # < 4 runs -> flat


def test_flaky_stats_min_score_filters_lone_blip():
    from airflow_pytest_plugin.web.routes.flaky import flaky_stats

    seq = ["passed"] * 20 + ["failed"]  # one fail in a long history -> flip rate 1/20
    assert flaky_stats(seq, min_score=0.0)["score"] == 0.05  # counts with floor off
    assert flaky_stats(seq, min_score=0.1) is None  # too steady -> filtered out


def test_flaky_excludes_lone_blip_via_min_score(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.flaky as flaky_mod

    # always passed, failed only in the latest run -> 1 flip / 11 = 0.09 < default 0.1
    for i in range(12):
        outcome = "failed" if i == 11 else "passed"
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i:02d}", "t", 1),
            [["a", outcome]],
            created_at=f"2026-06-{i + 1:02d}T00:00:00+00:00",
        )
    c = TestClient(make_app(reports_root))
    d = c.get("/api/flaky").json()
    assert d["min_score"] == 0.1 and d["flaky"] == []  # lone blip filtered out
    monkeypatch.setattr(flaky_mod, "get_flaky_min_score", lambda: 0.0)
    assert {f["node_id"] for f in c.get("/api/flaky").json()["flaky"]} == {
        "a"
    }  # floor off


def test_flaky_window_param_overrides_default(reports_root):
    for i, o in enumerate(["failed", "passed", "passed", "passed"], start=1):
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i}", "t", 1),
            [["a", o]],
            created_at=f"2026-06-0{i}T00:00:00+00:00",
        )
    c = TestClient(make_app(reports_root))
    assert c.get("/api/flaky?window=2").json()["flaky"] == []  # last 2 both passed
    d = c.get("/api/flaky?window=4").json()
    assert d["window"] == 4 and {f["node_id"] for f in d["flaky"]} == {"a"}


def test_flaky_quarantine_threshold_from_config(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.flaky as flaky_mod

    # a single mid blip -> score ~0.67; a high threshold leaves it un-quarantined
    for i, o in enumerate(["passed", "passed", "failed", "passed"], start=1):
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i}", "t", 1),
            [["a", o]],
            created_at=f"2026-06-0{i}T00:00:00+00:00",
        )
    monkeypatch.setattr(flaky_mod, "get_flaky_quarantine_score", lambda: 0.9)
    a = TestClient(make_app(reports_root)).get("/api/flaky").json()["flaky"][0]
    assert a["quarantined"] is False  # score ~0.67 < 0.9


def test_flaky_needs_two_runs(reports_root):
    write_tests(reports_root, ReportRef("dag", "r1", "t", 1), [["a", "failed"]])
    assert TestClient(make_app(reports_root)).get("/api/flaky").json()["flaky"] == []


def test_flaky_recent_strip_is_capped(reports_root):
    # 14 runs of a flipping test -> the recent-outcomes strip is trimmed to keep the UI tidy.
    for i in range(14):
        outcome = "failed" if i % 2 else "passed"
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i:02d}", "t", 1),
            [["a", outcome]],
            created_at=f"2026-06-{i + 1:02d}T00:00:00+00:00",
        )
    f = TestClient(make_app(reports_root)).get("/api/flaky").json()["flaky"][0]
    assert (
        f["runs"] == 14 and len(f["recent"]) == 10
    )  # full window counted, strip capped


def test_flaky_respects_window(reports_root):
    for i, o in enumerate(["failed", "passed", "passed"], start=1):
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i}", "t", 1),
            [["a", o]],
            created_at=f"2026-06-0{i}T00:00:00+00:00",
        )
    c = TestClient(make_app(reports_root))
    assert c.get("/api/flaky?window=2").json()["flaky"] == []  # last 2 both passed
    assert {f["node_id"] for f in c.get("/api/flaky?window=3").json()["flaky"]} == {"a"}


def test_flaky_task_filter(reports_root):
    for task in ("alpha", "beta"):
        write_tests(
            reports_root,
            ReportRef("dag", "r1", task, 1),
            [[task[0], "passed"]],
            created_at="2026-06-01T00:00:00+00:00",
        )
        write_tests(
            reports_root,
            ReportRef("dag", "r2", task, 1),
            [[task[0], "failed"]],
            created_at="2026-06-02T00:00:00+00:00",
        )
    d = TestClient(make_app(reports_root)).get("/api/flaky?task_id=alpha").json()
    assert {f["task_id"] for f in d["flaky"]} == {
        "alpha"
    }  # beta excluded by the filter


def test_flaky_hides_unreadable(reports_root):
    write_tests(reports_root, ReportRef("hidden", "r1", "t", 1), [["a", "passed"]])
    write_tests(reports_root, ReportRef("hidden", "r2", "t", 1), [["a", "failed"]])
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag_id, user: False))
    assert c.get("/api/flaky").json()["flaky"] == []


def test_test_history_timeline(reports_root):
    write_tests(
        reports_root,
        ReportRef("dag", "r1", "t", 1),
        [["a", "passed", 0.1]],
        created_at="2026-06-01T00:00:00+00:00",
    )
    write_tests(
        reports_root,
        ReportRef("dag", "r2", "t", 1),
        [["a", "failed", 0.2]],
        created_at="2026-06-02T00:00:00+00:00",
    )
    write_tests(
        reports_root,
        ReportRef("dag", "r3", "t", 1),
        [["b", "passed"]],
        created_at="2026-06-03T00:00:00+00:00",
    )
    d = (
        TestClient(make_app(reports_root))
        .get("/api/test-history?dag_id=dag&task_id=t&node_id=a")
        .json()
    )
    assert d["node_id"] == "a"
    assert [h["outcome"] for h in d["history"]] == [
        None,
        "failed",
        "passed",
    ]  # newest first
    assert d["history"][1]["duration"] == 0.2


def test_test_history_forbidden(reports_root):
    write_tests(reports_root, ReportRef("dag", "r1", "t", 1), [["a", "passed"]])
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag_id, user: False))
    assert c.get("/api/test-history?dag_id=dag&task_id=t&node_id=a").status_code == 403


def test_test_history_requires_node_id(client):
    assert client.get("/api/test-history?dag_id=d&task_id=t").status_code == 422


def test_unique_tests_counts_distinct_node_ids(reports_root):
    write_tests(
        reports_root, ReportRef("dag", "r1", "t", 1), [["a", "passed"], ["b", "failed"]]
    )
    write_tests(
        reports_root,
        ReportRef("dag", "r2", "t", 1),
        [["a", "passed"], ["b", "passed"], ["c", "passed"]],
    )
    write_tests(reports_root, ReportRef("dag2", "r1", "t", 1), [["x", "passed"]])
    c = TestClient(make_app(reports_root))
    # The KPI fetch is count-only (no list payload); the list rides ``full=1``.
    light = c.get("/api/unique-tests").json()
    assert light == {
        "count": 4,
        "capped": False,
    }  # a, b, c, x -- distinct, not 6 summed
    full = c.get("/api/unique-tests?full=1").json()
    assert [x["node_id"] for x in full["tests"]] == ["a", "b", "c", "x"]  # sorted
    assert full["tests"][3] == {"node_id": "x", "dag_id": "dag2", "task_id": "t"}


def test_unique_tests_scan_is_capped(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    monkeypatch.setattr(reports_mod, "_UNIQUE_SCAN_CAP", 2)
    # Three runs, each a distinct test; only the 2 newest are scanned -> count 2, capped.
    for i in range(3):
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i}", "t", 1),
            [[f"t{i}", "passed"]],
            created_at=f"2026-06-0{i + 1}T00:00:00+00:00",
        )
    d = TestClient(make_app(reports_root)).get("/api/unique-tests?full=1").json()
    assert d["count"] == 2 and d["capped"] is True
    assert sorted(x["node_id"] for x in d["tests"]) == ["t1", "t2"]  # newest two


def test_unique_tests_respects_filter_and_rbac(reports_root):
    write_tests(reports_root, ReportRef("keep", "r1", "t", 1), [["a", "passed"]])
    write_tests(reports_root, ReportRef("hide", "r1", "t", 1), [["z", "passed"]])
    c = TestClient(
        make_app(reports_root, read_authorizer=lambda dag_id, user: dag_id != "hide")
    )
    assert c.get("/api/unique-tests").json()["count"] == 1  # 'z' hidden by RBAC
    assert c.get("/api/unique-tests?dag_id=keep").json()["count"] == 1
    assert c.get("/api/unique-tests?dag_id=nope").json()["count"] == 0
    assert (
        c.get("/api/unique-tests?task_id=zzz").json()["count"] == 0
    )  # task filter excludes all
