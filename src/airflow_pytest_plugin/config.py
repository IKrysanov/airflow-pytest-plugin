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

"""Resolve the report root (env, then Airflow config, then default)."""

from __future__ import annotations

import os

from .compat import get_conf_value

ENV_VAR = "AIRFLOW_PYTEST_REPORTS_ROOT"
CONF_SECTION = "pytest_reports"
CONF_KEY = "reports_root"
DEFAULT_ROOT = "/opt/airflow/pytest-reports"

#: Toggles whether the reader plugin (UI + API) registers with Airflow. Default on.
ENABLE_ENV_VAR = "AIRFLOW_PYTEST_PLUGIN_ENABLE"
_FALSEY = frozenset({"0", "false", "no", "off", "n", "f"})


def is_plugin_enabled() -> bool:
    """Whether the reader plugin should register with Airflow.

    Reads ``AIRFLOW_PYTEST_PLUGIN_ENABLE`` -- ``True`` (the default when unset/empty)
    registers the UI + API; a falsey value (``0``/``false``/``no``/``off``) disables
    it. Only gates the reader; the producer-side parser is unaffected.
    """
    raw = os.environ.get(ENABLE_ENV_VAR)
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in _FALSEY


#: How long (seconds) the filesystem source may reuse a directory scan. A short
#: window lets the several summary-driven endpoints on one page load (list + flaky +
#: unique-tests, plus filter typing) share one tree walk instead of rescanning each.
SCAN_TTL_ENV_VAR = "AIRFLOW_PYTEST_SCAN_CACHE_TTL"
DEFAULT_SCAN_TTL = 2.0


def get_scan_cache_ttl() -> float:
    """Resolve the directory-scan cache TTL in seconds (``0`` disables caching).

    Reads ``AIRFLOW_PYTEST_SCAN_CACHE_TTL``; falls back to ``DEFAULT_SCAN_TTL``.
    A malformed or negative value falls back to the default.
    """
    raw = os.environ.get(SCAN_TTL_ENV_VAR)
    if raw is None or not raw.strip():
        return DEFAULT_SCAN_TTL
    try:
        ttl = float(raw.strip())
    except ValueError:
        return DEFAULT_SCAN_TTL
    return ttl if ttl >= 0 else DEFAULT_SCAN_TTL


def get_reports_root() -> str:
    """Resolve the report root directory (absolute path)."""
    env = os.environ.get(ENV_VAR)
    if env and env.strip():
        return os.path.abspath(env.strip())

    conf = get_conf_value(CONF_SECTION, CONF_KEY)
    if conf and conf.strip():
        return os.path.abspath(conf.strip())

    return os.path.abspath(DEFAULT_ROOT)
