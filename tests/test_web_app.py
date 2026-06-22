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
from conftest import write_allure, write_report

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


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


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
