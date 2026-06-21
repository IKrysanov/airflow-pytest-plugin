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

Every Airflow import is lazy (inside a function), never at module load, so the
producer parser can import the plugin on a worker without dragging in the Task
SDK. Airflow 2.x/3.x differences are resolved here, 3.x first, degrading
gracefully when Airflow is absent (unit tests, the dev server).
"""

from __future__ import annotations

from typing import Any, cast


def get_current_context() -> dict[str, Any] | None:
    """Return the running task's Airflow context, or ``None`` if unavailable.

    Tries the Airflow 3 Task SDK first, then the Airflow 2 location. ``None``
    means no active context (the parser used off-task); callers fall back.
    """
    # Airflow 3.x (Task SDK).
    try:
        from airflow.sdk import get_current_context as _gcc3

        return dict(_gcc3())
    except Exception:
        pass
    # Airflow 2.x.
    try:
        from airflow.operators.python import get_current_context as _gcc2

        return dict(_gcc2())
    except Exception:
        return None


def get_airflow_plugin_base() -> type[Any]:
    """Return ``airflow.plugins_manager.AirflowPlugin`` (same path on 2.x/3.x).

    Raises ``ImportError`` if Airflow is absent; the plugin module guards it.
    """
    from airflow.plugins_manager import AirflowPlugin

    return cast("type[Any]", AirflowPlugin)


def get_conf_value(section: str, key: str) -> str | None:
    """Read a value from ``airflow.cfg`` / env, or ``None`` if unset/absent."""
    try:
        from airflow.configuration import conf

        # Annotate rather than cast: clean whether ``conf.get`` is typed as
        # ``str | None`` (Airflow installed) or ``Any`` (not installed).
        value: str | None = conf.get(section, key, fallback=None)
        return value
    except Exception:
        return None
