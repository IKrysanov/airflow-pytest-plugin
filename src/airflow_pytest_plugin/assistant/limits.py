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

"""Per-principal request rate and daily token budget.

The concurrency semaphore bounds how much memory one process spends at once; it does not
bound how much *money* one user spends over time. A loop calling ``/api/assistant/query``
respects the semaphore perfectly and still bills a provider on every iteration.

The **daily token budget** is the one that costs money, so it is kept in the plugin's own
table when one exists (see :mod:`airflow_pytest_plugin.db`): shared by every worker and
unaffected by a restart. Without that table it falls back to memory, which is a guard rail
rather than a budget -- with N workers a principal then gets up to N times the allowance.

The **request rate limit** stays in process on purpose. It exists to stop a runaway loop,
which any single worker will notice on its own, and a sliding window in SQL would cost a
write per question to bound something that is not billed.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Protocol


class RateStore(Protocol):
    """Where a principal's request count for one time window is kept."""

    @property
    def available(self) -> bool:
        """Whether this store can answer right now."""

    def spent(self, principal: str, window: int) -> int:
        """Return the requests already admitted for ``principal`` in ``window``."""

    def charge(self, principal: str, window: int) -> None:
        """Record one more admitted request in that window."""


class QuotaStore(Protocol):
    """Where a principal's daily token spend is kept."""

    @property
    def available(self) -> bool:
        """Whether this store can answer right now."""

    def spent(self, principal: str, day: int) -> int:
        """Return the tokens ``principal`` has spent on ``day``."""

    def charge(self, principal: str, day: int, tokens: int) -> None:
        """Add ``tokens`` to that principal's spend for ``day``."""


class _MemoryQuotaStore:
    """Fallback used when no database is configured or the tables are missing."""

    def __init__(self, max_principals: int) -> None:
        self._max = max_principals
        self._lock = threading.Lock()
        self._tokens: OrderedDict[tuple[str, int], int] = OrderedDict()

    @property
    def available(self) -> bool:
        return True

    def spent(self, principal: str, day: int) -> int:
        with self._lock:
            return self._tokens.get((principal, day), 0)

    def charge(self, principal: str, day: int, tokens: int) -> None:
        with self._lock:
            key = (principal, day)
            self._tokens[key] = self._tokens.get(key, 0) + tokens
            self._tokens.move_to_end(key)
            while len(self._tokens) > self._max:
                self._tokens.popitem(last=False)

    def __len__(self) -> int:
        return len(self._tokens)


@dataclass(frozen=True)
class LimitDecision:
    """Whether a principal may ask now, and when to try again if not."""

    allowed: bool
    reason: str = ""
    retry_after: int = 0


class UserLimits:
    """Sliding-window request limit and calendar-day token quota, per principal."""

    #: Principals tracked at once. Bounds memory on a large or hostile installation; the
    #: least recently seen principal is evicted, which at worst forgives an old allowance.
    MAX_PRINCIPALS = 4_096

    def __init__(
        self,
        *,
        rate_limit: int = 0,
        rate_window_seconds: float = 3_600.0,
        daily_token_quota: int = 0,
        store: QuotaStore | None = None,
        rate_store: RateStore | None = None,
    ) -> None:
        self._rate_limit = max(0, rate_limit)
        self._window = max(1.0, rate_window_seconds)
        self._quota = max(0, daily_token_quota)
        self._lock = threading.Lock()
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()
        self._memory = _MemoryQuotaStore(self.MAX_PRINCIPALS)
        self._store = store
        self._rate_store = rate_store
        #: Injectable for deterministic tests; production uses the real clocks.
        self.clock = time.monotonic
        #: Wall clock. The shared window index has to mean the same thing in every
        #: process, and monotonic clocks do not compare across processes.
        self.wall = time.time
        self.today = _utc_day

    @property
    def rate_limit(self) -> int:
        """Requests allowed per window, or ``0`` when unlimited."""
        return self._rate_limit

    @property
    def rate_window_seconds(self) -> float:
        """Length of the sliding window."""
        return self._window

    @property
    def daily_token_quota(self) -> int:
        """Provider tokens allowed per principal per UTC day, or ``0`` when unlimited."""
        return self._quota

    @property
    def enabled(self) -> bool:
        """Whether any limit is configured."""
        return bool(self._rate_limit or self._quota)

    @property
    def shared(self) -> bool:
        """Whether token spend is recorded somewhere every worker can see.

        False when no quota is set: nothing is counted then, anywhere, and answering "yes,
        shared" would tell an operator their budget is enforced fleet-wide when there is no
        budget at all.
        """
        return bool(self._quota) and self._store is not None and self._store.available

    @property
    def rate_shared(self) -> bool:
        """Whether the request limit is counted across every worker. See :attr:`shared`."""
        return (
            bool(self._rate_limit)
            and self._rate_store is not None
            and self._rate_store.available
        )

    @property
    def tracked(self) -> int:
        """How many principals currently hold state."""
        with self._lock:
            return max(len(self._requests), len(self._memory))

    def _quota_store(self) -> QuotaStore:
        # Re-checked per call: an operator can run the CLI while the server is up, and the
        # next question should start counting against the shared table.
        if self._store is not None and self._store.available:
            return self._store
        return self._memory

    def check(self, principal: str) -> LimitDecision:
        """Decide whether ``principal`` may spend one more request right now.

        Checked before the model runs and before the slot is taken, so a refused request
        costs nothing and cannot displace a paying one.
        """
        if not self.enabled:
            return LimitDecision(True)
        if self._quota:
            # Read outside the lock: the shared store does its own I/O, and holding a
            # process-wide lock across a database round trip would serialise every worker
            # thread behind it.
            if self._quota_store().spent(principal, self.today()) >= self._quota:
                return LimitDecision(
                    False,
                    "daily_token_quota",
                    retry_after=_seconds_until_utc_midnight(),
                )
        if self._rate_limit:
            # The in-process window first: it costs nothing, and a runaway loop is stopped
            # here rather than being allowed to spend a database round trip per attempt.
            local = self._local_rate(principal)
            if not local.allowed:
                return local
            shared = self._shared_rate(principal)
            if not shared.allowed:
                return shared
        return LimitDecision(True)

    def _local_rate(self, principal: str) -> LimitDecision:
        """Sliding window kept in this process."""
        now = self.clock()
        with self._lock:
            seen = self._requests.get(principal)
            if seen is None:
                seen = deque()
                self._requests[principal] = seen
            self._requests.move_to_end(principal)
            cutoff = now - self._window
            while seen and seen[0] <= cutoff:
                seen.popleft()
            if len(seen) >= self._rate_limit:
                retry = max(1, int(seen[0] + self._window - now) + 1)
                return LimitDecision(False, "rate_limit", retry_after=retry)
            seen.append(now)
            self._evict()
        return LimitDecision(True)

    def _shared_rate(self, principal: str) -> LimitDecision:
        """Fixed window counted in the plugin's table, when there is one.

        Read then written, so a refused request never consumes budget -- the same rule the
        in-process window follows. Two workers can both read a value one below the limit
        and both admit, so the guarantee is "about N", not "exactly N"; that is the right
        trade for a guard rail that must never add a lock to the request path.
        """
        store = self._rate_store
        if store is None or not store.available:
            return LimitDecision(True)
        now = self.wall()
        window = int(now // self._window)
        if store.spent(principal, window) >= self._rate_limit:
            ends_at = (window + 1) * self._window
            return LimitDecision(
                False, "rate_limit", retry_after=max(1, int(ends_at - now))
            )
        store.charge(principal, window)
        return LimitDecision(True)

    def charge(self, principal: str, tokens: int) -> None:
        """Add provider-reported tokens to today's spend for ``principal``."""
        if not self._quota or tokens <= 0:
            return
        self._quota_store().charge(principal, self.today(), tokens)

    def spent_today(self, principal: str) -> int:
        """Return today's token spend, for status and tests."""
        return self._quota_store().spent(principal, self.today())

    def _evict(self) -> None:
        while len(self._requests) > self.MAX_PRINCIPALS:
            self._requests.popitem(last=False)


#: Bytes per token used when a provider reports no usage at all. Deliberately rough: it
#: only has to keep a configured budget draining, and under-counting is what would let an
#: unmetered endpoint spend without limit.
BYTES_PER_TOKEN = 4


def estimated_tokens(prompt_bytes: int, answer_bytes: int) -> int:
    """Approximate a request's token cost from the bytes that crossed the wire.

    Used only as a fallback. Some OpenAI-compatible gateways and self-hosted endpoints
    answer without a ``usage`` block; charging zero there would turn a configured spend cap
    into no cap, so an approximation is charged instead of nothing.
    """
    total = max(0, prompt_bytes) + max(0, answer_bytes)
    return max(1, total // BYTES_PER_TOKEN)


def _utc_day() -> int:
    return int(time.time() // 86_400)


def _seconds_until_utc_midnight() -> int:
    return max(1, 86_400 - int(time.time()) % 86_400)


__all__ = [
    "BYTES_PER_TOKEN",
    "LimitDecision",
    "QuotaStore",
    "UserLimits",
    "estimated_tokens",
]
