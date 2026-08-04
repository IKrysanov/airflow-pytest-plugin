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

"""One structured audit record per assistant request.

The assistant sends report data — including tracebacks and captured output — to a third
party on behalf of an Airflow user. An operator has to be able to answer "who sent data
from which DAGs to which provider, and what did it cost" after the fact, which neither the
Prometheus counters (aggregated and deliberately impersonal) nor the browser-local chat can
do.

The record deliberately carries **no report content and no question text**: it names the
principal, the DAGs whose data left the server, the provider, the cost and the outcome. The
question is identified by a truncated digest so the same question can be correlated across
records without storing what was asked.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Mapping
from typing import Any

#: Its own logger so a deployment can route or silence audit separately from diagnostics.
LOGGER = logging.getLogger("airflow_pytest_plugin.assistant.audit")

AUDIT_LOG_ENV = "AIRFLOW_PYTEST_ASSISTANT_AUDIT_LOG"

_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_MAX_DAGS = 50

#: Attributes that identify *an account*, in order of preference. A display name is
#: deliberately absent: ``BaseUser.get_name()`` may be "First Last", two colleagues can
#: share one, and this string keys both the stored transcript and the token quota.
_PRINCIPAL_ATTRS = ("username", "user_id", "id")

#: Anything longer is truncated, so the identity stays readable in a log line.
_MAX_PRINCIPAL = 128

#: Returned when no account key could be found. Nothing is stored under it -- see
#: ``ChatHistoryStore.storable`` -- because a shared bucket would merge two people.
ANONYMOUS = "unidentified"


def audit_enabled() -> bool:
    """Whether to emit audit records. On unless explicitly switched off.

    An audit trail that must be turned on is not one an incident responder can rely on, and
    one record per question is negligible log volume.
    """
    raw = os.environ.get(AUDIT_LOG_ENV)
    return raw is None or raw.strip().lower() not in _FALSE_VALUES


def principal(user: Any) -> str:
    """Return a readable identity for the acting Airflow user.

    This is an *authorization-relevant* string: it selects whose chat history is read and
    whose daily token budget is charged. So it is taken only from attributes an auth
    manager guarantees to be unique, never from a display name.

    Unlike the browser-storage namespace it is deliberately *not* hashed: an audit trail
    naming ``8f4a55c1`` answers nothing.
    """
    if user is None:
        return "standalone"
    for attr in _PRINCIPAL_ATTRS:
        value = (
            user.get(attr) if isinstance(user, Mapping) else getattr(user, attr, None)
        )
        if value is not None and str(value).strip():
            return _bounded(str(value).strip())
    get_id = getattr(user, "get_id", None)
    if callable(get_id):
        try:
            value = get_id()
        except Exception:  # pragma: no cover - defensive: a foreign user object
            return ANONYMOUS
        if value is not None and str(value).strip():
            return _bounded(str(value).strip())
    return ANONYMOUS


def _bounded(value: str) -> str:
    """Cap the identity without letting a shared prefix merge two accounts."""
    if len(value) <= _MAX_PRINCIPAL:
        return value
    digest = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]
    return f"{value[: _MAX_PRINCIPAL - len(digest) - 1]}~{digest}"


def record(**fields: Any) -> None:
    """Emit one audit record as a single JSON object."""
    if not audit_enabled():
        return
    try:
        body = json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return
    LOGGER.info("assistant.audit %s", body)


def question_digest(question: str) -> str:
    """Return a short, stable digest identifying a question without storing it."""
    return hashlib.sha256(question.encode("utf-8", "replace")).hexdigest()[:16]


def dag_ids(evidence: Any) -> list[str]:
    """Return the sorted, bounded DAG ids whose report data left the server."""
    names = sorted({item.dag_id for item in evidence})
    return names[:_MAX_DAGS]


__all__ = [
    "ANONYMOUS",
    "AUDIT_LOG_ENV",
    "LOGGER",
    "audit_enabled",
    "dag_ids",
    "principal",
    "question_digest",
    "record",
]
