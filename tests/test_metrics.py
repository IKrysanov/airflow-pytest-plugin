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

"""Tests for the Prometheus ``/api/metrics`` endpoint: rendering, security, and load."""

from __future__ import annotations

import pytest

from airflow_pytest_plugin.config import METRICS_TOKEN_ENV, get_metrics_token
from airflow_pytest_plugin.models import ReportRef, ReportSummary
from airflow_pytest_plugin.web.routes import monitoring
from airflow_pytest_plugin.web.routes.monitoring import render_metrics

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from airflow_pytest_plugin.sources import FileSystemReportSource  # noqa: E402
from airflow_pytest_plugin.web import create_app  # noqa: E402
from conftest import write_report  # noqa: E402

_TOKEN = "s3cr3t-scrape-token"


def _sum(
    dag,
    task,
    run,
    *,
    passed,
    failed=0,
    errors=0,
    skipped=0,
    duration=1.0,
    created_at="2026-06-01T10:00:00+00:00",
    success=None,
):
    total = passed + failed + errors + skipped
    if success is None:
        success = (failed + errors) == 0
    return ReportSummary(
        ref=ReportRef(dag, run, task, 1, -1),
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration=duration,
        success=success,
        created_at=created_at,
    )


def _app(reports_root):
    return create_app(
        FileSystemReportSource(report_root=reports_root),
        authorizer=lambda d, u: True,
        read_authorizer=lambda d, u: True,
        user_dependency=lambda: object(),
    )


# --- render_metrics (pure) ----------------------------------------------------
def test_render_metrics_has_global_families_and_valid_format():
    out = render_metrics([_sum("dag", "t", "r1", passed=8, failed=2)])
    assert "# HELP airflow_pytest_up" in out and "# TYPE airflow_pytest_up gauge" in out
    assert "airflow_pytest_up 1" in out
    assert "airflow_pytest_runs 1" in out
    assert "airflow_pytest_dagtasks 1" in out
    assert 'airflow_pytest_build_info{version="' in out
    assert out.endswith("\n")
    # every non-comment line is "name{labels} value" or "name value"
    for line in out.splitlines():
        if line and not line.startswith("#"):
            assert line.rsplit(" ", 1)[1]  # has a value token


def test_render_metrics_uses_latest_run_per_group():
    summaries = [
        _sum("dag", "t", "old", passed=10, created_at="2026-06-01T00:00:00+00:00"),
        _sum(
            "dag",
            "t",
            "new",
            passed=6,
            failed=4,
            created_at="2026-06-02T00:00:00+00:00",
        ),
        # An even-older run seen AFTER the newest must not replace it.
        _sum("dag", "t", "older", passed=99, created_at="2026-05-01T00:00:00+00:00"),
    ]
    out = render_metrics(summaries)
    assert 'airflow_pytest_latest_failed{dag_id="dag",task_id="t"} 4' in out
    assert 'airflow_pytest_latest_passed{dag_id="dag",task_id="t"} 6' in out
    assert (
        'airflow_pytest_dagtask_runs{dag_id="dag",task_id="t"} 3' in out
    )  # all runs counted
    assert "airflow_pytest_runs 3" in out


def test_render_metrics_pass_ratio_success_and_failures_total():
    out = render_metrics(
        [
            _sum("a", "t", "r", passed=9, failed=1),  # ratio 0.9, NOT success
            _sum("b", "t", "r", passed=5),  # all pass -> success
            _sum("c", "t", "r", passed=1, errors=1, success=False),
        ]
    )
    assert 'airflow_pytest_latest_pass_ratio{dag_id="a",task_id="t"} 0.9' in out
    assert 'airflow_pytest_latest_success{dag_id="a",task_id="t"} 0' in out
    assert 'airflow_pytest_latest_success{dag_id="b",task_id="t"} 1' in out
    assert "airflow_pytest_latest_failures 2" in out  # a:1 failed + c:1 error


def test_render_metrics_escapes_label_values():
    # A malicious dag_id can't break the exposition format / inject series.
    out = render_metrics([_sum('ev"il\nx\\y', "t", "r", passed=1)])
    assert 'dag_id="ev\\"il\\nx\\\\y"' in out
    # the literal newline in the dag_id must be escaped, not split into a forged line
    assert not any(line.startswith("x") for line in out.splitlines())


def test_render_metrics_caps_cardinality():
    summaries = [_sum(f"d{i:04d}", "t", "r", passed=1) for i in range(50)]
    out = render_metrics(summaries, max_groups=10)
    assert "airflow_pytest_series_truncated 1" in out
    assert out.count("airflow_pytest_latest_passed{") == 10  # only the cap is emitted
    assert (
        "airflow_pytest_dagtasks 50" in out
    )  # ...but the true total is still reported


def test_render_metrics_empty_still_valid():
    out = render_metrics([])
    assert "airflow_pytest_up 1" in out
    assert "airflow_pytest_runs 0" in out
    assert "airflow_pytest_series_truncated 0" in out


def test_render_metrics_timestamp_skips_unparseable():
    summaries = [
        _sum("good", "t", "r", passed=1, created_at="2026-06-01T10:00:00+00:00"),
        _sum("none", "t", "r", passed=1, created_at=None),  # missing -> skipped
        _sum(
            "junk", "t", "r", passed=1, created_at="not-a-date"
        ),  # unparseable -> skipped
    ]
    out = render_metrics(summaries)
    assert 'airflow_pytest_latest_run_timestamp_seconds{dag_id="good"' in out
    assert 'airflow_pytest_latest_run_timestamp_seconds{dag_id="none"' not in out
    assert 'airflow_pytest_latest_run_timestamp_seconds{dag_id="junk"' not in out


def test_render_metrics_values_are_full_precision_not_scientific():
    # Regression: a unix timestamp must not be rounded to "1.78276e+09" (the %g bug).
    out = render_metrics(
        [_sum("d", "t", "r", passed=1, created_at="2026-06-01T10:00:00+00:00")]
    )
    ts_line = next(
        ln
        for ln in out.splitlines()
        if ln.startswith("airflow_pytest_latest_run_timestamp_seconds")
    )
    value = ts_line.rsplit(" ", 1)[1]
    assert "e" not in value.lower(), f"scientific notation lost precision: {value}"
    assert value.isdigit() and len(value) >= 10  # full unix-seconds, all digits


def test_render_metrics_scrape_duration_optional():
    assert "scrape_duration" not in render_metrics([_sum("d", "t", "r", passed=1)])
    assert "airflow_pytest_scrape_duration_seconds" in render_metrics(
        [_sum("d", "t", "r", passed=1)], scrape_seconds=0.01
    )


# --- endpoint: security -------------------------------------------------------
def test_metrics_disabled_by_default_returns_404(reports_root, monkeypatch):
    monkeypatch.delenv(METRICS_TOKEN_ENV, raising=False)
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=1)
    r = TestClient(_app(reports_root)).get("/api/metrics")
    assert r.status_code == 404


def test_metrics_requires_bearer_token(reports_root, monkeypatch):
    monkeypatch.setenv(METRICS_TOKEN_ENV, _TOKEN)
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=1)
    c = TestClient(_app(reports_root))
    assert c.get("/api/metrics").status_code == 401  # no header
    assert (
        c.get("/api/metrics", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    assert (
        c.get("/api/metrics", headers={"Authorization": _TOKEN}).status_code == 401
    )  # no scheme


def test_metrics_with_valid_token_returns_exposition(reports_root, monkeypatch):
    monkeypatch.setenv(METRICS_TOKEN_ENV, _TOKEN)
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=3, failed=1)
    r = TestClient(_app(reports_root)).get(
        "/api/metrics", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert "airflow_pytest_up 1" in r.text
    assert 'airflow_pytest_latest_failed{dag_id="dag",task_id="t"} 1' in r.text


def test_metrics_openapi_documents_bearer_scheme(reports_root):
    # The endpoint must advertise an HTTP bearer security scheme so Swagger renders an
    # "Authorize" box that actually sends the Authorization header (a plain header param
    # is silently dropped by Swagger UI).
    spec = TestClient(_app(reports_root)).get("/api/openapi.json").json()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert any(
        s.get("type") == "http" and s.get("scheme") == "bearer"
        for s in schemes.values()
    )


def test_metrics_bearer_scheme_is_case_insensitive(reports_root, monkeypatch):
    monkeypatch.setenv(METRICS_TOKEN_ENV, _TOKEN)
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=1)
    r = TestClient(_app(reports_root)).get(
        "/api/metrics", headers={"Authorization": f"bearer {_TOKEN}"}
    )
    assert r.status_code == 200


def test_metrics_token_from_config_when_env_unset(monkeypatch):
    monkeypatch.delenv(METRICS_TOKEN_ENV, raising=False)
    monkeypatch.setattr(
        "airflow_pytest_plugin.config.get_conf_value",
        lambda section, key: _TOKEN if key == "metrics_token" else None,
    )
    assert get_metrics_token() == _TOKEN


# --- endpoint: load-resilience ------------------------------------------------
def test_metrics_is_summary_only_no_per_run_reads(reports_root, monkeypatch):
    # The scrape must not parse JUnit per run. Prove it by making get_detail explode:
    # metrics still succeeds because it only uses list_summaries().
    monkeypatch.setenv(METRICS_TOKEN_ENV, _TOKEN)
    write_report(reports_root, ReportRef("dag", "r", "t", 1), passed=2, failed=1)
    src = FileSystemReportSource(report_root=reports_root)
    src.get_detail = lambda ref: (_ for _ in ()).throw(
        AssertionError("must not read details")
    )  # type: ignore[method-assign]
    app = create_app(
        src,
        authorizer=lambda d, u: True,
        read_authorizer=lambda d, u: True,
        user_dependency=lambda: object(),
    )
    r = TestClient(app).get(
        "/api/metrics", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert r.status_code == 200 and "airflow_pytest_up 1" in r.text


def test_metrics_endpoint_caps_series(reports_root, monkeypatch):
    monkeypatch.setenv(METRICS_TOKEN_ENV, _TOKEN)
    monkeypatch.setattr(monitoring, "_METRICS_MAX_GROUPS", 3)
    for i in range(6):
        write_report(reports_root, ReportRef(f"dag{i}", "r", "t", 1), passed=1)
    r = TestClient(_app(reports_root)).get(
        "/api/metrics", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert r.status_code == 200
    assert "airflow_pytest_series_truncated 1" in r.text
    assert r.text.count("airflow_pytest_latest_passed{") == 3
