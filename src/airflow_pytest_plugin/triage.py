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

"""The AI-triage contract, shared by producer and reader.

`pytest-triage <https://pypi.org/project/pytest-triage/>`_ writes a JSON report of every
failed test, optionally enriched with an LLM verdict (**regression / flaky / env /
test_bug**) plus a one-line hypothesis and a suggested fix. The producer asks pytest for
that report inside the run's archive directory (``ArchivingResultParser(triage=True)``)
and :func:`distill_report` reduces it to two pieces, split by *who reads them*:

* a tiny **roll-up** (model, duration, category counts, and why the pass fell short) that
  travels in ``meta.json``, the file every tree scan parses -- so it must stay small;
* the **per-test verdicts**, written beside it in ``verdicts.json`` and opened only by views
  that read a single run: the detail, and the heatmap over its window.

Only the *judgement* is carried over -- never the tracebacks, stdout or logs pytest-triage
also captures. Those already live in ``junit.xml``, and the raw report is owner-only on
disk (it may hold residual secrets even after redaction), so duplicating them into a
world-readable sidecar would be both wasteful and a leak. A failure that was reported but
never judged is still kept: its exception type and rerun selector are what ``triage=True``
buys on its own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import islice
from typing import Any

from .models import TriageSummary, Verdict

#: Bumped when the ``meta.json`` ``triage`` block changes incompatibly.
TRIAGE_SCHEMA_VERSION = 1

#: The frozen verdict vocabulary of pytest-triage. Anything else reads as ``unknown``
#: rather than reaching the UI as an unstyled, untranslated string.
CATEGORIES = ("regression", "flaky", "env", "test_bug", "unknown")
#: Verdict confidence, likewise frozen; an unrecognised value becomes ``None``.
CONFIDENCES = ("low", "medium", "high")

#: Most per-test verdicts kept in one run's meta. A triaged run has at most
#: ``--ai-budget`` verdicts (10 by default), so this only bites on a pathological report --
#: and it keeps the sidecar bounded, since every scan of the tree parses it in full.
MAX_VERDICTS = 200
#: Clip for a model-written sentence (hypothesis / suggested fix).
MAX_TEXT = 1000
#: Clip for short identifiers: model name, exception type, rerun selector.
MAX_LABEL = 200

#: Prefixes pytest-triage stamps on the hypothesis of a verdict it could NOT produce (see
#: its ``wrappers`` module, where they are documented as stable for exactly this purpose).
#: All four arrive as ``category="unknown"``, but none of them is a judgement about the
#: test: they say the triage PASS failed -- the budget ran out, the key was rejected, the
#: provider timed out, or the breaker stopped paying a provider that kept failing. Shown as
#: verdicts they would be actively misleading, filling the card with "Unclear" chips while
#: hiding the fact that nothing was analysed. They are dropped, and the reason is reported
#: once at run level instead.
INCOMPLETE_REASONS = (
    "triage provider error",
    "triage timed out",
    "triage budget exhausted",
    "triage stopped:",
)


def canonical_node_key(node_id: str) -> str:
    """Map any pytest node id to the reader's dotted ``classname::name`` form.

    The two sides name the same test differently: pytest-triage reports the native
    slash form (``tests/test_x.py::TestThings::test_y``), while the JUnit parser
    reconstructs a dotted one from ``classname``/``name``
    (``tests.test_x.TestThings::test_y``). Both collapse onto the dotted key here, so a
    verdict can be joined to its case. Already-dotted ids pass through unchanged, which
    makes this idempotent and safe to apply on both the write and the read side.

    Only the *path* segment is rewritten: a parametrised id keeps its ``[...]`` suffix
    verbatim, so ``test_y[a/b]`` survives the round trip.
    """
    parts = [p for p in str(node_id).split("::") if p]
    if len(parts) < 2:
        return parts[0] if parts else ""
    head = parts[0]
    if head.endswith(".py"):
        head = head[:-3]
    head = head.replace("\\", "/").replace("/", ".").strip(".")
    dotted = ".".join([p for p in (head, *parts[1:-1]) if p])
    return f"{dotted}::{parts[-1]}" if dotted else parts[-1]


@dataclass(frozen=True)
class TriageArchive:
    """What the producer writes, split by which file it belongs in.

    ``rollup`` goes into ``meta.json`` and must stay small -- the reader parses that file
    for every run on every tree scan. ``verdicts`` goes into its own ``verdicts.json``
    beside it, opened only when a single run's detail is requested.
    """

    rollup: dict[str, Any] = field(default_factory=dict)
    verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def verdicts_document(self) -> dict[str, Any]:
        """The ``verdicts.json`` body: versioned, so the reader can reject a future shape."""
        return {"schema_version": TRIAGE_SCHEMA_VERSION, "verdicts": self.verdicts}


def distill_report(raw: Any) -> TriageArchive | None:
    """Reduce a pytest-triage JSON report to the two pieces the archive stores.

    Returns ``None`` when ``raw`` isn't a report object at all. A report with no verdicts
    still yields an archive: "triage ran and judged nothing" is itself worth showing, and it
    tells the reader the run was triaged rather than simply old.

    Args:
        raw: The parsed ``triage.json`` pytest-triage wrote (schema version 1).

    Returns:
        A :class:`TriageArchive` whose ``verdicts`` are keyed by :func:`canonical_node_key`.
        Every string is clipped and every number coerced -- the report is written by
        arbitrary test code on the worker.
    """
    if not isinstance(raw, dict):
        return None
    failures = raw.get("failures")
    if not isinstance(failures, list):
        failures = []

    verdicts: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    incomplete: str | None = None
    for failure in failures:
        if len(verdicts) >= MAX_VERDICTS:
            break
        if not isinstance(failure, dict):
            continue
        entry = _verdict_entry(failure)
        if entry is None:
            continue
        reason = _incomplete_reason(entry)
        if reason is not None:
            # The first reason is the cause; the ones after it are its consequence (a
            # provider that errors twice trips the breaker, and every later failure then
            # reports the breaker).
            incomplete = incomplete or reason
            continue
        key = canonical_node_key(failure.get("nodeid") or "")
        # First verdict wins: a rerun-in-place suite can report the same node twice, and
        # the earlier entry is the one whose failure the report's counts describe.
        if not key or key in verdicts:
            continue
        verdicts[key] = entry
        if entry["category"] is not None:  # unjudged failures are shown, never counted
            counts[entry["category"]] = counts.get(entry["category"], 0) + 1

    return TriageArchive(
        rollup={
            "schema_version": TRIAGE_SCHEMA_VERSION,
            "model": label(raw.get("ai_model")),
            "duration": _finite(raw.get("triage_duration")),
            "total_failures": _count(raw.get("total_failures"), len(failures)),
            "total_verdicts": _count(raw.get("total_verdicts"), len(verdicts)),
            # Kept for a reader that wants the mix without opening verdicts.json (and for
            # anyone running `jq` over the archive). The detail view recomputes it from the
            # verdicts it actually attached -- see `triage_view`.
            "counts": counts,
            # Why the pass produced fewer verdicts than there were failures, when the cause
            # was the triage pass itself rather than the budget being deliberately small.
            "incomplete": incomplete,
        },
        verdicts=verdicts,
    )


def triage_rollup(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """The run's stored ``triage`` roll-up, or ``None`` when it wasn't triaged.

    Defensive in the same way as the alert/coverage readers: ``meta.json`` is written on the
    worker by the tested project's own process, so nothing in it is trusted twice.
    """
    if not isinstance(meta, dict):
        return None
    block = meta.get("triage")
    return block if isinstance(block, dict) else None


def verdicts_from_document(document: Any, fallback: Any = None) -> dict[str, Verdict]:
    """Read ``verdicts.json`` into view models, keyed by :func:`canonical_node_key`.

    ``fallback`` accepts the roll-up block for archives written before the verdicts moved
    into their own file: those carry the mapping inline. Anything unreadable in either
    place yields ``{}`` -- a run then shows its roll-up with no per-test analysis, rather
    than failing to open.
    """
    raw = document.get("verdicts") if isinstance(document, dict) else None
    if not isinstance(raw, dict):
        raw = fallback.get("verdicts") if isinstance(fallback, dict) else None
    if not isinstance(raw, dict):
        return {}
    verdicts: dict[str, Verdict] = {}
    # islice, not a slice of .items(): a corrupt file could hold a million entries, and
    # copying them all just to drop most is the cost this cap exists to avoid.
    for key, value in islice(raw.items(), MAX_VERDICTS):
        entry = _verdict_entry({"verdict": value}, extras=value)
        if entry is not None:
            verdicts[canonical_node_key(key)] = Verdict(**entry)
    return verdicts


def triage_view(
    rollup: dict[str, Any] | None, attached: list[Verdict]
) -> TriageSummary | None:
    """The run-level summary the UI renders, given the verdicts actually shown.

    ``counts`` and ``total_verdicts`` are recomputed from ``attached`` rather than trusted
    from the roll-up, so the card can never advertise a category the table cannot show. The
    two legitimately differ: a verdict whose node id has no matching JUnit case (a collection
    error names the file, not a test) is counted by pytest-triage but is not clickable here.
    ``total_failures`` stays as recorded -- that is what pytest-triage saw, and the gap
    between the two is exactly the "N of M judged" the UI reports.
    """
    if rollup is None:
        return None
    counts: dict[str, int] = {}
    for verdict in attached:
        if verdict.category is not None:
            counts[verdict.category] = counts.get(verdict.category, 0) + 1
    judged = sum(counts.values())
    return TriageSummary(
        model=label(rollup.get("model")),
        duration=_finite(rollup.get("duration")),
        total_failures=_count(rollup.get("total_failures"), len(attached)),
        # Only judgements count: a report-only run shows every failure and judges none.
        total_verdicts=judged,
        counts={name: counts[name] for name in CATEGORIES if name in counts},
        incomplete=_text(rollup.get("incomplete")),
    )


# -- internals -----------------------------------------------------------------------


def _verdict_entry(
    failure: dict[str, Any], *, extras: Any = None
) -> dict[str, Any] | None:
    """One sanitized failure record, or ``None`` when it carries nothing worth showing.

    A verdict is optional. Report-only runs (``triage=True``, no provider) have none at
    all, and a budgeted run has none past its cap -- but pytest-triage still reports the
    exception type and the exact argument that reruns just that test, which is the whole
    value of the report on its own. An entry with neither a verdict nor either of those
    facts would render as an empty panel, so it is dropped.

    ``extras`` supplies ``exc_type``/``selector`` when re-reading our own stored entry
    (where they sit beside the verdict fields); on the producer side they come from the
    surrounding pytest-triage failure record instead.
    """
    side = extras if isinstance(extras, dict) else failure
    verdict = failure.get("verdict")
    if not isinstance(verdict, dict):
        verdict = {}
    # "Judged" is decided by the presence of a category, not by the object being non-empty:
    # on the read side the stored entry IS a populated dict whose `category` is explicitly
    # null, and truthiness there would silently promote an unjudged failure to "unknown".
    judged = verdict.get("category") is not None
    category = str(verdict.get("category") or "").strip().lower()
    confidence = str(verdict.get("confidence") or "").strip().lower()
    entry = {
        # None = "not judged", which is different from the model answering "unknown".
        "category": (category if category in CATEGORIES else "unknown")
        if judged
        else None,
        "hypothesis": _text(verdict.get("hypothesis")),
        "confidence": confidence if confidence in CONFIDENCES else None,
        "suggested_fix": _text(verdict.get("suggested_fix")),
        "exc_type": label(side.get("exc_type")),
        # The ready-to-run selector for THIS test, so the UI can offer a rerun command
        # without reconstructing the slash form from a dotted node id.
        "selector": label(_first_selector(side)),
    }
    if entry["category"] is None and not entry["exc_type"] and not entry["selector"]:
        return None
    return entry


def _incomplete_reason(entry: dict[str, Any]) -> str | None:
    """The reason this "verdict" is not a judgement, or ``None`` when it is one.

    Matched by PREFIX: a provider error appends its (already redacted and capped) cause,
    which is the single most useful thing a misconfigured run can tell you -- "triage
    provider error: 401 invalid x-api-key" beats any number of Unclear chips.
    """
    if entry["category"] != "unknown":
        return None
    hypothesis = entry["hypothesis"] or ""
    return hypothesis if hypothesis.startswith(INCOMPLETE_REASONS) else None


def _first_selector(failure: dict[str, Any]) -> Any:
    """The failure's own rerun selector: its ``pytest_args``, else its raw ``nodeid``."""
    args = failure.get("pytest_args")
    if isinstance(args, list) and args and isinstance(args[0], str):
        return args[0]
    return failure.get("selector") or failure.get("nodeid")


#: Everything a model writes ends up in a JSON response, a log line and the DOM. Control
#: characters have no business in any of them: a NUL truncates C-based consumers, and an
#: ESC sequence repaints the terminal of whoever tails the logs. Newlines and tabs survive
#: as spaces (see :func:`_readable`); the rest are dropped.
_CONTROL = dict.fromkeys([*range(0x20), 0x7F], " ")


def _readable(value: str) -> str:
    """``value`` with control characters neutralised to spaces."""
    return value.translate(_CONTROL)


def _text(value: Any) -> str | None:
    """A model-written sentence, trimmed, de-controlled and clipped; ``None`` when empty."""
    if not isinstance(value, str):
        return None
    cleaned = _readable(value).strip()[:MAX_TEXT]
    return cleaned or None


def label(value: Any) -> str | None:
    """A short identifier, single-lined and clipped; ``None`` when empty or not a string.

    Public because the reader normalises the same fields on the summary path, and the two
    must agree: a model name shown in the list is the one shown in the run.
    """
    if not isinstance(value, str):
        return None
    cleaned = " ".join(_readable(value).split())[:MAX_LABEL]
    return cleaned or None


def _count(value: Any, default: int) -> int:
    """A non-negative count, or ``default`` for anything unparseable."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if isinstance(value, float) and not math.isfinite(value):
        return default
    return max(0, int(value))


def _finite(value: Any) -> float | None:
    """A finite, non-negative duration in seconds, else ``None``.

    Non-finite floats aren't JSON-spec and would 500 the response serializer.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None
