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
    # The inline-JS single-page app must never be cached, or an upgrade keeps running old JS.
    assert "no-store" in r.headers.get("cache-control", "")


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
        "renderClusters",
        "openClusters",
        "failure-clusters",
        "cl-btn",
        "cl-item",
        "trend-danger",
        "trend-dot-bad",
        "kFailuresTip",
        "slowRowAvg",
        "slowSlowest",
        "uq-meta",
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
        'id="trend-toggle"',
        'id="f-clear"',
        "clearFilters",
        "leg-reset",
        "legendReset",
        "statusShown",
        "renderTrend",
        "trendToggle",
        "trend-line",
        "trend-thresh",
        "trend-on",
        'id="list-grp"',
        "groupReports",
        "listGroup",
        "lgrp",
        "gsel",
        "grp-runs",
        "syncGroupChecks",
        "groupVal",
        "groupMore",
        "gHeadCell",
        "gsort",
        "groupArrow",
        "headCells",
        "cPassRate",
        "rsort",
        "groupRunSort",
        "runComparator",
        "cAvgDur",
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
        "uqStats",
        "kpi-unique",
        "kpi-slow",
        "openSlow",
        "loadSlow",
        "refreshSlow",
        "slowQuery",
        "fillSlow",
        'id="slow"',
        "slowRowReg",
        "slowRegressing",
        "slowKpiTip",
        "renderCaseHead",
        "caseCmp",
        'id="case-head"',
        "forbidden",
        'id="flk-scope"',
        "flkSelScope",
        "selKeySet",
        "scopeClusters",
        "chart-range",
        "chart-avg",
        "updateChartMeta",
        "surface-glass",
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
    assert "/api/groups" in paths and paths["/api/groups"]["get"]["tags"] == ["reports"]
    assert "/api/slow" in paths and paths["/api/slow"]["get"]["tags"] == ["reports"]
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
    assert paths["/api/failure-clusters"]["get"]["tags"] == ["failures"]
    assert paths["/api/health"]["get"]["tags"] == ["monitoring"]
    assert paths["/api/version"]["get"]["tags"] == ["monitoring"]
    assert "/icon.svg" not in paths and "/" not in paths  # icons + viewer hidden
    assert paths["/api/flaky"]["get"]["summary"]  # every method has a summary

    # Responses are documented with a real JSON example (not a bare "string") ...
    def ex(path, method):
        return paths[path][method]["responses"]["200"]["content"]["application/json"][
            "example"
        ]

    assert "reports" in ex("/api/reports", "get")
    assert ex("/api/groups", "get")["groups"][0]["avg_duration"] is not None
    assert "flaky" in ex("/api/flaky", "get")
    assert ex("/api/slow", "get")["regressed"][0]["regressed"] is True
    assert ex("/api/failure-clusters", "get")["clusters"][0]["signature"]
    # ... and the error status codes each route can return are declared.
    for path, method in [
        ("/api/reports/{report_id}", "get"),
        ("/api/reports/{report_id}", "delete"),
        ("/api/compare", "get"),
    ]:
        codes = set(paths[path][method]["responses"])
        assert {"400", "403", "404"} <= codes, (path, method, codes)


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
    body = TestClient(make_app(reports_root)).get("/api/reports").json()
    r = body["reports"][0]
    assert r["failed"] == 1 and r["success"] is True
    # The threshold is echoed so the chart can draw the pass-rate gridline.
    assert body["success_threshold"] == 0.85


def test_summarize_groups_aggregates_by_dag_task():
    from airflow_pytest_plugin.models import ReportRef, ReportSummary
    from airflow_pytest_plugin.web.routes.reports import summarize_groups

    def mk(dag, task, run, created, *, success, errors=0, duration=0.1):
        return ReportSummary(
            ReportRef(dag, run, task, 1),
            1,
            1 if success else 0,
            0 if success else 1,
            0,
            errors,
            duration,
            success,
            created_at=created,
        )

    groups = summarize_groups(
        [
            mk("d", "t", "r1", "2026-06-01T00:00:00+00:00", success=True, duration=2.0),
            mk(
                "d", "t", "r2", "2026-06-03T00:00:00+00:00", success=False, duration=4.0
            ),  # newest of d·t
            mk("d", "u", "r3", "2026-06-02T00:00:00+00:00", success=True),
            mk("d", "e", "r4", "2026-05-01T00:00:00+00:00", success=False, errors=1),
        ]
    )
    by = {(g["dag_id"], g["task_id"]): g for g in groups}
    assert by[("d", "t")]["runs"] == 2 and by[("d", "t")]["passed"] == 1
    assert by[("d", "t")]["pass_rate"] == 0.5
    assert by[("d", "t")]["avg_duration"] == 3.0  # (2.0 + 4.0) / 2
    assert by[("d", "t")]["last_status"] == "failed"  # newest run (r2) failed
    assert (
        by[("d", "u")]["pass_rate"] == 1.0 and by[("d", "u")]["last_status"] == "passed"
    )
    assert by[("d", "e")]["last_status"] == "error"  # newest run errored
    # Ordered by most-recent activity (d·t Jun 3, d·u Jun 2, d·e May 1).
    assert [(g["dag_id"], g["task_id"]) for g in groups] == [
        ("d", "t"),
        ("d", "u"),
        ("d", "e"),
    ]


def test_groups_endpoint_and_rbac(reports_root):
    write_report(reports_root, ReportRef("dagA", "r1", "taskX", 1), passed=2)
    write_report(reports_root, ReportRef("dagA", "r2", "taskX", 1), passed=1, failed=1)
    write_report(reports_root, ReportRef("dagB", "r3", "taskY", 1), passed=3)
    body = TestClient(make_app(reports_root)).get("/api/groups").json()
    by = {(g["dag_id"], g["task_id"]): g for g in body["groups"]}
    assert body["total"] == 2
    assert by[("dagA", "taskX")]["runs"] == 2 and by[("dagB", "taskY")]["runs"] == 1
    # RBAC: a reader denied dagB sees only its permitted group.
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag, u: dag == "dagA"))
    assert {g["dag_id"] for g in c.get("/api/groups").json()["groups"]} == {"dagA"}


def test_slow_stats_pure():
    from airflow_pytest_plugin.web.routes.reports import slow_stats

    flat = slow_stats([1.0, 1.0, 1.0, 1.0], factor=1.3, min_delta=0.5)
    assert flat["avg"] == 1.0 and flat["regressed"] is False and flat["ratio"] == 1.0

    reg = slow_stats([1.0, 1.0, 3.0, 3.0], factor=1.3, min_delta=0.5)
    assert reg["old_avg"] == 1.0 and reg["new_avg"] == 3.0
    assert reg["ratio"] == 3.0 and reg["regressed"] is True

    # big ratio but the absolute slowdown is below the floor -> not a regression
    tiny = slow_stats([0.1, 0.1, 0.5, 0.5], factor=1.3, min_delta=0.5)
    assert tiny["ratio"] == 5.0 and tiny["regressed"] is False

    few = slow_stats([1.0, 9.0], factor=1.3, min_delta=0.5)  # < 4 runs -> no verdict
    assert few["runs"] == 2 and few["old_avg"] is None and few["regressed"] is False
    assert few["avg"] == 5.0 and few["last"] == 9.0

    empty = slow_stats([], factor=1.3, min_delta=0.5)
    assert empty["runs"] == 0 and empty["avg"] == 0.0 and empty["regressed"] is False

    # a test that sped back up in the recent half is NOT a regression
    faster = slow_stats([5.0, 5.0, 1.0, 1.0], factor=1.3, min_delta=0.5)
    assert faster["new_avg"] == 1.0 and faster["regressed"] is False

    # appeared from ~0s and is now slow -> regression with ratio None (infinite jump)
    appeared = slow_stats([0.0, 0.0, 2.0, 2.0], factor=1.3, min_delta=0.5)
    assert appeared["regressed"] is True and appeared["ratio"] is None


def _seed_slow_group(reports_root, dag="dag", task="t"):
    """4 runs where test 'a' doubles its duration in the recent half; 'b' stays fast."""
    durs = {"a": [1.0, 1.0, 5.0, 5.0], "b": [0.1, 0.1, 0.1, 0.1]}
    for i in range(4):
        write_tests(
            reports_root,
            ReportRef(dag, f"r{i}", task, 1),
            [["a", "passed", durs["a"][i]], ["b", "passed", durs["b"][i]]],
            created_at=f"2026-06-0{i + 1}T00:00:00+00:00",
        )


def test_slow_endpoint_regressions_and_slowest(reports_root):
    _seed_slow_group(reports_root)
    d = TestClient(make_app(reports_root)).get("/api/slow").json()
    assert d["window"] == 30 and d["factor"] == 1.3 and d["min_delta"] == 0.5
    assert {r["node_id"] for r in d["regressed"]} == {"a"}  # b is flat
    a = d["regressed"][0]
    assert a["old_avg"] == 1.0 and a["new_avg"] == 5.0 and a["ratio"] == 5.0
    # the slowest leaderboard ranks by average duration (a avg 3.0, b 0.1)
    assert [r["node_id"] for r in d["slowest"]] == ["a", "b"]
    assert d["slowest"][0]["avg"] == 3.0
    assert d["capped"] is False
    assert "baseline" not in d  # no per-run baseline leaks from this endpoint


def test_slow_endpoint_skips_single_run_and_caps_scan(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    # a one-off run -> not eligible for the "reliably slow" leaderboard despite 9s
    write_tests(
        reports_root,
        ReportRef("solo", "r0", "t", 1),
        [["only", "passed", 9.0]],
        created_at="2026-05-01T00:00:00+00:00",
    )
    _seed_slow_group(reports_root)  # a 4-run group (eligible)
    c = TestClient(make_app(reports_root))
    d = c.get("/api/slow").json()
    assert "only" not in {r["node_id"] for r in d["slowest"]} and d["capped"] is False
    # a tiny read budget skips whole groups and flags it
    monkeypatch.setattr(reports_mod, "_SLOW_SCAN_CAP", 1)
    assert c.get("/api/slow").json()["capped"] is True


def test_slow_endpoint_window_clamped_and_echoed(reports_root):
    _seed_slow_group(reports_root)
    c = TestClient(make_app(reports_root))
    assert c.get("/api/slow?window=4").json()["window"] == 4
    assert c.get("/api/slow?window=1").json()["window"] == 2  # clamped low
    assert c.get("/api/slow?window=999").json()["window"] == 200  # clamped high


def test_slow_endpoint_hides_unreadable(reports_root):
    _seed_slow_group(reports_root, dag="dagA")
    _seed_slow_group(reports_root, dag="dagB")
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag, u: dag == "dagA"))
    d = c.get("/api/slow").json()
    assert {r["dag_id"] for r in d["slowest"]} == {"dagA"}
    assert {r["dag_id"] for r in d["regressed"]} == {"dagA"}


def test_slow_endpoint_respects_filters(reports_root):
    _seed_slow_group(reports_root, dag="dagA", task="alpha")
    _seed_slow_group(reports_root, dag="dagB", task="beta")
    c = TestClient(make_app(reports_root))
    # task_id substring narrows to one group (mirrors the run list filters)
    d = c.get("/api/slow?task_id=alpha").json()
    assert {r["dag_id"] for r in d["slowest"]} == {"dagA"}
    assert {r["dag_id"] for r in d["regressed"]} == {"dagA"}
    # run_id narrows the considered runs (only r0 -> 1 run/group -> no verdicts)
    only_r0 = c.get("/api/slow?run_id=r0").json()
    assert only_r0["total_regressed"] == 0 and only_r0["slowest"] == []


def test_slow_factor_from_config(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    for i, dur in enumerate([1.0, 1.0, 2.0, 2.0]):  # ratio 2.0, delta 1.0
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i}", "t", 1),
            [["a", "passed", dur]],
            created_at=f"2026-06-0{i + 1}T00:00:00+00:00",
        )
    c = TestClient(make_app(reports_root))
    assert {r["node_id"] for r in c.get("/api/slow").json()["regressed"]} == {"a"}
    monkeypatch.setattr(reports_mod, "get_slow_factor", lambda: 3.0)
    assert c.get("/api/slow").json()["regressed"] == []  # 2.0× < 3.0× -> not flagged


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


# --- email a run summary (UI action) ----------------------------------------------------------
class _SpyMailer:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, *, subject, body, recipients, html=None, attachments=()) -> None:
        self.sent.append(
            {"subject": subject, "recipients": list(recipients), "html": html}
        )


def _first_token(c) -> str:
    return c.get("/api/reports").json()["reports"][0]["id"]


def test_reports_echoes_email_available(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    monkeypatch.setattr(reports_mod, "build_mailer", lambda: object())
    assert client.get("/api/reports").json()["email_available"] is True
    monkeypatch.setattr(reports_mod, "build_mailer", lambda: None)
    assert client.get("/api/reports").json()["email_available"] is False


def test_email_run_sends_to_configured_recipients(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    spy = _SpyMailer()
    monkeypatch.setattr(reports_mod, "build_mailer", lambda: spy)
    monkeypatch.setenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", "team@x.io")
    r = client.post(
        f"/api/reports/{_first_token(client)}/email"
    )  # no body -> configured
    assert r.status_code == 200 and r.json()["sent"] is True
    assert r.json()["recipients"] == ["team@x.io"]
    assert spy.sent and spy.sent[0]["recipients"] == ["team@x.io"]
    # Styled HTML is delivered (the client fixture's run failed -> red banner).
    assert spy.sent[0]["html"] and "#dc2626" in spy.sent[0]["html"]
    assert r.json()["kind"] == "failed"


def test_email_run_accepts_and_dedups_supplied_recipients(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    spy = _SpyMailer()
    monkeypatch.setattr(reports_mod, "build_mailer", lambda: spy)
    r = client.post(
        f"/api/reports/{_first_token(client)}/email",
        json={"recipients": ["a@x.io", "b@x.io", "a@x.io", "A@X.IO"]},
    )
    assert r.status_code == 200
    # Deduped case-insensitively (one mailbox = one send), first spelling kept, order kept.
    assert r.json()["recipients"] == ["a@x.io", "b@x.io"]
    assert spy.sent[0]["recipients"] == ["a@x.io", "b@x.io"]


def test_email_run_rejects_invalid_and_excess_recipients(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    spy = _SpyMailer()
    monkeypatch.setattr(reports_mod, "build_mailer", lambda: spy)
    token = _first_token(client)
    assert (
        client.post(
            f"/api/reports/{token}/email", json={"recipients": ["nope"]}
        ).status_code
        == 400
    )
    # A header-injection attempt in a recipient is rejected by validation.
    assert (
        client.post(
            f"/api/reports/{token}/email",
            json={"recipients": ["a@x.io\nBcc: evil@x.io"]},
        ).status_code
        == 400
    )
    too_many = {"recipients": [f"a{i}@x.io" for i in range(11)]}
    assert client.post(f"/api/reports/{token}/email", json=too_many).status_code == 400
    assert spy.sent == []  # nothing sent on any rejection


def test_email_run_no_recipients_is_400(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    monkeypatch.setattr(reports_mod, "build_mailer", lambda: _SpyMailer())
    monkeypatch.delenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", raising=False)
    r = client.post(
        f"/api/reports/{_first_token(client)}/email"
    )  # none configured/supplied
    assert r.status_code == 400


def test_email_run_no_transport_is_503(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    monkeypatch.setattr(reports_mod, "build_mailer", lambda: None)
    monkeypatch.setenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", "team@x.io")
    r = client.post(f"/api/reports/{_first_token(client)}/email")
    assert r.status_code == 503


def test_email_run_send_failure_is_502(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    class _Boom:
        def send(self, *, subject, body, recipients, html=None, attachments=()):
            raise RuntimeError("smtp down")

    monkeypatch.setattr(reports_mod, "build_mailer", lambda: _Boom())
    r = client.post(
        f"/api/reports/{_first_token(client)}/email", json={"recipients": ["a@x.io"]}
    )
    assert r.status_code == 502
    # The real reason is surfaced (type + message) so the UI can show something actionable.
    assert "smtp down" in r.json()["detail"] and "RuntimeError" in r.json()["detail"]


def test_email_run_bad_token_is_400_and_unknown_is_404(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    monkeypatch.setattr(reports_mod, "build_mailer", lambda: _SpyMailer())
    assert client.post("/api/reports/%21%21bad/email").status_code == 400
    gone = ReportRef("nope", "nope", "nope", 9).token
    assert client.post(f"/api/reports/{gone}/email").status_code == 404


def test_email_run_records_history_visible_in_detail(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    monkeypatch.setattr(reports_mod, "build_mailer", lambda: _SpyMailer())
    token = _first_token(client)
    assert client.get(f"/api/reports/{token}").json()["alerts"] == []  # empty at first
    assert (
        client.post(
            f"/api/reports/{token}/email", json={"recipients": ["a@x.io"]}
        ).status_code
        == 200
    )
    alerts = client.get(f"/api/reports/{token}").json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["manual"] is True and alerts[0]["ok"] is True
    assert alerts[0]["recipients"] == ["a@x.io"] and alerts[0]["kind"] == "failed"


def test_email_run_accepts_string_recipients_and_rejects_non_list(client, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    spy = _SpyMailer()
    monkeypatch.setattr(reports_mod, "build_mailer", lambda: spy)
    token = _first_token(client)
    # A comma/semicolon string is parsed + deduped like a list.
    r = client.post(
        f"/api/reports/{token}/email",
        json={"recipients": "a@x.io; b@x.io , A@X.IO"},
    )
    assert r.status_code == 200 and r.json()["recipients"] == ["a@x.io", "b@x.io"]
    # A non-list, non-string recipients value is a clear 400.
    r = client.post(
        f"/api/reports/{token}/email", json={"recipients": {"not": "a list"}}
    )
    assert r.status_code == 400 and "list of email" in r.json()["detail"]


def test_safe_reason_is_single_line_and_bounded():
    from airflow_pytest_plugin.web.routes.reports import _safe_reason

    out = _safe_reason(RuntimeError("line one\nline two\twith\rgaps"))
    assert "\n" not in out and "\r" not in out and "\t" not in out
    assert out.startswith("RuntimeError:")
    assert len(_safe_reason(ValueError("x" * 500))) <= 200
    assert _safe_reason(RuntimeError()) == "RuntimeError"  # empty message


def test_email_run_requires_read_permission(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.reports as reports_mod

    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=2, failed=1)
    monkeypatch.setattr(reports_mod, "build_mailer", lambda: _SpyMailer())
    token = _first_token(TestClient(make_app(reports_root)))
    denied = TestClient(make_app(reports_root, read_authorizer=lambda d, u: False))
    assert (
        denied.post(
            f"/api/reports/{token}/email", json={"recipients": ["a@x.io"]}
        ).status_code
        == 403
    )


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


def test_normalize_and_cluster_failures_pure():
    from airflow_pytest_plugin.web.routes.failures import (
        cluster_failures,
        normalize_error,
    )

    assert (
        normalize_error("AssertionError: expected 5 got 7")
        == "AssertionError: expected N got N"
    )
    assert normalize_error("conn 0xDEADbeef to 10.0.0.1") == "conn ADDR to N.N.N.N"
    assert (
        normalize_error("boom\n--- Captured stdout ---\nx") == "boom"
    )  # skips section header
    items = [
        {
            "id": "a",
            "dag_id": "d",
            "task_id": "t",
            "run_id": "r1",
            "created_at": "x",
            "node_id": "n1",
            "outcome": "failed",
            "message": "E: boom 1",
        },
        {
            "id": "b",
            "dag_id": "d",
            "task_id": "t",
            "run_id": "r2",
            "created_at": "y",
            "node_id": "n2",
            "outcome": "failed",
            "message": "E: boom 2",
        },
        {
            "id": "c",
            "dag_id": "d",
            "task_id": "t",
            "run_id": "r3",
            "created_at": "z",
            "node_id": "n3",
            "outcome": "error",
            "message": "Other",
        },
    ]
    cl = cluster_failures(items)
    assert cl[0]["signature"] == "E: boom N" and cl[0]["count"] == 2  # biggest first
    assert cl[0]["outcomes"] == ["failed"] and len(cl[0]["tests"]) == 2
    assert "message" not in cl[0]["tests"][0]  # raw message not leaked per test


def _xml_failures(cases):
    """Tiny JUnit body. cases: list of (classname, name, outcome, message)."""
    tc = []
    for cn, nm, oc, msg in cases:
        kind = {"failed": "failure"}.get(oc, oc)  # junit uses <failure>, not <failed>
        body = (
            f'<{kind} message="{msg}">{msg}</{kind}>'
            if oc in ("failed", "error")
            else ""
        )
        tc.append(
            f'<testcase classname="{cn}" name="{nm}" time="0.1">{body}</testcase>'
        )
    return (
        f'<testsuites><testsuite name="pytest" tests="{len(cases)}">'
        + "".join(tc)
        + "</testsuite></testsuites>"
    )


def test_failure_clusters_endpoint_groups_and_filters(reports_root):
    write_report_xml(
        reports_root,
        ReportRef("dagA", "r1", "task", 1),
        _xml_failures(
            [
                (
                    "tests/api.py",
                    "test_a",
                    "failed",
                    "AssertionError: expected 5 got 7",
                ),
                (
                    "tests/api.py",
                    "test_b",
                    "failed",
                    "AssertionError: expected 8 got 3",
                ),
                ("tests/api.py", "test_c", "error", "RuntimeError: boom"),
            ]
        ),
        summary={"total": 3, "passed": 0, "failed": 2, "errors": 1},
    )
    write_report_xml(
        reports_root,
        ReportRef("dagB", "r2", "task", 1),
        _xml_failures(
            [("tests/x.py", "test_d", "failed", "AssertionError: expected 1 got 9")]
        ),
        summary={"total": 1, "passed": 0, "failed": 1, "errors": 0},
    )
    c = TestClient(make_app(reports_root))
    d = c.get("/api/failure-clusters").json()
    top = d["clusters"][0]
    assert top["signature"] == "AssertionError: expected N got N" and top["count"] == 3
    assert d["total"] == 4 and d["capped"] is False
    # RBAC: deny dagB -> its failure drops out
    cc = TestClient(
        make_app(reports_root, read_authorizer=lambda dag, u: dag == "dagA")
    )
    dd = cc.get("/api/failure-clusters").json()
    assert dd["total"] == 3
    assert {x["dag_id"] for cl in dd["clusters"] for x in cl["tests"]} == {"dagA"}
    # run_id filter scopes to a single run (the in-run view)
    assert c.get("/api/failure-clusters?run_id=r2").json()["total"] == 1


def test_normalize_error_masks_and_first_line():
    from airflow_pytest_plugin.web.routes.failures import _error_line, normalize_error

    assert (
        normalize_error("E: id 550e8400-e29b-41d4-a716-446655440000 at 0xAB12 n=7")
        == "E: id UUID at ADDR n=N"
    )
    assert (
        normalize_error("first\n--- Captured ---\nx") == "first"
    )  # skips section header
    assert _error_line("--- only ---") == "--- only ---"  # fallback: no non-header line
    assert normalize_error("") == "" and normalize_error(None) == ""
    assert len(normalize_error("x" * 500)) == 200  # capped


def test_cluster_failures_caps_tests_not_count():
    from airflow_pytest_plugin.web.routes.failures import (
        _CLUSTER_TESTS_CAP,
        cluster_failures,
    )

    items = [
        {
            "id": str(i),
            "dag_id": "d",
            "task_id": "t",
            "run_id": "r",
            "created_at": "x",
            "node_id": f"n{i}",
            "outcome": "failed",
            "message": "same boom",
        }
        for i in range(_CLUSTER_TESTS_CAP + 50)
    ]
    cl = cluster_failures(items)
    assert len(cl) == 1
    assert cl[0]["count"] == _CLUSTER_TESTS_CAP + 50  # exact count...
    assert len(cl[0]["tests"]) == _CLUSTER_TESTS_CAP  # ...list capped


def test_slow_endpoint_zero_baseline_ranks_first(reports_root):
    durs = {"a": [0.0, 0.0, 3.0, 3.0], "b": [1.0, 1.0, 2.0, 2.0]}
    for i in range(4):
        write_tests(
            reports_root,
            ReportRef("dag", f"r{i}", "t", 1),
            [["a", "passed", durs["a"][i]], ["b", "passed", durs["b"][i]]],
            created_at=f"2026-06-0{i + 1}T00:00:00+00:00",
        )
    d = TestClient(make_app(reports_root)).get("/api/slow").json()
    reg = [r["node_id"] for r in d["regressed"]]
    assert set(reg) == {"a", "b"}
    assert (
        reg[0] == "a"
    )  # 0->slow (infinite ratio) ranks before finite-ratio regression


def test_unique_tests_same_node_across_tasks_merges(reports_root):
    write_tests(
        reports_root,
        ReportRef("dagA", "r", "alpha", 1),
        [["shared", "passed", 1.0]],
        created_at="2026-06-02T00:00:00+00:00",  # newest
    )
    write_tests(
        reports_root,
        ReportRef("dagB", "r", "beta", 1),
        [["shared", "failed", 3.0]],
        created_at="2026-06-01T00:00:00+00:00",
    )
    d = TestClient(make_app(reports_root)).get("/api/unique-tests?full=1").json()
    assert d["count"] == 1  # distinct by node_id
    x = d["tests"][0]
    assert x["node_id"] == "shared" and x["runs"] == 2  # stats merged across dag·tasks
    assert x["passed"] == 1 and x["failed"] == 1
    assert (x["dag_id"], x["task_id"]) == ("dagA", "alpha")  # first-seen = newest run


def test_non_finite_duration_is_sanitized(reports_root):
    import os

    from airflow_pytest_plugin.layout import META_FILENAME, ReportLayout

    ref = ReportRef("dag", "r", "t", 1)
    d = ReportLayout().dir_for(reports_root, ref)
    os.makedirs(d, exist_ok=True)
    meta = {
        "schema_version": 1,
        "dag_id": "dag",
        "run_id": "r",
        "task_id": "t",
        "try_number": 1,
        "map_index": -1,
        "created_at": "2026-06-01T00:00:00+00:00",
        "report_file": "junit.xml",
        "summary": {"total": 1, "passed": 1, "failed": 0},
        "tests": [["a", "passed", float("inf")]],  # corrupt/crafted duration
    }
    with open(os.path.join(d, META_FILENAME), "w") as fh:
        json.dump(meta, fh)  # stdlib json writes "Infinity"
    body = TestClient(make_app(reports_root)).get("/api/unique-tests?full=1")
    assert "Infinity" not in body.text and "NaN" not in body.text  # valid JSON out
    assert body.json()["tests"][0]["avg_duration"] == 0.0  # sanitized


def test_failures_latest_retry_green_hides_failed_try(reports_root):
    # same dag·run·task: try 1 failed, try 2 passed, EQUAL created_at -> the newer try
    # wins the tie (try_number tiebreaker) so "current" is green.
    when = "2026-06-01T00:00:00+00:00"
    write_report_xml(
        reports_root,
        ReportRef("dag", "r", "t", 1),
        _xml_failures([("tests/a.py", "x", "failed", "Boom")]),
        summary={"total": 1, "passed": 0, "failed": 1},
        created_at=when,
    )
    write_report(reports_root, ReportRef("dag", "r", "t", 2), passed=1, created_at=when)
    c = TestClient(make_app(reports_root))
    assert (
        c.get("/api/failures").json()["total"] == 0
    )  # try 2 (newer) green -> nothing now
    assert c.get("/api/failures?latest=0").json()["total"] == 1  # history keeps try 1


def test_failures_latest_only_drops_fixed_tests(reports_root):
    # same dag·task: an OLD failing run, then a NEWER green run -> the failure is "fixed"
    write_report_xml(
        reports_root,
        ReportRef("dag", "old", "t", 1),
        _xml_failures([("tests/a.py", "test_x", "failed", "Boom")]),
        summary={"total": 1, "passed": 0, "failed": 1},
        created_at="2026-06-01T00:00:00+00:00",
    )
    write_report(
        reports_root,
        ReportRef("dag", "new", "t", 1),
        passed=3,
        created_at="2026-06-02T00:00:00+00:00",  # newer, all green
    )
    c = TestClient(make_app(reports_root))
    # default (current): latest run is green -> the old failure has dropped off
    assert c.get("/api/failures").json()["total"] == 0
    assert c.get("/api/failure-clusters").json()["total"] == 0
    # full history still has it
    assert c.get("/api/failures?latest=0").json()["total"] == 1
    assert c.get("/api/failure-clusters?latest=0").json()["total"] == 1


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


def test_flaky_endpoint_caps_scan(reports_root, monkeypatch):
    import airflow_pytest_plugin.web.routes.flaky as flaky_mod

    # Two flaky dag·task groups (each flips a: passed -> failed across two runs).
    for dag in ("d1", "d2"):
        write_tests(
            reports_root,
            ReportRef(dag, "r1", "t", 1),
            [["a", "passed"]],
            created_at="2026-06-01T00:00:00+00:00",
        )
        write_tests(
            reports_root,
            ReportRef(dag, "r2", "t", 1),
            [["a", "failed"]],
            created_at="2026-06-02T00:00:00+00:00",
        )
    c = TestClient(make_app(reports_root))
    full = c.get("/api/flaky").json()
    assert full["total"] == 2 and full["capped"] is False  # both groups fit the budget
    # a tiny read budget stops after the first group and flags it
    monkeypatch.setattr(flaky_mod, "_FLAKY_SCAN_CAP", 1)
    capped = c.get("/api/flaky").json()
    assert capped["total"] == 1 and capped["capped"] is True


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


def test_test_history_merges_across_dag_tasks(reports_root):
    # The SAME node id, run from two different dag·tasks (e.g. shared conftest test).
    write_tests(
        reports_root,
        ReportRef("dag1", "r1", "unit", 1),
        [["shared", "passed", 0.1]],
        created_at="2026-06-01T00:00:00+00:00",
    )
    write_tests(
        reports_root,
        ReportRef("dag2", "r1", "smoke", 1),
        [["shared", "failed", 0.2]],
        created_at="2026-06-02T00:00:00+00:00",
    )
    # No dag/task -> merged timeline across every place the node ran.
    d = (
        TestClient(make_app(reports_root))
        .get("/api/test-history?node_id=shared")
        .json()
    )
    assert d["node_id"] == "shared"
    assert d["dag_id"] is None and d["task_id"] is None  # merged, not scoped
    assert [h["outcome"] for h in d["history"]] == ["failed", "passed"]  # newest first
    assert {(h["dag_id"], h["task_id"]) for h in d["history"]} == {
        ("dag1", "unit"),
        ("dag2", "smoke"),
    }


def test_test_history_merged_respects_rbac(reports_root):
    write_tests(
        reports_root,
        ReportRef("dag1", "r1", "unit", 1),
        [["shared", "passed"]],
        created_at="2026-06-01T00:00:00+00:00",
    )
    write_tests(
        reports_root,
        ReportRef("dag2", "r1", "smoke", 1),
        [["shared", "failed"]],
        created_at="2026-06-02T00:00:00+00:00",
    )
    # Only dag1 is readable -> the merged timeline excludes dag2's run.
    c = TestClient(
        make_app(reports_root, read_authorizer=lambda dag_id, user: dag_id == "dag1")
    )
    d = c.get("/api/test-history?node_id=shared").json()
    assert {(h["dag_id"], h["task_id"]) for h in d["history"]} == {("dag1", "unit")}


def test_unique_tests_counts_distinct_node_ids(reports_root):
    write_tests(
        reports_root,
        ReportRef("dag", "r1", "t", 1),
        [["a", "passed", 1.0], ["b", "failed", 0.5], ["d", "error", 0.0]],
    )
    write_tests(
        reports_root,
        ReportRef("dag", "r2", "t", 1),
        [
            ["a", "passed", 3.0],
            ["b", "passed", 0.5],
            ["c", "passed", 0.0],
            ["d", "skipped", 0.0],
        ],
    )
    write_tests(reports_root, ReportRef("dag2", "r1", "t", 1), [["x", "passed", 0.0]])
    c = TestClient(make_app(reports_root))
    # The KPI fetch is count-only (no list payload); the list rides ``full=1``.
    light = c.get("/api/unique-tests").json()
    assert light == {"count": 5, "capped": False}  # a, b, c, d, x distinct
    full = c.get("/api/unique-tests?full=1").json()
    assert [x["node_id"] for x in full["tests"]] == ["a", "b", "c", "d", "x"]  # sorted
    by = {x["node_id"]: x for x in full["tests"]}
    # per-test stats aggregated from the same scan (no extra I/O)
    assert (
        by["a"]["runs"] == 2
        and by["a"]["passed"] == 2
        and by["a"]["avg_duration"] == 2.0
    )
    assert by["b"]["passed"] == 1 and by["b"]["failed"] == 1
    assert by["d"]["runs"] == 2 and by["d"]["errors"] == 1 and by["d"]["skipped"] == 1
    assert by["x"] == {
        "node_id": "x",
        "dag_id": "dag2",
        "task_id": "t",
        "runs": 1,
        "passed": 1,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "avg_duration": 0.0,
    }


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


# --- hardening: a lax custom source must degrade, never 500 --------------------------


def test_endpoints_tolerate_source_rows_without_outcome(reports_root):
    """Every ``test_outcomes`` consumer must survive a row lacking "outcome".

    The filesystem source always writes the key, but the ``ReportSource`` contract is
    open to custom implementations — a missing key must degrade to unknown/None, not
    take the endpoint down with a KeyError 500.
    """

    class LaxSource(FileSystemReportSource):
        def test_outcomes(self, ref):  # noqa: ARG002 - same shape for every run
            return {"t.py::a": {"duration": 0.1}}

    base = ReportRef("dag", "r1", "t", 1)
    head = ReportRef("dag", "r2", "t", 1)
    write_report(reports_root, base, created_at="2026-06-21T10:00:00+00:00")
    write_report(reports_root, head, created_at="2026-06-21T11:00:00+00:00")
    c = TestClient(
        create_app(
            LaxSource(report_root=reports_root),
            authorizer=lambda dag_id, user: True,
            read_authorizer=lambda dag_id, user: True,
            user_dependency=lambda: _TEST_USER,
        )
    )

    assert c.get("/api/flaky").status_code == 200
    heat = c.get("/api/heatmap?dag_id=dag&task_id=t")
    assert heat.status_code == 200
    assert [t["node_id"] for t in heat.json()["tests"]] == ["t.py::a"]
    assert c.get(f"/api/compare?base={base.token}&head={head.token}").status_code == 200
    hist = c.get("/api/test-history?dag_id=dag&task_id=t&node_id=t.py::a")
    assert hist.status_code == 200
    entry = hist.json()["history"][0]
    assert entry["outcome"] is None and entry["duration"] == 0.1


def test_token_with_smuggled_junk_bytes_is_rejected(client):
    # Lax base64 silently skips non-alphabet bytes, so 4 CRLF chars inside a valid
    # token used to decode "successfully" and carry the raw string into logs
    # (CodeQL: log injection). Strict decoding must 400 it on every endpoint.
    good = ReportRef("dag", "run", "task", 1).token
    dirty = good[:10] + "%0D%0A%0D%0A" + good[10:]  # \r\n\r\n url-encoded in the path
    assert client.get(f"/api/reports/{dirty}").status_code == 400
    assert client.post(f"/api/reports/{dirty}/email", json={}).status_code == 400
    assert client.delete(f"/api/reports/{dirty}").status_code == 400


def test_email_endpoint_log_lines_are_single_line(reports_root, monkeypatch, caplog):
    # The report token is unsigned, so its decoded dag_id/run_id can carry newlines.
    # Every log line the email endpoint emits must be sanitized to ONE line so a crafted
    # request can't forge extra log entries (CodeQL: log injection).
    import logging

    from airflow_pytest_plugin.models import ReportRef

    ref = ReportRef("dag\nFAKE LOG LINE", "run\r\ninjected", "task", 1, -1)
    write_report(reports_root, ref, passed=1)

    class _SpyMailer:
        def send(
            self, **kw
        ):  # succeeds -> the audit _log.info fires with the ref fields
            pass

    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.build_mailer", lambda: _SpyMailer()
    )
    monkeypatch.setenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", "team@example.com")
    c = TestClient(make_app(reports_root))
    with caplog.at_level(logging.INFO):
        r = c.post(f"/api/reports/{ref.token}/email", json={})
    assert r.status_code == 200
    for rec in caplog.records:
        assert "\n" not in rec.getMessage() and "\r" not in rec.getMessage()


def test_common_all_declares_its_cross_module_exports():
    # ERR_400/403/404 are imported by sibling route modules but not referenced inside
    # common.py, so CodeQL's intra-module unused-global check flags them unless they're
    # in __all__. Pin __all__ so a refactor can't silently drop them (and re-trigger it).
    from airflow_pytest_plugin.web.routes import common

    for name in ("ERR_400", "ERR_403", "ERR_404"):
        assert name in common.__all__
        assert isinstance(getattr(common, name), dict) and getattr(common, name)
    # No dangling name in __all__ (every export must resolve).
    for name in common.__all__:
        assert hasattr(common, name), f"__all__ lists undefined {name!r}"


def _fresh_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def test_detail_bakes_coverage_from_xcom_then_serves_without_reread(
    reports_root, monkeypatch
):
    # A just-finished run's coverage lands in XCom slightly after the report is archived,
    # so the detail route probes XCom, bakes the value into the report, and thereafter
    # serves it from the report (no further XCom round-trip). Fresh run -> keeps probing
    # until coverage appears.
    write_report(
        reports_root, ReportRef("dag", "run", "task", 1), created_at=_fresh_iso()
    )
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "run", "task", 1, -1).token

    # Not committed yet -> null (bench hidden); a fresh run is NOT negative-cached.
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage",
        lambda *a: None,
    )
    assert c.get(f"/api/reports/{tok}").json()["coverage"] is None

    # Operator committed 0.83 -> surfaced verbatim AND baked into the report.
    xcom_calls = []
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage",
        lambda dag, run, task, mi: (xcom_calls.append(1), 0.83)[1],
    )
    assert c.get(f"/api/reports/{tok}").json()["coverage"] == 0.83
    assert len(xcom_calls) == 1  # XCom read once

    # Now XCom raises if touched -> coverage still 0.83, served from the report (baked in),
    # and XCom is NOT queried again (it's part of the report now).
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage",
        lambda *a: (_ for _ in ()).throw(AssertionError("XCom must not be re-read")),
    )
    assert c.get(f"/api/reports/{tok}").json()["coverage"] == 0.83


def test_detail_negative_cache_stops_reprobing_settled_run(reports_root, monkeypatch):
    # A run old enough to have settled (default fixed created_at is well in the past) with
    # no XCom coverage never will -- the route probes ONCE, then serves null from an
    # in-process negative cache without hammering the shared metadata DB on every view.
    write_report(reports_root, ReportRef("dag", "old", "task", 1))
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "old", "task", 1, -1).token

    probes = []
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage",
        lambda *a: (probes.append(1), None)[1],
    )
    assert c.get(f"/api/reports/{tok}").json()["coverage"] is None
    assert c.get(f"/api/reports/{tok}").json()["coverage"] is None
    assert c.get(f"/api/reports/{tok}").json()["coverage"] is None
    assert len(probes) == 1  # probed once, then negative-cached


def test_detail_fresh_run_keeps_probing_until_coverage_arrives(
    reports_root, monkeypatch
):
    # A fresh run (coverage may still be committing) is NOT negative-cached: each view
    # re-probes so late-arriving coverage is not permanently missed.
    write_report(
        reports_root, ReportRef("dag", "new", "task", 1), created_at=_fresh_iso()
    )
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "new", "task", 1, -1).token

    probes = []
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage",
        lambda *a: (probes.append(1), None)[1],
    )
    assert c.get(f"/api/reports/{tok}").json()["coverage"] is None
    assert c.get(f"/api/reports/{tok}").json()["coverage"] is None
    assert len(probes) == 2  # re-probed, not suppressed


def test_detail_coverage_not_probed_when_read_denied(reports_root, monkeypatch):
    # The XCom read AND the write-on-GET (record_coverage) sit AFTER the RBAC read gate.
    # A caller who may not read the run must never trigger either. Guards against a
    # regression that reorders the coverage block above the authz check.
    from airflow_pytest_plugin.sources.filesystem import FileSystemReportSource

    write_report(
        reports_root, ReportRef("dag", "run", "task", 1), created_at=_fresh_iso()
    )
    c = TestClient(make_app(reports_root, read_authorizer=lambda dag_id, user: False))
    tok = ReportRef("dag", "run", "task", 1, -1).token

    def _boom(*a, **k):
        raise AssertionError("coverage path must not run when read is denied")

    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage", _boom
    )
    monkeypatch.setattr(FileSystemReportSource, "record_coverage", _boom)
    assert c.get(f"/api/reports/{tok}").status_code == 403


def test_detail_records_coverage_once_with_map_index_and_tolerates_write_failure(
    reports_root, monkeypatch
):
    # The route must (a) pass the run's map_index through to the XCom read, (b) invoke
    # record_coverage exactly once with the decoded ref + value, and (c) still serve the
    # coverage even if that best-effort write fails (a write error must not break the GET).
    from airflow_pytest_plugin.sources.filesystem import FileSystemReportSource

    write_report(
        reports_root, ReportRef("dag", "run", "task", 1, 2), created_at=_fresh_iso()
    )
    tok = ReportRef("dag", "run", "task", 1, 2).token

    seen = {}
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage",
        lambda dag, run, task, mi: (seen.update(mi=mi), 0.5)[1],
    )
    baked = []
    monkeypatch.setattr(
        FileSystemReportSource,
        "record_coverage",
        lambda self, ref, cov: (baked.append((ref.map_index, cov)), True)[1],
    )
    c = TestClient(make_app(reports_root))
    assert c.get(f"/api/reports/{tok}").json()["coverage"] == 0.5
    assert seen["mi"] == 2  # decoded map_index reaches the XCom read
    assert baked == [(2, 0.5)]  # record_coverage called once with the ref + value

    # A write failure (record_coverage returns False) must not drop the value or 500.
    monkeypatch.setattr(
        FileSystemReportSource, "record_coverage", lambda self, ref, cov: False
    )
    r = c.get(f"/api/reports/{tok}")
    assert r.status_code == 200
    assert r.json()["coverage"] == 0.5


def test_detail_serves_archive_baked_coverage_without_touching_xcom(
    reports_root, monkeypatch
):
    # Producer-side coverage (parser coverage=True) writes the fraction into meta.json at
    # archive time, so the reader must serve it straight from the report -- never querying
    # the shared Airflow metadata DB, even for a brand-new run.
    from airflow_pytest_plugin.layout import ReportLayout

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, created_at=_fresh_iso())
    meta_path = ReportLayout().meta_path(reports_root, ref)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    meta["coverage"] = 0.77
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh)

    def boom(*a):  # any XCom probe is a regression
        raise AssertionError("XCom must not be queried when coverage is in the archive")

    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage", boom
    )
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "run", "task", 1, -1).token
    assert c.get(f"/api/reports/{tok}").json()["coverage"] == 0.77


def test_detail_echoes_the_coverage_threshold(reports_root, monkeypatch):
    # The viewer needs the configured bar to label the card; it rides on the detail
    # payload so the UI never has to guess (or hardcode) it.
    monkeypatch.setenv("AIRFLOW_PYTEST_SUCCESS_COVERAGE", "0.6")
    write_report(reports_root, ReportRef("dag", "run", "task", 1))
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "run", "task", 1, -1).token
    assert c.get(f"/api/reports/{tok}").json()["coverage_threshold"] == 0.6


def test_low_coverage_does_not_fail_the_run(reports_root, monkeypatch):
    # Coverage is presentational: a run far below the bar is STILL a successful run.
    # Enforcing coverage is the operator's cov_fail_under gate, not this viewer's job.
    monkeypatch.setenv("AIRFLOW_PYTEST_SUCCESS_COVERAGE", "0.9")
    from airflow_pytest_plugin.layout import ReportLayout

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, passed=3, failed=0)
    meta_path = ReportLayout().meta_path(reports_root, ref)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    meta["coverage"] = 0.10  # way below the 0.9 bar
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh)

    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "run", "task", 1, -1).token
    body = c.get(f"/api/reports/{tok}").json()
    assert body["coverage"] == 0.10 and body["coverage_threshold"] == 0.9
    assert body["success"] is True  # unaffected by the coverage shortfall
    listed = c.get("/api/reports").json()["reports"]
    assert [r["success"] for r in listed] == [True]


def test_run_pinned_coverage_threshold_outranks_the_env_var(reports_root, monkeypatch):
    # The suite's own bar wins over the global reader setting: a core library and a legacy
    # smoke suite need different standards, which one env var cannot express.
    monkeypatch.setenv("AIRFLOW_PYTEST_SUCCESS_COVERAGE", "0.9")
    from airflow_pytest_plugin.layout import ReportLayout

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    meta_path = ReportLayout().meta_path(reports_root, ref)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    meta["coverage"], meta["coverage_threshold"] = 0.55, 0.5
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh)

    c = TestClient(make_app(reports_root))
    body = c.get(f"/api/reports/{ReportRef('dag', 'run', 'task', 1, -1).token}").json()
    # 0.55 would be RED under the 0.9 env bar, but the run pinned 0.5 -> it passes.
    assert body["coverage_threshold"] == 0.5 and body["coverage"] == 0.55


def test_corrupt_pinned_threshold_falls_back_to_the_env_var(reports_root, monkeypatch):
    monkeypatch.setenv("AIRFLOW_PYTEST_SUCCESS_COVERAGE", "0.75")
    from airflow_pytest_plugin.layout import ReportLayout

    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    meta_path = ReportLayout().meta_path(reports_root, ref)
    for bogus in (42, "0.5", -1, None):
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        meta["coverage_threshold"] = bogus
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        c = TestClient(make_app(reports_root))
        tok = ReportRef("dag", "run", "task", 1, -1).token
        assert c.get(f"/api/reports/{tok}").json()["coverage_threshold"] == 0.75, bogus


def _bake(reports_root, ref, **fields):
    """Write extra keys straight into a run's meta.json."""
    from airflow_pytest_plugin.layout import ReportLayout

    meta_path = ReportLayout().meta_path(reports_root, ref)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    meta.update(fields)
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh)


def test_zero_coverage_is_served_and_never_reprobed(reports_root, monkeypatch):
    # 0.0 is falsy: `if not coverage` anywhere here would both hide the card and send the
    # reader back to the metadata DB on every open of a run that already has its answer.
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, created_at=_fresh_iso())
    _bake(reports_root, ref, coverage=0.0)

    def boom(*a):
        raise AssertionError("XCom probed for a run whose coverage is already 0.0")

    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage", boom
    )
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "run", "task", 1, -1).token
    body = c.get(f"/api/reports/{tok}").json()
    assert body["coverage"] == 0.0 and body["coverage"] is not None


def test_zero_pinned_threshold_is_honoured_not_treated_as_unset(
    reports_root, monkeypatch
):
    # A pinned 0 means "never mark this suite red" -- another falsy value that must not
    # silently fall through to the env default.
    monkeypatch.setenv("AIRFLOW_PYTEST_SUCCESS_COVERAGE", "0.9")
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    _bake(reports_root, ref, coverage=0.05, coverage_threshold=0.0)
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "run", "task", 1, -1).token
    assert c.get(f"/api/reports/{tok}").json()["coverage_threshold"] == 0.0


def test_coverage_boundaries_survive_the_round_trip(reports_root, monkeypatch):
    monkeypatch.delenv("AIRFLOW_PYTEST_SUCCESS_COVERAGE", raising=False)
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    tok = ReportRef("dag", "run", "task", 1, -1).token
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage", lambda *a: None
    )
    for value in (0.0, 0.5, 0.85, 1.0):
        _bake(reports_root, ref, coverage=value)
        c = TestClient(make_app(reports_root))
        assert c.get(f"/api/reports/{tok}").json()["coverage"] == value


def test_out_of_range_coverage_in_meta_is_dropped(reports_root, monkeypatch):
    # A hand-edited or corrupt meta must not put an impossible percentage on the card.
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage", lambda *a: None
    )
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref)
    tok = ReportRef("dag", "run", "task", 1, -1).token
    for bogus in (1.5, -0.1, "0.8", True, None):
        _bake(reports_root, ref, coverage=bogus)
        c = TestClient(make_app(reports_root))
        assert c.get(f"/api/reports/{tok}").json()["coverage"] is None, bogus


def test_archive_coverage_wins_over_a_disagreeing_xcom(reports_root, monkeypatch):
    # Both routes can be active at once. The archived value is the run's own record, so it
    # must win -- and the XCom must not be consulted to discover that.
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, created_at=_fresh_iso())
    _bake(reports_root, ref, coverage=0.42)
    monkeypatch.setattr(
        "airflow_pytest_plugin.web.routes.reports.get_run_coverage", lambda *a: 0.99
    )
    c = TestClient(make_app(reports_root))
    tok = ReportRef("dag", "run", "task", 1, -1).token
    assert c.get(f"/api/reports/{tok}").json()["coverage"] == 0.42


def test_index_ships_kpi_info_notes_in_both_languages(client):
    # The ⓘ notes on the KPI cards are part of the shipped page: guard the wiring, the
    # per-KPI keys, and that every note exists in BOTH dictionaries -- a key present only
    # in one silently falls back to English for the other locale.
    html = client.get("/").text
    for marker in ("kpi-info", "infoBtnHtml", "wireKpiInfo", "openPanelInfo"):
        assert marker in html, marker
    for key in ("unique", "failures", "slow", "coverage"):
        assert f'"{key}"' in html or f"'{key}'" in html, key
        assert f"{key}InfoTitle" in html and f"{key}InfoBody" in html, key
    # Both locales define every note (each key appears at least twice: en + ru).
    for key in ("unique", "failures", "slow", "coverage"):
        assert html.count(f"{key}InfoTitle") >= 2, key
        assert html.count(f"{key}InfoBody") >= 2, key
    assert html.count("kpiInfoAl") >= 2  # the ⓘ aria-label is localised too


def test_coverage_card_signals_state_in_words_not_only_colour(client):
    # WCAG: the tint must never be the only carrier of "passing / failing".
    html = client.get("/").text
    assert "covPass" in html and "covFail" in html
    assert "meets target" in html and "below target" in html  # en
    assert "ниже порога" in html  # ru
    # The card reads the run's own bar, defaulting to 0.85 if the payload omits it.
    assert "coverage_threshold" in html and "0.85" in html


def test_deep_link_params_are_all_cleared_on_close(client):
    # Guard the fix: closing a run must drop every param that can re-open it, not just
    # "report" -- otherwise the tracking link's dag/run/task reopen it on the next refresh.
    html = client.get("/").text
    assert "DEEP_LINK_PARAMS" in html
    for param in ("report", "dag", "run", "task", "try", "map"):
        assert f'"{param}"' in html, param


# --- cross-tenant RBAC sweep ------------------------------------------------------------
#: Every documented data route, with params that would surface the FORBIDDEN dag if the
#: route failed to filter. Health/version/metrics are excluded: they carry no per-dag data
#: (health/version) or run on a separate scrape-token model (metrics, covered separately).
_READ_ROUTES = [
    ("GET", "/api/reports", None),
    ("GET", "/api/reports?dag_id=secret", None),
    ("GET", "/api/groups", None),
    ("GET", "/api/groups?dag_id=secret", None),
    ("GET", "/api/failures", None),
    ("GET", "/api/failure-clusters", None),
    ("GET", "/api/flaky", None),
    ("GET", "/api/slow", None),
    ("GET", "/api/unique-tests?full=true", None),
]


def _make_two_tenant_root(reports_root):
    """One run each for a readable dag and a forbidden one, with distinct test names.

    Real reports (junit + meta) so the token-addressed routes have something to serve, with
    the per-test rows renamed so a leak is unmistakable in any response body.
    """
    for dag in ("public", "secret"):
        ref = ReportRef(dag, "r1", "task", 1)
        write_report(reports_root, ref, passed=0, failed=1)
        _bake(reports_root, ref, tests=[[f"tests/t.py::test_{dag}", "failed", 0.1]])


def test_no_read_route_leaks_a_forbidden_dag(reports_root):
    # The guarantee a shared deployment rests on: a user who may read only "public" must
    # never see "secret" -- its dag id, its task, or its test names -- through ANY route.
    # Swept in one place so a new endpoint added without a read_auth filter fails here.
    _make_two_tenant_root(reports_root)
    c = TestClient(
        make_app(reports_root, read_authorizer=lambda dag, u: dag == "public")
    )
    for method, path, _ in _READ_ROUTES:
        r = c.request(method, path)
        assert r.status_code == 200, (path, r.status_code)
        body = r.text
        assert "secret" not in body, f"{path} leaked the forbidden dag: {body[:300]}"
        assert "test_secret" not in body, f"{path} leaked a forbidden test id"

    # /api/test-history is swept separately: it echoes the caller's own node_id, so a raw
    # substring check would flag the request back at us. What matters is that the merged
    # history carries no run from the forbidden dag.
    hist = c.get("/api/test-history?node_id=tests/t.py::test_secret").json()
    assert hist["history"] == [], hist


def test_per_run_routes_refuse_a_forbidden_dag(reports_root):
    # Token-addressed routes must 403 rather than serve, even though the token itself is
    # guessable (it only encodes coordinates -- it is an identifier, never a capability).
    _make_two_tenant_root(reports_root)
    c = TestClient(
        make_app(reports_root, read_authorizer=lambda dag, u: dag == "public")
    )
    tok = ReportRef("secret", "r1", "task", 1, -1).token
    assert c.get(f"/api/reports/{tok}").status_code == 403
    assert c.get(f"/api/reports/{tok}/allure.zip").status_code == 403
    assert (
        c.post(f"/api/reports/{tok}/email", json={"recipients": ["a@b.co"]}).status_code
        == 403
    )
    assert c.get("/api/heatmap?dag_id=secret&task_id=task").status_code == 403
    assert (
        c.get("/api/test-history?node_id=x&dag_id=secret&task_id=task").status_code
        == 403
    )
    # ...and the readable one still works, so the filter isn't just denying everything.
    ok_tok = ReportRef("public", "r1", "task", 1, -1).token
    assert c.get(f"/api/reports/{ok_tok}").status_code == 200


def test_compare_refuses_when_either_side_is_forbidden(reports_root):
    # A diff reads TWO runs; permission on one must not carry the other into the response.
    _make_two_tenant_root(reports_root)
    c = TestClient(
        make_app(reports_root, read_authorizer=lambda dag, u: dag == "public")
    )
    pub = ReportRef("public", "r1", "task", 1, -1).token
    sec = ReportRef("secret", "r1", "task", 1, -1).token
    assert c.get(f"/api/compare?base={pub}&head={sec}").status_code == 403
    assert c.get(f"/api/compare?base={sec}&head={pub}").status_code == 403


def test_delete_needs_more_than_read(reports_root):
    # Read and delete are independent axes: a reader must not be able to destroy data.
    _make_two_tenant_root(reports_root)
    c = TestClient(
        make_app(
            reports_root,
            read_authorizer=lambda dag, u: True,  # may read everything
            authorizer=lambda dag, u: False,  # may delete nothing
        )
    )
    tok = ReportRef("public", "r1", "task", 1, -1).token
    assert c.get(f"/api/reports/{tok}").status_code == 200
    assert c.delete(f"/api/reports/{tok}").status_code == 403
    assert c.get(f"/api/reports/{tok}").status_code == 200  # still there


def test_standalone_without_airflow_serves_openly(reports_root, monkeypatch):
    # No Airflow at all = the bundled dev server: there is no user to authorize, and
    # allow-all is the documented behaviour (health reports auth="open").
    import airflow_pytest_plugin.web.app as app_mod

    monkeypatch.setattr(app_mod, "airflow_auth_available", lambda: False)
    monkeypatch.setattr(app_mod, "airflow_available", lambda: False)
    write_report(reports_root, ReportRef("dag", "run", "task", 1))
    c = TestClient(app_mod.create_app(FileSystemReportSource(report_root=reports_root)))
    assert len(c.get("/api/reports").json()["reports"]) == 1
    assert c.get("/api/health").json()["auth"] == "open"


def test_airflow_present_but_auth_broken_fails_closed(
    reports_root, monkeypatch, caplog
):
    # The dangerous middle case: we ARE inside Airflow but cannot reach its RBAC. Serving
    # every team's runs would be the worst reading of "auth unavailable" -- deny instead.
    import airflow_pytest_plugin.web.app as app_mod

    monkeypatch.setattr(app_mod, "airflow_auth_available", lambda: False)
    monkeypatch.setattr(app_mod, "airflow_available", lambda: True)
    write_report(reports_root, ReportRef("dag", "run", "task", 1))
    with caplog.at_level("ERROR"):
        c = TestClient(
            app_mod.create_app(FileSystemReportSource(report_root=reports_root))
        )
    assert c.get("/api/reports").json()["reports"] == []  # nothing is readable
    tok = ReportRef("dag", "run", "task", 1, -1).token
    assert c.get(f"/api/reports/{tok}").status_code == 403
    assert c.delete(f"/api/reports/{tok}").status_code == 403
    assert any("fails closed" in r.message for r in caplog.records), (
        "must be logged loudly"
    )


def test_locale_prefers_the_stored_choice_over_a_static_lang_attribute(client):
    # The stand bug: Airflow's served index.html carries a hardcoded lang="en" that never
    # changes when the user switches language, while i18next persists the real choice in
    # localStorage. Reading the attribute first pinned the plugin to English on a Russian
    # stand, so localeSignals must list the stored choice BEFORE the attribute.
    html = client.get("/").text
    assert "localeSignals" in html
    body = html[
        html.index("function localeSignals") : html.index("function detectLocale")
    ]
    assert body.index("i18nextLng") < body.index('getAttribute("lang")'), (
        "the stored i18next choice must outrank the parent's <html lang> attribute"
    )
    # And the startup race is covered: the parent may write the language after we boot.
    assert "catchLateLocale" in html
    assert "syncFromParent" in html and 'addEventListener("storage"' in html


def test_kpi_title_shrinks_to_stay_on_one_line(client):
    # The title must shrink rather than wrap: wrapping strands the "all" chip beside a
    # two-line block and reads as unrelated content. CSS pins it to one line; fitKpiLabels
    # scales it down to fit and re-runs on resize so it grows back when there is room.
    html = client.get("/").text
    assert "label-text" in html
    css = html[html.index(".kpi .label {") : html.index(".kpi .value {")]
    assert "display: flex" in css and "flex-wrap: nowrap" in css
    assert "white-space: nowrap" in css  # the title itself may not wrap
    assert (
        "flex: 0 0 auto" in css
    )  # badges keep their size instead of being pushed down
    assert "fitKpiLabels" in html and "KPI_LABEL_MIN" in html
    assert "refitKpiLabels" in html
    assert 'addEventListener("resize", refitKpiLabels)' in html
    # A wide enough card grid so shrinking never has to reach the floor and clip.
    assert "minmax(190px, 1fr)" in html
