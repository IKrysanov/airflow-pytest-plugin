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

import pytest

from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import write_report

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from airflow_pytest_plugin.web import create_app  # noqa: E402


@pytest.fixture
def client(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), passed=2, failed=1)
    app = create_app(FileSystemReportSource(report_root=reports_root))
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Pytest Reports" in r.text


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
