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

"""Integration UI tests: the dashboard EMBEDDED in a real Airflow api-server.

Unlike the standalone ``ui`` suite (which drives ``python -m airflow_pytest_plugin.web``),
these boot a real Airflow 3 api-server, let the plugin register + mount its FastAPI app at
``/pytest-reports/``, and drive Playwright against that mount — proving the plugin loads,
mounts, and serves the working UI *under Airflow's own runtime and auth manager*.

Opt-in (marker ``ui_airflow``); needs Airflow + the ``ui-test`` extra + a browser. Run:
    pip install -e '.[web,ui-test]' apache-airflow==<v> --constraint <constraints>
    playwright install chromium
    pytest -m ui_airflow
"""

from __future__ import annotations

import json
import urllib.request

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui_airflow


def test_airflow_serves_embedded_dashboard(airflow_dash):
    page = airflow_dash.page
    expect(page.locator("#kpis")).to_be_visible()
    expect(page.locator(".chart-bars")).to_be_visible()
    assert page.locator("#kpis .kpi").count() == 5
    assert airflow_dash.errors == [], (
        f"JS errors in embedded app: {airflow_dash.errors}"
    )


def test_airflow_health_reports_real_auth_manager(airflow_base_url):
    # The mounted app sees Airflow's real auth manager (not the open standalone fallback).
    with urllib.request.urlopen(airflow_base_url + "api/health", timeout=10) as r:
        body = json.load(r)
    assert body["auth"] == "airflow"
    assert body["ready"] is True and body["reports_root_exists"] is True


def test_airflow_embedded_data_endpoints_work(airflow_dash):
    page = airflow_dash.page
    # KPIs populate from /pytest-reports/api/* served + authorized by Airflow (SMALL seed).
    expect(page.locator("#kpi-failures .value")).not_to_have_text("…", timeout=15000)
    assert page.locator("#kpi-failures .value").inner_text().strip() == "2"
    expect(page.locator("#kpi-unique .value")).not_to_have_text("…", timeout=15000)
    assert int(page.locator("#kpi-unique .value").inner_text().strip()) > 0
