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

"""Airflow compatibility surface (the only package that touches Airflow)."""

from __future__ import annotations

from .airflow import (
    airflow_auth_available,
    get_airflow_plugin_base,
    get_conf_value,
    get_current_context,
    get_run_coverage,
    get_user_dependency,
    is_authorized_to_read,
    is_authorized_to_trigger,
)

__all__ = [
    "get_current_context",
    "get_airflow_plugin_base",
    "get_conf_value",
    "get_run_coverage",
    "airflow_auth_available",
    "get_user_dependency",
    "is_authorized_to_read",
    "is_authorized_to_trigger",
]
