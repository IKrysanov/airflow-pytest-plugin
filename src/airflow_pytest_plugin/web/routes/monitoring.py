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

"""Monitoring routes — liveness, readiness, and build info of the reader."""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...compat import airflow_auth_available
from ...version import __version__
from .common import RouteDeps

TAG = "monitoring"
_DIST_NAME = "airflow-pytest-plugin"


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``monitoring``."""
    router = APIRouter(tags=[TAG])
    src = deps.src

    @router.get("/api/health", summary="Health & readiness")
    def health() -> JSONResponse:
        """Liveness + readiness of the reader. No parameters, no report reads, no auth.

        Fields:

        - ``status`` — ``"ok"`` whenever the app is serving (liveness).
        - ``ready`` / ``reports_root_exists`` — whether the report directory exists
          and is readable; ``ready`` is ``false`` when the reader can't see its store.
        - ``reports_root`` — the directory the producer writes to and the reader reads
          from (``null`` for a non-filesystem source).
        - ``auth`` — ``"airflow"`` when Airflow RBAC gates the data routes, else
          ``"open"`` (standalone / allow-all).
        - ``secure_xml`` — whether JUnit XML is parsed with the hardened ``defusedxml``
          parser (vs the stdlib fallback).

        Cheap by design — no directory scan — so it is safe for frequent probes.
        """
        root = getattr(src, "report_root", None)
        exists = bool(
            root is not None and os.path.isdir(root) and os.access(root, os.R_OK)
        )
        return JSONResponse(
            {
                "status": "ok",
                "ready": exists,
                "reports_root": root,
                "reports_root_exists": exists,
                "auth": "airflow" if airflow_auth_available() else "open",
                "secure_xml": getattr(src, "secure_xml", None),
            }
        )

    @router.get("/api/version", summary="Build info")
    def version() -> JSONResponse:
        """The plugin's distribution name and version (from package metadata)."""
        return JSONResponse({"name": _DIST_NAME, "version": __version__})

    return router
