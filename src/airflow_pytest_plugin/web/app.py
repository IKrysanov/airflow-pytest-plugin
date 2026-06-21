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

"""The FastAPI application.

Maps HTTP routes onto an injected :class:`ReportSource` and serves the viewer --
no filesystem, layout, or XML knowledge of its own (Dependency Inversion).
Mountable under any prefix; the page derives its API base from the URL at
runtime, so no base path is baked in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import ReportRef
from ..sources import FileSystemReportSource, ReportSource
from .templates import index_html

if TYPE_CHECKING:
    from fastapi import FastAPI

# The nav glyph (a flask / colba). Airflow's external_views ``icon`` is a URL,
# so the app serves the SVG itself -- one per theme, since a URL-loaded SVG
# can't inherit ``currentColor``. Blue tuned for contrast on each nav bg.
_ICON_LIGHT = "#1e40af"
_ICON_DARK = "#93b8f4"


def _flask_svg(stroke: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 3h6M10 3v6.3a2 2 0 0 1-.4 1.2L4.5 18a2 2 0 0 0 1.6 3.2h11.8'
        'a2 2 0 0 0 1.6-3.2l-5.1-7.5a2 2 0 0 1-.4-1.2V3"/>'
        '<path d="M7.2 15h9.6"/></svg>'
    )


def create_app(source: ReportSource | None = None) -> FastAPI:
    """Build the FastAPI app for ``source`` (defaults to the filesystem source).

    Imported lazily so the rest of the package -- in particular the
    producer-side parser on a worker -- never needs FastAPI installed.
    """
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    src = source or FileSystemReportSource()
    app = FastAPI(
        title="Airflow Pytest Reports",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/api/reports")
    def list_reports(
        dag_id: str | None = None,
        run_id: str | None = None,
    ) -> JSONResponse:
        summaries = src.list_summaries(dag_id=dag_id, run_id=run_id)
        return JSONResponse({"reports": [s.to_dict() for s in summaries]})

    @app.get("/api/reports/{report_id}")
    def get_report(report_id: str) -> JSONResponse:
        try:
            ref = ReportRef.from_token(report_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        detail = src.get_detail(ref)
        if detail is None:
            raise HTTPException(status_code=404, detail="report not found")
        return JSONResponse(detail.to_dict())

    @app.get("/icon.svg")
    def icon() -> Response:
        return Response(_flask_svg(_ICON_LIGHT), media_type="image/svg+xml")

    @app.get("/icon-dark.svg")
    def icon_dark() -> Response:
        return Response(_flask_svg(_ICON_DARK), media_type="image/svg+xml")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(index_html())

    return app
