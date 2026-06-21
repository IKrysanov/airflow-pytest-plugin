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

"""Resolve the report root -- the same way on producer and reader.

Precedence, highest first:
1. an explicit argument in code (handled by the caller);
2. ``AIRFLOW_PYTEST_REPORTS_ROOT`` (env);
3. ``[pytest_reports] reports_root`` (Airflow config);
4. the default ``/opt/airflow/pytest-reports``.
"""

from __future__ import annotations

import os

from .compat import get_conf_value

ENV_VAR = "AIRFLOW_PYTEST_REPORTS_ROOT"
CONF_SECTION = "pytest_reports"
CONF_KEY = "reports_root"
DEFAULT_ROOT = "/opt/airflow/pytest-reports"


def get_reports_root() -> str:
    """Resolve the report root directory (absolute path)."""
    env = os.environ.get(ENV_VAR)
    if env and env.strip():
        return os.path.abspath(env.strip())

    conf = get_conf_value(CONF_SECTION, CONF_KEY)
    if conf and conf.strip():
        return os.path.abspath(conf.strip())

    return os.path.abspath(DEFAULT_ROOT)
