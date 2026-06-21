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

"""Integration tests for the authz wiring against a real Airflow (skipped if absent)."""

from __future__ import annotations

import pytest

from airflow_pytest_plugin.compat import airflow as compat


def _airflow_present() -> bool:
    try:
        import airflow  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _airflow_present(), reason="integration: requires Airflow installed"
)


def test_auth_available_and_user_dependency_are_the_real_ones():
    # The current-user dependency must be Airflow's own get_user, unchanged.
    from airflow.api_fastapi.core_api.security import get_user

    assert compat.airflow_auth_available() is True
    assert compat.get_user_dependency() is get_user


def test_dag_access_symbols_match_the_installed_airflow():
    # Guards against API drift in the symbols compat imports for _is_authorized_dag.
    from airflow.api_fastapi.auth.managers.models.resource_details import (
        DagAccessEntity,
        DagDetails,
    )

    assert hasattr(DagAccessEntity, "RUN")
    assert DagDetails(id="some_dag").id == "some_dag"


def _real_simple_auth_manager():
    """A real SimpleAuthManager + admin/viewer users, or skip if unavailable."""
    try:
        from airflow.api_fastapi.auth.managers.simple.simple_auth_manager import (
            SimpleAuthManager,
        )
        from airflow.api_fastapi.auth.managers.simple.user import (
            SimpleAuthManagerUser,
        )

        manager = SimpleAuthManager()
        admin = SimpleAuthManagerUser(username="admin", role="admin")
        viewer = SimpleAuthManagerUser(username="viewer", role="viewer")
    except Exception as exc:  # pragma: no cover - depends on the Airflow build
        pytest.skip(f"real SimpleAuthManager unavailable here: {exc!r}")
    return manager, admin, viewer


def test_compat_drives_real_auth_manager_call_signature(monkeypatch):
    # Route compat through a real auth manager; our wrapper must return its verdict verbatim.
    from airflow.api_fastapi.auth.managers.models.resource_details import (
        DagAccessEntity,
        DagDetails,
    )

    manager, admin, _viewer = _real_simple_auth_manager()
    baseline = manager.is_authorized_dag(
        method="GET",
        access_entity=DagAccessEntity.RUN,
        details=DagDetails(id="d"),
        user=admin,
    )
    assert isinstance(baseline, bool)

    monkeypatch.setattr(compat, "_resolve_auth_manager", lambda: manager)
    assert compat.is_authorized_to_read("d", admin) == baseline


def test_real_rbac_admin_and_viewer_semantics(monkeypatch):
    # Real RBAC: admin may read+trigger; read-only viewer may read but not trigger (delete).
    manager, admin, viewer = _real_simple_auth_manager()
    monkeypatch.setattr(compat, "_resolve_auth_manager", lambda: manager)

    assert compat.is_authorized_to_read("d", admin) is True
    assert compat.is_authorized_to_trigger("d", admin) is True
    assert compat.is_authorized_to_read("d", viewer) is True
    assert compat.is_authorized_to_trigger("d", viewer) is False


def test_fails_closed_when_manager_unavailable_even_with_airflow(monkeypatch):
    # With real Airflow present but no resolvable manager, deny (fail closed).
    def _boom():
        raise RuntimeError("no app context")

    monkeypatch.setattr(compat, "_resolve_auth_manager", _boom)
    assert compat.is_authorized_to_read("d", object()) is False
    assert compat.is_authorized_to_trigger("d", object()) is False
