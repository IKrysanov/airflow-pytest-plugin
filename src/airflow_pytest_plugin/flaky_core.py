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

"""Pure flaky-scoring logic, shared by the ``/api/flaky`` route and the alerting layer.

No web/Airflow/FastAPI imports -- outcome sequences in, stats out -- so the reader route and
producer-side email alerts score flakiness identically without the producer pulling in the
web layer.
"""

from __future__ import annotations

from typing import Any

#: Outcomes that count as failures for flakiness detection.
FAIL_OUTCOMES = ("failed", "error")


def flip_rate(seq: list[str]) -> float:
    """Fraction of consecutive runs that switched between pass and fail/error."""
    if len(seq) < 2:
        return 0.0
    flips = sum(
        1
        for a, b in zip(seq, seq[1:], strict=False)
        if (a in FAIL_OUTCOMES) != (b in FAIL_OUTCOMES)
    )
    return flips / (len(seq) - 1)


def trend(seq: list[str]) -> str:
    """Flipping more lately? ``up`` (worse) / ``down`` (calmer) / ``flat``."""
    if len(seq) < 4:
        return "flat"
    mid = len(seq) // 2
    older, newer = flip_rate(seq[:mid]), flip_rate(seq[mid:])
    if newer > older + 1e-9:
        return "up"
    if newer < older - 1e-9:
        return "down"
    return "flat"


def is_flaky(seq: list[str], *, min_score: float = 0.0) -> bool:
    """True if the window holds BOTH a pass and a fail/error AND the flip rate clears
    ``min_score`` -- so a lone blip in an otherwise steady history is not flaky."""
    if not any(o in FAIL_OUTCOMES for o in seq):
        return False
    if not any(o == "passed" for o in seq):
        return False
    return flip_rate(seq) >= min_score


def flaky_stats(
    seq: list[str],
    *,
    min_score: float = 0.0,
    quarantine_score: float = 1.0,
    strip: int = 10,
) -> dict[str, Any] | None:
    """Flakiness stats for one test's outcomes (oldest→newest), or ``None`` if stable.

    Flaky only if the window holds both a pass and a fail/error AND ``score`` clears
    ``min_score`` -- filtering out a lone blip in a long history (near-zero flip rate).
    ``score`` is the flip rate (0–1), normalised by run count so it's comparable across
    histories; ``trend`` compares the recent half to the older half; ``quarantined``
    marks scores at/above ``quarantine_score``; ``recent`` is the last ``strip``
    outcomes for the UI strip.
    """
    fails = sum(1 for o in seq if o in FAIL_OUTCOMES)
    if not fails or not any(o == "passed" for o in seq):
        return None
    score = round(flip_rate(seq), 3)
    if score < min_score:  # too steady to be flaky
        return None
    flips = sum(
        1
        for a, b in zip(seq, seq[1:], strict=False)
        if (a in FAIL_OUTCOMES) != (b in FAIL_OUTCOMES)
    )
    return {
        "runs": len(seq),
        "fails": fails,
        "flips": flips,
        "score": score,
        "trend": trend(seq),
        "quarantined": score >= quarantine_score,
        "recent": seq[-strip:],
    }
