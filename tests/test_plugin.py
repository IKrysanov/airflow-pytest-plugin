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

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402

from airflow_pytest_plugin import plugin as plugin_mod  # noqa: E402
from airflow_pytest_plugin.plugin import (  # noqa: E402
    URL_PREFIX,
    PytestReportsPlugin,
)


def test_plugin_name():
    assert PytestReportsPlugin.name == "pytest_reports"


def test_fastapi_app_registered():
    apps = PytestReportsPlugin.fastapi_apps
    assert len(apps) == 1
    entry = apps[0]
    assert entry["url_prefix"] == URL_PREFIX
    assert entry["name"]
    assert isinstance(entry["app"], FastAPI)


def test_external_view_href_has_trailing_slash():
    # Regression: the trailing slash hits the mounted app's index, not the Airflow SPA.
    view = PytestReportsPlugin.external_views[0]
    assert view["href"] == f"{URL_PREFIX}/"
    assert view["href"].endswith("/")
    assert view["url_route"] == "pytest-reports"
    assert view["destination"] == "nav"


def test_fastapi_apps_degrade_when_build_fails(monkeypatch):
    # If app construction fails, registration is empty rather than crashing discovery.
    import airflow_pytest_plugin.web as web

    def _boom(*args, **kwargs):
        raise RuntimeError("no fastapi")

    monkeypatch.setattr(web, "create_app", _boom)
    assert plugin_mod._build_fastapi_apps() == []
