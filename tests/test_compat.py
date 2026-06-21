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

import sys
import types

import pytest

from airflow_pytest_plugin.compat import airflow as compat


def _airflow_present() -> bool:
    try:
        import airflow  # noqa: F401

        return True
    except Exception:
        return False


def test_get_current_context_none_when_no_active_context():
    # No running task (and, in the unit env, no Airflow at all) -> None.
    assert compat.get_current_context() is None


def test_get_conf_value_none_when_unset():
    assert compat.get_conf_value("pytest_reports", "nope") is None


@pytest.mark.skipif(_airflow_present(), reason="exercises the Airflow-absent path")
def test_get_airflow_plugin_base_raises_without_airflow():
    with pytest.raises(ImportError):
        compat.get_airflow_plugin_base()


def test_get_current_context_reads_task_sdk(monkeypatch):
    # Inject a fake airflow.sdk so the Airflow-3 branch resolves and returns.
    airflow_mod = types.ModuleType("airflow")
    sdk = types.ModuleType("airflow.sdk")
    sdk.get_current_context = lambda: {"run_id": "r1", "ti": object()}
    monkeypatch.setitem(sys.modules, "airflow", airflow_mod)
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    ctx = compat.get_current_context()
    assert ctx is not None and ctx["run_id"] == "r1"


@pytest.mark.skipif(_airflow_present(), reason="exercises the Airflow-absent path")
def test_airflow_auth_unavailable_without_airflow():
    assert compat.airflow_auth_available() is False


def test_authorization_fails_closed_without_auth_manager():
    # No resolvable auth manager -> deny (fail closed) for both read and delete.
    assert compat.is_authorized_to_trigger("any_dag", object()) is False
    assert compat.is_authorized_to_read("any_dag", object()) is False


def _inject_module(monkeypatch, name, module):
    parts = name.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            monkeypatch.setitem(sys.modules, parent, types.ModuleType(parent))
    monkeypatch.setitem(sys.modules, name, module)


def test_is_authorized_to_trigger_calls_auth_manager(monkeypatch):
    rd = types.ModuleType("airflow.api_fastapi.auth.managers.models.resource_details")

    class DagAccessEntity:
        RUN = "RUN"

    class DagDetails:
        def __init__(self, id):
            self.id = id

    rd.DagAccessEntity = DagAccessEntity
    rd.DagDetails = DagDetails
    _inject_module(
        monkeypatch,
        "airflow.api_fastapi.auth.managers.models.resource_details",
        rd,
    )

    class FakeMgr:
        def is_authorized_dag(self, *, method, access_entity, details, user):
            # trigger -> POST, read -> GET, both on the DAG's runs.
            return (
                method in ("POST", "GET")
                and access_entity is DagAccessEntity.RUN
                and details.id == "d1"
            )

    app_mod = types.ModuleType("airflow.api_fastapi.app")
    app_mod.get_auth_manager = lambda: FakeMgr()
    _inject_module(monkeypatch, "airflow.api_fastapi.app", app_mod)

    assert compat.is_authorized_to_trigger("d1", object()) is True
    assert compat.is_authorized_to_read("d1", object()) is True
    assert compat.is_authorized_to_trigger("other_dag", object()) is False
    assert compat.is_authorized_to_read("other_dag", object()) is False


def test_get_current_context_falls_back_to_airflow2(monkeypatch):
    # SDK present but without the name -> the Airflow-2 path is taken.
    airflow_mod = types.ModuleType("airflow")
    sdk = types.ModuleType("airflow.sdk")  # no get_current_context
    ops_pkg = types.ModuleType("airflow.operators")
    ops = types.ModuleType("airflow.operators.python")
    ops.get_current_context = lambda: {"run_id": "r2"}
    monkeypatch.setitem(sys.modules, "airflow", airflow_mod)
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "airflow.operators", ops_pkg)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", ops)
    ctx = compat.get_current_context()
    assert ctx is not None and ctx["run_id"] == "r2"
