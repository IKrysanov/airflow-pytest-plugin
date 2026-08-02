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

"""In-process assistant counters for the Prometheus endpoint.

Deliberately cheap: a handful of integers behind one lock, updated once per request. The
counters carry no report content, no question text and no user identity -- only what an
operator needs to see spend and health. They are per API-server process and reset on
restart, which is what a Prometheus counter is expected to do.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

#: Terminal states of one assistant request, used as the ``outcome`` label.
OUTCOMES = ("answered", "empty_scope", "busy", "error", "stopped")

#: Where the report evidence came from, used as the ``mode`` label.
MODES = ("direct", "local")


@dataclass
class AssistantMetricsSnapshot:
    """One consistent read of the counters."""

    requests: dict[tuple[str, str], int]
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    provider_seconds: float
    local_reduce_calls: int
    reports_considered: int
    context_limited: int
    output_limited: int
    in_flight: int


class AssistantMetrics:
    """Thread-safe counters shared by every assistant request in this process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str], int] = {}
        self._input_tokens = 0
        self._output_tokens = 0
        self._cached_input_tokens = 0
        self._provider_seconds = 0.0
        self._local_reduce_calls = 0
        self._reports_considered = 0
        self._context_limited = 0
        self._output_limited = 0
        self._in_flight = 0

    def request_started(self) -> None:
        """Count one request that acquired a model slot."""
        with self._lock:
            self._in_flight += 1

    def request_finished(
        self,
        *,
        mode: str,
        outcome: str,
        reports_considered: int = 0,
        provider_seconds: float = 0.0,
        local_reduce_calls: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        context_limited: bool = False,
        output_limited: bool = False,
    ) -> None:
        """Record one terminal outcome and everything it cost."""
        key = (mode if mode in MODES else "direct", outcome)
        with self._lock:
            self._requests[key] = self._requests.get(key, 0) + 1
            self._reports_considered += max(0, reports_considered)
            self._provider_seconds += max(0.0, provider_seconds)
            self._local_reduce_calls += max(0, local_reduce_calls)
            self._input_tokens += max(0, input_tokens)
            self._output_tokens += max(0, output_tokens)
            self._cached_input_tokens += max(0, cached_input_tokens)
            self._context_limited += 1 if context_limited else 0
            self._output_limited += 1 if output_limited else 0
            if self._in_flight > 0:
                self._in_flight -= 1

    def rejected(self, *, mode: str) -> None:
        """Count one request refused before it held a slot."""
        with self._lock:
            key = (mode if mode in MODES else "direct", "busy")
            self._requests[key] = self._requests.get(key, 0) + 1

    def snapshot(self) -> AssistantMetricsSnapshot:
        """Return the counters as one consistent immutable read."""
        with self._lock:
            return AssistantMetricsSnapshot(
                requests=dict(self._requests),
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                cached_input_tokens=self._cached_input_tokens,
                provider_seconds=self._provider_seconds,
                local_reduce_calls=self._local_reduce_calls,
                reports_considered=self._reports_considered,
                context_limited=self._context_limited,
                output_limited=self._output_limited,
                in_flight=self._in_flight,
            )


__all__ = ["MODES", "OUTCOMES", "AssistantMetrics", "AssistantMetricsSnapshot"]
