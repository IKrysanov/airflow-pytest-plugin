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

"""Compare route — per-test diff between two runs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from .common import (
    ERR_400,
    ERR_403,
    ERR_404,
    FAIL_OUTCOMES,
    RouteDeps,
    ok,
    ref_from_token,
)

TAG = "compare"


def diff_outcomes(
    base: dict[str, dict[str, Any]], head: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Categorise a base→head per-test diff into the five change buckets + counts."""
    cats: dict[str, Any] = {
        "newly_failed": [],
        "fixed": [],
        "still_failing": [],
        "added": [],
        "removed": [],
    }
    for node in set(base) | set(head):
        b, h = base.get(node), head.get(node)
        if h is None and b is not None:
            cats["removed"].append({"node_id": node, "outcome": b["outcome"]})
        elif b is None and h is not None:
            cats["added"].append({"node_id": node, "outcome": h["outcome"]})
        elif b is not None and h is not None:
            bf, hf = b["outcome"] in FAIL_OUTCOMES, h["outcome"] in FAIL_OUTCOMES
            if bf or hf:
                item = {"node_id": node, "base": b["outcome"], "head": h["outcome"]}
                if not bf and hf:
                    cats["newly_failed"].append(item)
                elif bf and not hf:
                    cats["fixed"].append(item)
                else:
                    cats["still_failing"].append(item)
    for rows in cats.values():
        rows.sort(key=lambda x: x["node_id"])
    cats["counts"] = {k: len(v) for k, v in cats.items()}
    return cats


def build_router(deps: RouteDeps) -> APIRouter:
    """Routes tagged ``compare``."""
    router = APIRouter(tags=[TAG])
    src = deps.src
    read_auth = deps.read_auth
    user_dep = deps.user_dep

    @router.get(
        "/api/compare",
        summary="Compare two runs",
        responses={
            **ok(
                {
                    "newly_failed": [
                        {
                            "node_id": "tests/api.py::test_auth",
                            "base": "passed",
                            "head": "failed",
                        }
                    ],
                    "fixed": [],
                    "still_failing": [],
                    "added": [],
                    "removed": [
                        {"node_id": "tests/api.py::test_legacy", "outcome": "passed"}
                    ],
                    "counts": {
                        "newly_failed": 1,
                        "fixed": 0,
                        "still_failing": 0,
                        "added": 0,
                        "removed": 1,
                    },
                }
            ),
            **ERR_400,
            **ERR_403,
            **ERR_404,
        },
    )
    def compare(
        base: str,
        head: str,
        user: Any = Depends(user_dep),  # noqa: B008 - FastAPI dependency idiom
    ) -> JSONResponse:
        """Per-test diff between two runs given their ``base`` and ``head`` tokens.

        Buckets every test into ``newly_failed`` / ``fixed`` / ``still_failing`` /
        ``added`` / ``removed`` (with a ``counts`` summary). Both runs must be
        readable (``403``); ``400`` on a malformed token, ``404`` if either run has
        no per-test map.
        """
        base_ref = ref_from_token(base)
        head_ref = ref_from_token(head)
        if not read_auth(base_ref.dag_id, user) or not read_auth(head_ref.dag_id, user):
            raise HTTPException(
                status_code=403, detail="not authorized to read these reports"
            )
        base_t = src.test_outcomes(base_ref)
        head_t = src.test_outcomes(head_ref)
        if base_t is None or head_t is None:
            raise HTTPException(status_code=404, detail="report not found")
        return JSONResponse(diff_outcomes(base_t, head_t))

    return router
