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

"""Plugin entry point: mounts the FastAPI app and a nav link.

Also home to :func:`run_tracking_url` — the viewer's address is defined here
(``URL_PREFIX``), so composing a deep link to a run belongs here too.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .compat import get_airflow_plugin_base
from .config import ENABLE_ENV_VAR, get_base_url, is_plugin_enabled

if TYPE_CHECKING:
    from .models import ReportRef

_log = logging.getLogger(__name__)

URL_PREFIX = "/pytest-reports"
APP_NAME = "Pytest Reports"
NAV_NAME = "Pytest"
#: The Airflow SPA route rendering this plugin's page (``external_views[].url_route``).
PLUGIN_ROUTE = "pytest-reports"


def run_tracking_url(ref: ReportRef) -> str | None:
    """Deep link to ``ref`` in the Pytest Reports viewer, or ``None`` without a base URL.

    Points at the **Airflow plugin page** (``/plugin/<route>``) — the viewer inside the
    Airflow chrome (sidebar and all) — not the bare mounted app, which renders without
    any navigation. The query rides the parent URL; the embedded viewer reads it from
    there. Deliberately the SHORT human-readable form (``?dag=…&run=…&task=…&try=…``),
    not the opaque ``?report=<token>`` one: the ~200-char token gets wrapped/truncated
    by log viewers, breaking the link with an HTTP 400.
    """
    base = get_base_url()
    if not base:
        return None
    params = [
        ("dag", ref.dag_id),
        ("run", ref.run_id),
        ("task", ref.task_id),
        ("try", str(ref.try_number)),
    ]
    if ref.map_index != -1:
        params.append(("map", str(ref.map_index)))
    query = "&".join(f"{k}={quote(v, safe='')}" for k, v in params)
    return f"{base}/plugin/{PLUGIN_ROUTE}?{query}"


def _build_fastapi_apps() -> list[dict[str, Any]]:
    """The ``fastapi_apps`` registration, or ``[]`` if FastAPI is unavailable."""
    try:
        from .sources import FileSystemReportSource
        from .web import create_app

        app = create_app(FileSystemReportSource())
    except Exception:  # FastAPI missing or app build failed
        _log.warning(
            "Pytest Reports UI not registered (FastAPI unavailable or app build "
            "failed); the producer-side parser is unaffected.",
            exc_info=True,
        )
        return []
    return [{"app": app, "url_prefix": URL_PREFIX, "name": APP_NAME}]


def _build_external_views() -> list[dict[str, Any]]:
    """Nav link embedding the mounted app in an iframe (Airflow 3.1+).

    ``href`` MUST end in a trailing slash so it hits the mounted app's index;
    the bare prefix falls through to the Airflow SPA (duplicated nav, 404).
    """
    return [
        {
            "name": NAV_NAME,
            "href": f"{URL_PREFIX}/",
            "url_route": PLUGIN_ROUTE,
            "destination": "nav",
            "icon": f"{URL_PREFIX}/icon.svg",
            "icon_dark_mode": f"{URL_PREFIX}/icon-dark.svg",
        }
    ]


# mypy sees a plain ``object`` base; the real Airflow base is resolved at runtime.
if TYPE_CHECKING:
    _Base = object
else:
    try:
        _Base = get_airflow_plugin_base()
    except Exception:  # Airflow absent -- keep import working for unit tests
        _Base = object


#: Kill switch: when AIRFLOW_PYTEST_PLUGIN_ENABLE is falsey, register nothing
#: (no app, no nav link) so the UI/API stay unavailable.
_ENABLED = is_plugin_enabled()
if not _ENABLED:
    _log.info("Pytest Reports reader disabled via %s; not registering.", ENABLE_ENV_VAR)


class PytestReportsPlugin(_Base):
    """Exposes the Pytest Reports UI to Airflow (unless disabled via env var)."""

    name = "pytest_reports"
    fastapi_apps = _build_fastapi_apps() if _ENABLED else []
    external_views = _build_external_views() if _ENABLED else []
