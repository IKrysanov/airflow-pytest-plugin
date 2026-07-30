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

import hashlib
import logging
from collections.abc import Callable, Mapping, Sequence
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
from .help_templates import help_html
from .routes.common import MAX_BULK_DELETE_BODY_BYTES, Authorizer, RouteDeps
from .templates import index_html

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    from starlette.types import ASGIApp, Message, Receive, Scope, Send
else:
    # Viewer/icon routes annotate these; with future annotations FastAPI resolves
    # them from module globals, so they must live here. FastAPI is optional.
    try:
        from fastapi import Request
        from fastapi.responses import HTMLResponse, JSONResponse, Response
    except ModuleNotFoundError:  # pragma: no cover - only without fastapi installed
        HTMLResponse = JSONResponse = Request = Response = None

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

_HELP_HEADERS = {
    # Unlike the viewer, the guide is one constant string with no report data in it, so it
    # can be cached -- but it still must never be served stale after an upgrade. no-cache
    # keeps the copy and forces revalidation on every open; the ETag then turns a repeat
    # visit into an empty 304 instead of ~95 KB, and changes to the page change the tag.
    "Cache-Control": "no-cache, must-revalidate",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'self'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
}


_HELP_ETAG_CACHE: str | None = None


class _RequestBodyLimitMiddleware:
    """Reject one sensitive endpoint before FastAPI buffers and decodes a huge body."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        path: str,
        method: str,
        max_bytes: int,
    ) -> None:
        self.app = app
        self.path = path
        self.method = method
        self.max_bytes = max_bytes

    async def _reject(self, send: Send) -> None:
        body = (
            f'{{"detail":"request body too large (max {self.max_bytes} bytes)"}}'
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        request_path = scope.get("path", "")
        root_path = scope.get("root_path", "")
        if root_path and request_path.startswith(root_path):
            request_path = request_path[len(root_path) :] or "/"
        if (
            scope["type"] != "http"
            or request_path != self.path
            or scope.get("method") != self.method
        ):
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                declared_size = int(value)
            except ValueError:
                break
            if declared_size > self.max_bytes:
                await self._reject(send)
                return
            break

        # Content-Length is optional (for example with chunked transfer encoding), so
        # enforce the same limit while reading. Buffering at most one bounded request here
        # also keeps the oversized value away from FastAPI/Pydantic's JSON parser.
        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                await self._reject(send)
                return
            if not message.get("more_body", False):
                break

        iterator = iter(messages)

        async def replay() -> Message:
            return next(iterator, {"type": "http.disconnect"})

        await self.app(scope, replay, send)


def _safe_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Strip caller-controlled values from FastAPI's otherwise reflective 422 body."""
    unsafe = {"ctx", "input", "url"}
    return [
        {key: value for key, value in error.items() if key not in unsafe}
        for error in errors
    ]


def _help_etag() -> str:
    """Strong validator for the guide: the build's own content hash."""
    global _HELP_ETAG_CACHE
    if _HELP_ETAG_CACHE is None:
        digest = hashlib.sha256(help_html().encode("utf-8")).hexdigest()[:32]
        _HELP_ETAG_CACHE = f'"{digest}"'
    return _HELP_ETAG_CACHE


def _etag_matches(header: str | None, etag: str) -> bool:
    """Whether an ``If-None-Match`` header covers ``etag`` (RFC 9110 weak comparison)."""
    if not header:
        return False
    for candidate in header.split(","):
        token = candidate.strip()
        if token == "*":
            return True
        if token.startswith("W/"):
            token = token[2:]
        if token == etag:
            return True
    return False


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
    from fastapi.exceptions import RequestValidationError

    from .routes import compare, failures, flaky, monitoring, reports

    src = source or FileSystemReportSource()

    # Said once, at startup, where an operator will see it: the hardened XML parser is an
    # extra, so the default install reads archived reports with the stdlib one. That is fine
    # when every report comes from your own suites and a real problem when it does not --
    # and ``/api/health`` reporting ``secure_xml: false`` is only found by someone already
    # looking.
    if not getattr(src, "secure_xml", True):
        _log.warning(
            "Parsing archived JUnit XML with the stdlib parser: defusedxml is not "
            "installed, so a hostile or corrupt report can exhaust API-server memory via "
            "entity expansion. Install the extra: pip install "
            "'airflow-pytest-plugin[secure-xml]'."
        )

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
    app.add_middleware(
        _RequestBodyLimitMiddleware,
        path="/api/reports/delete",
        method="POST",
        max_bytes=MAX_BULK_DELETE_BODY_BYTES,
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # Pydantic includes the original invalid value under ``input``. That is useful
        # during development but lets an attacker reflect a large or sensitive string in
        # the response. Location, error type and message are enough for API clients.
        del request
        return JSONResponse(
            status_code=422,
            content={"detail": _safe_validation_errors(exc.errors())},
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

    # Both spellings are served directly. Left to Starlette's redirect_slashes, a
    # bookmarked or hand-typed "/help/" costs an extra 307 round trip on every open --
    # and shows up as two document requests for one visit.
    @app.get("/help", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/help/", response_class=HTMLResponse, include_in_schema=False)
    def help_page(request: Request) -> Response:
        """Serve the static user guide without reading report data."""
        etag = _help_etag()
        headers = {**_HELP_HEADERS, "ETag": etag}
        if _etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
        return HTMLResponse(help_html(), headers=headers)

    return app
