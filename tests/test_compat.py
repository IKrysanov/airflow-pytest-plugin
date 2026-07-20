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

import os
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


@pytest.mark.skipif(_airflow_present(), reason="exercises the Airflow-absent path")
def test_airflow_email_unavailable_without_airflow():
    assert compat.airflow_email_available() is False


def test_send_airflow_email_maps_args_and_stages_attachments(monkeypatch):
    # The single spot that touches Airflow's mail API: verify the argument mapping
    # and that byte attachments become real file paths carrying the right bytes.
    captured: dict = {}

    def fake_send_email(*, to, subject, html_content, files):
        captured["to"] = to
        captured["subject"] = subject
        captured["html_content"] = html_content
        # Read staged files WHILE the temp dir still exists (inside the call).
        captured["file_names"] = [os.path.basename(f) for f in (files or [])]
        captured["file_bytes"] = [open(f, "rb").read() for f in (files or [])]

    email_mod = types.ModuleType("airflow.utils.email")
    email_mod.send_email = fake_send_email
    _inject_module(monkeypatch, "airflow.utils.email", email_mod)

    assert compat.airflow_email_available() is True
    compat.send_airflow_email(
        to=["a@x.io", "b@x.io"],
        subject="Subj",
        html_content="<b>hi</b>",
        attachments=(("allure-results.zip", b"PK\x03\x04payload"),),
    )
    assert captured["to"] == ["a@x.io", "b@x.io"]
    assert captured["subject"] == "Subj"
    assert captured["html_content"] == "<b>hi</b>"
    assert captured["file_names"] == ["allure-results.zip"]
    assert captured["file_bytes"] == [b"PK\x03\x04payload"]


def test_send_airflow_email_without_attachments_passes_none(monkeypatch):
    captured: dict = {}

    def fake_send_email(*, to, subject, html_content, files):
        captured["files"] = files

    email_mod = types.ModuleType("airflow.utils.email")
    email_mod.send_email = fake_send_email
    _inject_module(monkeypatch, "airflow.utils.email", email_mod)

    compat.send_airflow_email(to=["a@x.io"], subject="S", html_content="h")
    assert captured["files"] is None


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


def test_send_airflow_email_attachment_name_cannot_escape_staging_dir(monkeypatch):
    # A hostile attachment name must be flattened to its basename inside the
    # throwaway staging dir — never a path that writes outside it.
    captured: dict = {}

    def fake_send_email(*, to, subject, html_content, files):
        captured["names"] = [os.path.basename(f) for f in (files or [])]
        captured["parents"] = [os.path.dirname(f) for f in (files or [])]

    email_mod = types.ModuleType("airflow.utils.email")
    email_mod.send_email = fake_send_email
    _inject_module(monkeypatch, "airflow.utils.email", email_mod)

    compat.send_airflow_email(
        to=["a@x.io"],
        subject="S",
        html_content="h",
        attachments=(
            ("../../../../tmp/evil.zip", b"x"),
            ("", b"y"),  # empty name -> the safe fallback
        ),
    )
    assert captured["names"] == ["evil.zip", "attachment.bin"]
    assert all("apx-mail-" in p for p in captured["parents"])  # staged, not elsewhere


def test_send_airflow_email_silences_only_the_connection_deprecation(
    monkeypatch, recwarn
):
    # Airflow's send_mime_email emits a get_connection_from_secrets DeprecationWarning
    # on EVERY send (their code, not ours) — it must not spam each task log.
    import warnings as w

    def fake_send_email(*, to, subject, html_content, files):
        w.warn(
            "Using Connection.get_connection_from_secrets from `airflow.models` "
            "is deprecated. Please use `get` on Connection from sdk",
            DeprecationWarning,
            stacklevel=2,
        )

    email_mod = types.ModuleType("airflow.utils.email")
    email_mod.send_email = fake_send_email
    _inject_module(monkeypatch, "airflow.utils.email", email_mod)

    compat.send_airflow_email(to=["a@x.io"], subject="S", html_content="h")
    leaked = [r for r in recwarn if "get_connection_from_secrets" in str(r.message)]
    assert leaked == []


def test_send_airflow_email_lets_other_deprecations_through(monkeypatch, recwarn):
    # The filter is surgical: any OTHER deprecation must still surface.
    import warnings as w

    def fake_send_email(*, to, subject, html_content, files):
        w.warn("something unrelated is deprecated", DeprecationWarning, stacklevel=2)

    email_mod = types.ModuleType("airflow.utils.email")
    email_mod.send_email = fake_send_email
    _inject_module(monkeypatch, "airflow.utils.email", email_mod)

    compat.send_airflow_email(to=["a@x.io"], subject="S", html_content="h")
    assert any("something unrelated" in str(r.message) for r in recwarn)


_NO_ROW = object()


def _inject_xcom(monkeypatch, *, value, capture=None):
    """Fake the DB-backed XComModel + create_session (the server-side read path).

    ``value`` is what ``deserialize_value`` yields (the run summary); ``_NO_ROW`` means
    the query found no XCom row (``session.scalar`` returns ``None``).
    """

    class FakeXComModel:
        @staticmethod
        def get_many(*, run_id, key, task_ids, dag_ids, map_indexes, limit=None):
            if capture is not None:
                capture.update(
                    run_id=run_id,
                    key=key,
                    task_ids=task_ids,
                    dag_ids=dag_ids,
                    map_indexes=map_indexes,
                    limit=limit,
                )
            return "STMT"

        @staticmethod
        def deserialize_value(row):
            return row  # the row already IS the summary in this fake

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def scalar(self, stmt):
            assert stmt == "STMT"
            return None if value is _NO_ROW else value

    xcom_mod = types.ModuleType("airflow.models.xcom")
    xcom_mod.XComModel = FakeXComModel
    _inject_module(monkeypatch, "airflow.models.xcom", xcom_mod)
    session_mod = types.ModuleType("airflow.utils.session")
    session_mod.create_session = lambda: FakeSession()
    _inject_module(monkeypatch, "airflow.utils.session", session_mod)


def test_get_run_coverage_reads_xcom_fraction(monkeypatch):
    # Operator >=0.6 pushes a coverage fraction (0-1) into the return_value XCom summary;
    # the reader pulls it via the DB-backed XComModel (NOT the Task-SDK XCom.get_one).
    calls: dict = {}
    _inject_xcom(monkeypatch, value={"total": 10, "coverage": 0.8525}, capture=calls)
    assert compat.get_run_coverage("dag", "run1", "task", 3) == 0.8525
    assert calls == {
        "run_id": "run1",
        "key": "return_value",
        "task_ids": "task",
        "dag_ids": "dag",
        "map_indexes": 3,
        "limit": 1,
    }


@pytest.mark.parametrize(
    "value",
    [
        {"total": 5},  # coverage key absent (no --cov run)
        {"coverage": None},  # requested but unavailable
        {"coverage": 1.5},  # over 1.0 -> reject
        {"coverage": -0.1},  # negative -> reject
        {"coverage": True},  # bool is not a coverage number
        {"coverage": False},  # bool (even 0-valued) is not a coverage number
        {"coverage": "0.9"},  # wrong type
        "not-a-dict",  # unexpected XCom value
        _NO_ROW,  # no XCom row at all (task with no return_value)
    ],
)
def test_get_run_coverage_none_on_missing_or_bad_value(monkeypatch, value):
    _inject_xcom(monkeypatch, value=value)
    assert compat.get_run_coverage("dag", "r", "t", -1) is None


@pytest.mark.parametrize("frac", [0.0, 0.5, 1.0])
def test_get_run_coverage_accepts_inclusive_bounds(monkeypatch, frac):
    # The whole [0, 1] range is valid coverage, boundaries included (0% and 100%).
    _inject_xcom(monkeypatch, value={"coverage": frac})
    assert compat.get_run_coverage("dag", "r", "t", -1) == frac


def test_get_run_coverage_none_when_xcom_read_raises(monkeypatch):
    # Any DB/session error while reading XCom degrades to None (bench hidden), never
    # propagates into the detail request. Force create_session() to raise.
    import types as _t

    xcom_mod = _t.ModuleType("airflow.models.xcom")

    class _Boom:
        @staticmethod
        def get_many(**_):
            return "STMT"

        @staticmethod
        def deserialize_value(row):  # pragma: no cover - never reached
            return row

    xcom_mod.XComModel = _Boom
    _inject_module(monkeypatch, "airflow.models.xcom", xcom_mod)
    session_mod = _t.ModuleType("airflow.utils.session")

    def _raise():
        raise RuntimeError("database is locked")

    session_mod.create_session = _raise
    _inject_module(monkeypatch, "airflow.utils.session", session_mod)
    assert compat.get_run_coverage("dag", "r", "t", -1) is None


@pytest.mark.skipif(_airflow_present(), reason="exercises the Airflow-absent path")
def test_get_run_coverage_none_without_airflow():
    assert compat.get_run_coverage("dag", "r", "t", -1) is None
