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

"""Single source of truth for the package version (read from package metadata)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_DIST_NAME = "airflow-pytest-plugin"


def _resolve_version() -> str:
    try:
        return version(_DIST_NAME)
    except PackageNotFoundError:  # running from an uninstalled source tree
        return "0.0.0+unknown"


__version__ = _resolve_version()
