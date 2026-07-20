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

"""The FastAPI application: wires the route modules onto an injected ``ReportSource``."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..compat import (
    airflow_auth_available,
    airflow_available,
    get_user_dependency,
    is_authorized_to_read,
    is_authorized_to_trigger,
)
from ..sources import FileSystemReportSource, ReportSource
from ..version import __version__
from .routes.common import Authorizer, RouteDeps
from .templates import index_html

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, Response
else:
    # Viewer/icon routes annotate these; with future annotations FastAPI resolves
    # them from module globals, so they must live here. FastAPI is optional.
    try:
        from fastapi.responses import HTMLResponse, Response
    except ModuleNotFoundError:  # pragma: no cover - only without fastapi installed
        HTMLResponse = Response = None

#: Tag descriptions shown as Swagger UI section headers.
_OPENAPI_TAGS = [
    {"name": "monitoring", "description": "Liveness of the reader."},
    {
        "name": "reports",
        "description": "Browse archived runs, their per-test detail and history, "
        "and the catalogue of unique tests.",
    },
    {
        "name": "failures",
        "description": "Failed and errored cases across the visible runs.",
    },
    {"name": "compare", "description": "Diff one run against another, test by test."},
    {
        "name": "flaky",
        "description": "Tests that both pass and fail across recent runs.",
    },
]

_API_DESCRIPTION = (
    "JSON API behind the Pytest Reports viewer. Every read is gated by Airflow's "
    "DAG permissions and deletes need permission to trigger the DAG; tokens identify "
    "a run (dag·run·task·try). The viewer itself and its icons are served outside "
    "this schema."
)


def _no_user() -> None:
    """Standalone-mode user dependency: no Airflow user."""
    return None


# Airflow renders external_view ``icon`` as a plain ``<img>`` (no currentColor),
# so bake the colour into the SVG -- one per theme.
_ICON_LIGHT = "#52525b"
_ICON_DARK = "#a1a1aa"


def _flask_svg(stroke: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 3h6M10 3v6.3a2 2 0 0 1-.4 1.2L4.5 18a2 2 0 0 0 1.6 3.2h11.8'
        'a2 2 0 0 0 1.6-3.2l-5.1-7.5a2 2 0 0 1-.4-1.2V3"/>'
        '<path d="M7.2 15h9.6"/></svg>'
    )


def create_app(
    source: ReportSource | None = None,
    authorizer: Authorizer | None = None,
    read_authorizer: Authorizer | None = None,
    user_dependency: Callable[[], Any] | None = None,
) -> FastAPI:
    """Build the FastAPI app for ``source`` (defaults to the filesystem source).

    ``read_authorizer`` gates which reports a user may see/open, ``authorizer``
    who may delete; both default to Airflow DAG permissions when its auth is
    available, else allow-all. ``user_dependency`` overrides current-user lookup.
    """
    from fastapi import FastAPI

    from .routes import compare, failures, flaky, monitoring, reports

    src = source or FileSystemReportSource()

    def _allow_all(dag_id: str, user: Any) -> bool:
        return True

    def _deny_all(dag_id: str, user: Any) -> bool:
        return False

    auth_on = airflow_auth_available()
    # Without Airflow's auth there is no user to authorize, so the fallback depends on WHY
    # it is missing. No Airflow at all = the standalone dev server, where allow-all is the
    # point. Airflow present but its auth API not importable = we are inside a real
    # deployment whose RBAC we cannot consult -- serving every team's runs to everyone
    # would be the worst possible reading of "auth unavailable", so deny instead and say so.
    _fallback: Authorizer = _allow_all
    if not auth_on and airflow_available():
        _log.error(
            "Airflow is installed but its auth API could not be imported: refusing all "
            "report access. The plugin cannot verify DAG permissions, so it fails closed "
            "rather than exposing every DAG's runs. Check the Airflow version."
        )
        _fallback = _deny_all
    read_auth: Authorizer = read_authorizer or (
        is_authorized_to_read if auth_on else _fallback
    )
    delete_auth: Authorizer = authorizer or (
        is_authorized_to_trigger if auth_on else _fallback
    )
    # Depends keeps the user out of the annotations, so future-annotations can't
    # break dependency resolution.
    user_dep = user_dependency or (get_user_dependency() if auth_on else _no_user)
    deps = RouteDeps(
        src=src, read_auth=read_auth, delete_auth=delete_auth, user_dep=user_dep
    )

    app = FastAPI(
        title="Airflow Pytest Reports",
        version=__version__,
        summary="Browse archived pytest results in the Airflow 3 UI.",
        description=_API_DESCRIPTION,
        openapi_tags=_OPENAPI_TAGS,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    for module in (monitoring, reports, failures, compare, flaky):
        app.include_router(module.build_router(deps))

    # Viewer and icons are UI assets, not part of the documented JSON API.
    @app.get("/icon.svg", include_in_schema=False)
    def icon() -> Response:
        return Response(_flask_svg(_ICON_LIGHT), media_type="image/svg+xml")

    @app.get("/icon-dark.svg", include_in_schema=False)
    def icon_dark() -> Response:
        return Response(_flask_svg(_ICON_DARK), media_type="image/svg+xml")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> HTMLResponse:
        # The whole SPA (incl. inline JS) lives in this HTML, so it must never be
        # served stale -- else a browser/Airflow cache runs old JS after an upgrade.
        # no-store guarantees every load fetches the current build.
        return HTMLResponse(
            index_html(), headers={"Cache-Control": "no-store, must-revalidate"}
        )

    return app
