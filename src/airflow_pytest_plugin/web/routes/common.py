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

"""Shared route dependencies and helpers (no FastAPI import at module load)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...flaky_core import FAIL_OUTCOMES  # re-exported: shared with /api/compare
from ...models import ReportRef
from ...sources import ReportSource

#: An authorizer: ``(dag_id, user) -> bool``. ``user`` is ``None`` standalone.
Authorizer = Callable[[str, Any], bool]

__all__ = ["FAIL_OUTCOMES", "Authorizer", "RouteDeps", "ok", "ref_from_token"]


@dataclass(frozen=True)
class RouteDeps:
    """Runtime collaborators every route closes over.

    Built once in ``create_app``, passed to each module's ``build_router``.
    """

    src: ReportSource
    read_auth: Authorizer
    delete_auth: Authorizer
    user_dep: Callable[[], Any]


def ref_from_token(token: str) -> ReportRef:
    """Parse an attacker-controlled report token, or raise HTTP ``400``."""
    from fastapi import HTTPException

    try:
        return ReportRef.from_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# -- OpenAPI helpers: example payloads + status codes for Swagger -------------
# Routes return a raw JSONResponse, so FastAPI infers no schema (Swagger would
# show an empty "string"). These attach a concrete 200 example and document each
# route's error codes.


def ok(example: Any, description: str = "Successful response") -> dict[int | str, Any]:
    """A 200 response documented with a concrete JSON ``example``."""
    return {
        200: {
            "description": description,
            "content": {"application/json": {"example": example}},
        }
    }


def _err(detail: str) -> dict[str, Any]:
    return {"content": {"application/json": {"example": {"detail": detail}}}}


#: Reusable error responses (FastAPI's HTTPException body is ``{"detail": "..."}``).
ERR_400: dict[int | str, Any] = {
    400: {"description": "Malformed report token.", **_err("malformed report token")}
}
ERR_403: dict[int | str, Any] = {
    403: {
        "description": "Forbidden — not authorized for this dag (RBAC).",
        **_err("not authorized"),
    }
}
ERR_404: dict[int | str, Any] = {
    404: {"description": "Not found.", **_err("report not found")}
}
