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

"""The FastAPI application: maps HTTP routes onto an injected ``ReportSource``."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..compat import (
    airflow_auth_available,
    get_user_dependency,
    is_authorized_to_read,
    is_authorized_to_trigger,
)
from ..models import ReportRef
from ..sources import FileSystemReportSource, ReportSource
from .templates import index_html

if TYPE_CHECKING:
    from fastapi import FastAPI

#: An authorizer: ``(dag_id, user) -> bool``. ``user`` is ``None`` standalone.
Authorizer = Callable[[str, Any], bool]

#: Upper bound on failed cases returned by /api/failures, to bound the payload.
_FAILURES_CAP = 5000


def _no_user() -> None:
    """Standalone-mode user dependency: there is no Airflow user."""
    return None


# Airflow renders external_views ``icon`` as a plain ``<img>`` (no currentColor),
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
    available, else allow-all. ``user_dependency`` overrides current-user resolution.
    """
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    src = source or FileSystemReportSource()

    def _allow_all(dag_id: str, user: Any) -> bool:
        return True

    auth_on = airflow_auth_available()
    read_auth: Authorizer = read_authorizer or (
        is_authorized_to_read if auth_on else _allow_all
    )
    delete_auth: Authorizer = authorizer or (
        is_authorized_to_trigger if auth_on else _allow_all
    )
    # Depends keeps the user out of the annotations, so future-annotations can't
    # break dependency resolution.
    user_dep = user_dependency or (get_user_dependency() if auth_on else _no_user)

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
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        summaries = src.list_summaries(dag_id=dag_id, run_id=run_id)
        visible = [s for s in summaries if read_auth(s.ref.dag_id, user)]
        return JSONResponse({"reports": [s.to_dict() for s in visible]})

    @app.get("/api/reports/{report_id}")
    def get_report(
        report_id: str,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        try:
            ref = ReportRef.from_token(report_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not read_auth(ref.dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read this report"
            )
        detail = src.get_detail(ref)
        if detail is None:
            raise HTTPException(status_code=404, detail="report not found")
        return JSONResponse(detail.to_dict())

    @app.delete("/api/reports/{report_id}")
    def delete_report(
        report_id: str,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        try:
            ref = ReportRef.from_token(report_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not delete_auth(ref.dag_id, user):
            raise HTTPException(
                status_code=403,
                detail="deleting a report requires permission to trigger its DAG",
            )
        if not src.delete(ref):
            raise HTTPException(status_code=404, detail="report not found")
        return JSONResponse({"deleted": True})

    @app.get("/api/reports/{report_id}/allure.zip")
    def allure_zip(
        report_id: str,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> Response:
        try:
            ref = ReportRef.from_token(report_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not read_auth(ref.dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read this report"
            )
        data = src.allure_archive(ref)
        if data is None:
            raise HTTPException(status_code=404, detail="no Allure results")
        return Response(
            data,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="allure-results.zip"'
            },
        )

    @app.get("/api/failures")
    def failures(
        dag_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Every failed/errored case across the visible runs (newest run first).

        Filters mirror the list view; the client paginates the flat result. Capped
        to keep the payload bounded -- ``capped`` flags truncation.
        """
        task_q = (task_id or "").lower()
        items: list[dict[str, Any]] = []
        capped = False
        for s in src.list_summaries(dag_id=dag_id, run_id=run_id):
            if task_q and task_q not in s.ref.task_id.lower():
                continue
            if (s.failed + s.errors) <= 0 or not read_auth(s.ref.dag_id, user):
                continue
            detail = src.get_detail(s.ref)
            if detail is None:
                continue
            for c in detail.cases:
                if c.outcome not in ("failed", "error"):
                    continue
                items.append(
                    {
                        "id": s.ref.token,
                        "dag_id": s.ref.dag_id,
                        "task_id": s.ref.task_id,
                        "run_id": s.ref.run_id,
                        "created_at": s.created_at,
                        "node_id": c.node_id,
                        "outcome": c.outcome,
                    }
                )
            if len(items) >= _FAILURES_CAP:
                capped = True
                break
        return JSONResponse(
            {
                "failures": items[:_FAILURES_CAP],
                "total": len(items[:_FAILURES_CAP]),
                "capped": capped,
            }
        )

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
