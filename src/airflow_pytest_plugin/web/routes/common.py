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

"""Shared dependencies and helpers for the route modules (no FastAPI at import)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...models import ReportRef
from ...sources import ReportSource

#: An authorizer: ``(dag_id, user) -> bool``. ``user`` is ``None`` standalone.
Authorizer = Callable[[str, Any], bool]

#: Outcomes that count as a failure, shared by /api/compare and /api/flaky.
FAIL_OUTCOMES = ("failed", "error")


@dataclass(frozen=True)
class RouteDeps:
    """The runtime collaborators every route closes over.

    Built once in ``create_app`` and passed to each module's ``build_router``.
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
