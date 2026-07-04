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

"""Airflow version compatibility shim -- the only module that imports Airflow.

Imports are lazy (inside functions) so loading the plugin never pulls in the
Task SDK. 2.x/3.x differences live here, degrading gracefully when Airflow is
absent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

_log = logging.getLogger(__name__)


def get_current_context() -> dict[str, Any] | None:
    """Return the running task's Airflow context, or ``None`` if unavailable."""
    # Try 3.x (Task SDK) first, then 2.x.
    try:
        from airflow.sdk import get_current_context as _gcc3

        return dict(_gcc3())
    except Exception:
        pass
    try:
        from airflow.operators.python import get_current_context as _gcc2

        return dict(_gcc2())
    except Exception:
        return None


def get_airflow_plugin_base() -> type[Any]:
    """Return ``airflow.plugins_manager.AirflowPlugin`` (raises if Airflow absent)."""
    from airflow.plugins_manager import AirflowPlugin

    return cast("type[Any]", AirflowPlugin)


def get_conf_value(section: str, key: str) -> str | None:
    """Read a value from ``airflow.cfg`` / env, or ``None`` if unset/absent."""
    try:
        from airflow.configuration import conf

        # Annotate rather than cast: works whether conf.get is typed str | None or Any.
        value: str | None = conf.get(section, key, fallback=None)
        return value
    except Exception:
        return None


def airflow_email_available() -> bool:
    """True if Airflow's ``send_email`` is importable (i.e. a mail transport exists)."""
    try:
        from airflow.utils.email import send_email  # noqa: F401

        return True
    except Exception:
        return False


def send_airflow_email(
    *,
    to: list[str],
    subject: str,
    html_content: str,
    attachments: Sequence[tuple[str, bytes]] = (),
) -> None:
    """Send through Airflow's configured SMTP (``airflow.utils.email.send_email``).

    The one place that touches Airflow's mail API. ``send_email`` wants file
    PATHS, so byte attachments are staged in a throwaway dir here. If the call's
    name or signature shifts between Airflow versions, this is the only fix site.
    """
    import os
    import tempfile

    from airflow.utils.email import send_email

    with tempfile.TemporaryDirectory(prefix="apx-mail-") as tmp:
        files = []
        for name, payload in attachments:
            path = os.path.join(tmp, os.path.basename(name) or "attachment.bin")
            with open(path, "wb") as handle:
                handle.write(payload)
            files.append(path)
        send_email(
            to=to,
            subject=subject,
            html_content=html_content,
            files=files or None,
        )


def airflow_auth_available() -> bool:
    """True if Airflow 3's FastAPI auth (current-user dependency) is importable."""
    try:
        from airflow.api_fastapi.core_api.security import get_user  # noqa: F401

        return True
    except Exception:
        return False


def get_user_dependency() -> Any:
    """Return Airflow's ``get_user`` FastAPI dependency (call only when auth available)."""
    from airflow.api_fastapi.core_api.security import get_user

    return get_user


def is_authorized_to_trigger(dag_id: str, user: Any) -> bool:
    """True if ``user`` may trigger ``dag_id`` (gates report deletion)."""
    return _is_authorized_dag("POST", dag_id, user)


def is_authorized_to_read(dag_id: str, user: Any) -> bool:
    """True if ``user`` may read ``dag_id`` (gates listing / detail)."""
    return _is_authorized_dag("GET", dag_id, user)


def _is_authorized_dag(method: str, dag_id: str, user: Any) -> bool:
    """Ask the Airflow auth manager about a DAG-run action. Fails **closed**."""
    try:
        from airflow.api_fastapi.auth.managers.models.resource_details import (
            DagAccessEntity,
            DagDetails,
        )

        manager = _resolve_auth_manager()
        return bool(
            manager.is_authorized_dag(
                method=method,
                access_entity=DagAccessEntity.RUN,
                details=DagDetails(id=dag_id),
                user=user,
            )
        )
    except Exception:
        _log.warning(
            "DAG authorization check (%s) failed; denying", method, exc_info=True
        )
        return False


def _resolve_auth_manager() -> Any:
    """Return the active Airflow auth manager, trying known import locations."""
    for module_name in (
        "airflow.api_fastapi.app",
        "airflow.www.extensions.init_auth_manager",
    ):
        try:
            module = __import__(module_name, fromlist=["get_auth_manager"])
            return module.get_auth_manager()
        except Exception:
            continue
    raise RuntimeError("could not resolve the Airflow auth manager")
