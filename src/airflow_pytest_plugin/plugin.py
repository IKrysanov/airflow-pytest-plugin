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

"""The Airflow plugin entry point.

Mounts the FastAPI app on Airflow 3's API server (``fastapi_apps``) and adds a
nav link that embeds it in an iframe (``external_views``). Both are best-effort:
missing FastAPI leaves the producer parser unaffected.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .compat import get_airflow_plugin_base

_log = logging.getLogger(__name__)

#: Mount prefix on the API server. The viewer derives its API base from the URL,
#: so this can change without touching the page.
URL_PREFIX = "/pytest-reports"
#: Metadata name for the mounted app (not shown in the nav).
APP_NAME = "Pytest Reports"
#: The label shown in the Airflow left nav.
NAV_NAME = "Pytest"


def _build_fastapi_apps() -> list[dict[str, Any]]:
    """Construct the ``fastapi_apps`` registration, or ``[]`` if unavailable."""
    try:
        from .sources import FileSystemReportSource
        from .web import create_app

        app = create_app(FileSystemReportSource())
    except Exception:  # FastAPI missing, or any construction error
        _log.warning(
            "Pytest Reports UI not registered (FastAPI unavailable or app build "
            "failed); the producer-side parser is unaffected.",
            exc_info=True,
        )
        return []
    return [{"app": app, "url_prefix": URL_PREFIX, "name": APP_NAME}]


def _build_external_views() -> list[dict[str, Any]]:
    """A nav link that embeds the mounted app in an iframe (Airflow 3.1+).

    ``url_route`` makes Airflow render the view inline (an iframe whose ``src``
    is ``href``); ``href`` MUST carry a trailing slash so it hits the mounted
    app's index (``/pytest-reports/``) directly. Without it the bare prefix
    falls through to the Airflow SPA, which renders its own chrome inside the
    iframe (duplicated nav) and a 404 for the unknown client route.

    ``icon`` / ``icon_dark_mode`` are URLs to SVGs the app itself serves (the
    flask glyph), so the nav shows a colba icon that contrasts in both themes.
    """
    return [
        {
            "name": NAV_NAME,
            "href": f"{URL_PREFIX}/",
            "url_route": "pytest-reports",
            "destination": "nav",
            "icon": f"{URL_PREFIX}/icon.svg",
            "icon_dark_mode": f"{URL_PREFIX}/icon-dark.svg",
        }
    ]


# mypy checks the plugin against a plain ``object`` base (the dynamic Airflow
# base is resolved only at runtime); this keeps the class definition type-clean
# whether or not Airflow is installed in the checking environment.
if TYPE_CHECKING:
    _Base = object
else:
    try:
        _Base = get_airflow_plugin_base()
    except Exception:  # Airflow not installed -- allow import for unit tests
        _Base = object


class PytestReportsPlugin(_Base):
    """Exposes the Pytest Reports UI to Airflow."""

    name = "pytest_reports"
    fastapi_apps = _build_fastapi_apps()
    external_views = _build_external_views()
