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

"""Hierarchical local reduction of a complete chunked report tree."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Generator, Iterable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Any

from .common import ContextReducer, clip_utf8
from .redaction import redact_text

_MAX_REDUCTION_PASSES = 12
_CITATION = re.compile(r"\[R[1-9][0-9]*\]")

#: A partial this short that also cites nothing carries no usable facts. Measured against
#: real GGUF output: Qwen2.5-0.5B-Instruct answers a 9 KiB chunk with one to fifteen bytes
#: ("4", "1", "4 тестов падают") instead of summarizing it. That is indistinguishable from
#: a working reduction to the code that follows, so the whole request would quietly ask a
#: paid provider to reason from nothing. A partial that kept a citation is never counted:
#: the model demonstrably followed the labelling instruction, however terse it was.
_MIN_USEFUL_PARTIAL_BYTES = 32

#: A raw chunk states each case as one machine-written JSON line, so what a chunk contains
#: is known exactly rather than inferred. These read it back.
_CASE_LINE = re.compile(r"^CASE (\{.*\})$", re.M)
_RUN_LINE = re.compile(r"^RUN (\[R[1-9][0-9]*\]) (\{.*\})$", re.M)
#: The body is fenced line by line by the chunk producer, so it ends at the first line
#: that is not fenced -- which no amount of test output can forge.
_TRACEBACK_BLOCK = re.compile(
    r"^TRACEBACK (R[1-9][0-9]*:C[0-9]+)\n((?:\| .*\n?)*)",
    re.M,
)

#: Restored failures per chunk, and how much of one error message is kept. Enough to name
#: and group real failures; not so much that a chunk full of them becomes the whole budget.
_MAX_RESTORED_FAILURES = 40
_MAX_RESTORED_ERROR_CHARS = 200

#: Below this share of the chunk's failures being named in the model's own output, the
#: output is treated as a paraphrase and the failures are restored. Not zero: a model that
#: kept most of them made an editorial choice about the rest, which is what it is for.
_MIN_NAMED_SHARE = 0.5
_GROUP_HEADER = (
    "These are partial summaries of disjoint parts of one report tree. Merge them "
    "without answering the user. Preserve useful [R<n>] citations and cross-run trends."
)


@dataclass(frozen=True)
class ReducedEvidence:
    """Final bounded evidence plus whether a deterministic fallback dropped data."""

    text: str
    hard_truncated: bool
    source_truncated: bool
    passes: int
    chunks_processed: int
    budget_exhausted: bool = False
    reducer_calls: int = 0
    degenerate: bool = False
    """The local model produced too little text to carry any facts."""


def reduce_context_tree(
    *,
    question: str,
    chunks: Iterable[str],
    reducer: ContextReducer,
    max_bytes: int,
    input_bytes: int | None = None,
    budget_seconds: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ReducedEvidence:
    """Map every raw chunk, then reduce summaries until one provider prompt fits.

    The blocking form: identical work to :func:`reduce_context_tree_events`, with the
    progress reports thrown away. Kept because most callers -- and every test that only
    cares about the evidence -- have no use for them.
    """
    events = reduce_context_tree_events(
        question=question,
        chunks=chunks,
        reducer=reducer,
        max_bytes=max_bytes,
        input_bytes=input_bytes,
        budget_seconds=budget_seconds,
        clock=clock,
    )
    while True:
        try:
            next(events)
        except StopIteration as stop:
            result: ReducedEvidence = stop.value
            return result


def reduce_context_tree_events(
    *,
    question: str,
    chunks: Iterable[str],
    reducer: ContextReducer,
    max_bytes: int,
    input_bytes: int | None = None,
    budget_seconds: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    scope: Callable[[], AbstractContextManager[Any]] = nullcontext,
) -> Generator[dict[str, Any], None, ReducedEvidence]:
    """Map and merge as above, yielding one progress report per mapped chunk.

    Local mode streams nothing until the whole tree has been reduced, which at the default
    budget is up to two minutes of an unexplained spinner. Each yielded dict says how far
    the map phase has got and how much of the budget is left, so the wait has a visible
    end.

    ``budget_seconds`` bounds the wall clock spent in the local model. A synchronous
    llama.cpp call cannot be cancelled and the runtime holds its only slot for the whole
    request, so an unbounded tree would otherwise let one question monopolize the
    assistant for as long as it takes to map every chunk. When the budget runs out the
    map phase stops consuming chunks and the caller reports a limited context instead of
    hanging: a partial, honestly-labelled answer beats an unavailable assistant.

    Yielding between chunks also makes the phase cancellable for the first time: a caller
    that abandons this generator raises ``GeneratorExit`` at the chunk boundary, so a
    browser pressing Stop no longer leaves a minute of local inference running.

    ``scope`` wraps each individual chunk, so a caller can pin per-request state
    (redaction uses it) without that state having to survive a ``yield`` -- a generator
    resumes on whichever worker thread the server happens to use.
    """
    deadline = None if budget_seconds is None else clock() + budget_seconds
    started = clock()
    partials: list[str] = []
    chunks_processed = 0
    calls = 0
    # Counted on what the model itself wrote, before citations are restored: the repair
    # adds bytes of our own and would otherwise mask a model that produced nothing.
    useless = 0
    budget_exhausted = False
    iterator = iter(chunks)
    while True:
        if deadline is not None and clock() >= deadline:
            budget_exhausted = True
            break
        with scope():
            chunk = next(iterator, None)
            if chunk is None:
                break
            text, model_output = _reduce(reducer, question, chunk)
        partials.append(text)
        useless += _is_useless(model_output)
        calls += 1
        chunks_processed += 1
        yield {
            "phase": "local_reduce",
            "chunks_done": chunks_processed,
            "elapsed_seconds": round(clock() - started, 2),
            "budget_seconds": budget_seconds,
        }
    source_truncated = bool(getattr(chunks, "truncated", False))
    mapped = chunks_processed

    def result(text: str, *, hard: bool, passes: int, spent: bool) -> ReducedEvidence:
        # One useless partial is noise; a run of them means the configured model cannot do
        # this job at all, and the caller must not present the answer as fully grounded.
        return ReducedEvidence(
            text=text,
            hard_truncated=hard,
            source_truncated=source_truncated,
            passes=passes,
            chunks_processed=chunks_processed,
            budget_exhausted=spent,
            reducer_calls=calls,
            degenerate=bool(mapped) and useless * 2 > mapped,
        )

    if not partials:
        return result("", hard=False, passes=0, spent=budget_exhausted)

    passes = 1
    for _ in range(_MAX_REDUCTION_PASSES - 1):
        joined = "\n\n".join(partials)
        if len(joined.encode("utf-8", "replace")) <= max_bytes:
            return result(joined, hard=False, passes=passes, spent=budget_exhausted)
        if deadline is not None and clock() >= deadline:
            return result(
                clip_utf8(joined, max_bytes), hard=True, passes=passes, spent=True
            )

        before = sum(len(item.encode("utf-8", "replace")) for item in partials)
        groups, packing_truncated = _pack_partials(partials, input_bytes or max_bytes)
        with scope():
            next_partials = [_reduce(reducer, question, group)[0] for group in groups]
        calls += len(groups)
        passes += 1
        yield {
            "phase": "local_merge",
            "chunks_done": chunks_processed,
            "pass": passes,
            "elapsed_seconds": round(clock() - started, 2),
            "budget_seconds": budget_seconds,
        }
        after = sum(len(item.encode("utf-8", "replace")) for item in next_partials)
        if packing_truncated or (
            len(next_partials) >= len(partials) and after >= before
        ):
            return result(
                clip_utf8("\n\n".join(next_partials), max_bytes),
                hard=True,
                passes=passes,
                spent=budget_exhausted,
            )
        partials = next_partials

    return result(
        clip_utf8("\n\n".join(partials), max_bytes),
        hard=True,
        passes=passes,
        spent=budget_exhausted,
    )


def _reduce(reducer: ContextReducer, question: str, context: str) -> tuple[str, str]:
    """Return the usable partial and what the model itself produced."""
    result = reducer.reduce(question=question, context=context).strip()
    if not result:
        raise RuntimeError("the local context model returned an empty summary")
    cleaned = redact_text(result)
    kept = _keep_runs(_keep_citations(cleaned, context), context)
    return _keep_failures(kept, context), cleaned


def _is_useless(model_output: str) -> bool:
    """Whether one model output is too small to carry a fact and cites nothing."""
    if _CITATION.search(model_output):
        return False
    return len(model_output.encode("utf-8", "replace")) < _MIN_USEFUL_PARTIAL_BYTES


def _keep_citations(summary: str, context: str) -> str:
    """Re-attach the ``[R<n>]`` labels of a chunk when the model dropped all of them.

    Small local models routinely ignore the instruction to preserve labels, and the final
    provider then has nothing to cite: evidence buttons fall back to arbitrary reports. The
    labels covered by this chunk are known exactly, so restoring them is deterministic. A
    model that kept any label is trusted and left alone.
    """
    if _CITATION.search(summary):
        return summary
    labels = list(dict.fromkeys(_CITATION.findall(context)))
    if not labels:
        return summary
    return f"{' '.join(labels)} — facts below come from these reports.\n{summary}"


def _chunk_failures(context: str) -> list[tuple[str, str, str, str]]:
    """Return ``(label, node_id, outcome, error)`` for each failure a raw chunk states."""
    errors: dict[str, str] = {}
    for key, body in _TRACEBACK_BLOCK.findall(context):
        lines = (line[len("| ") :] for line in body.splitlines())
        first = next((line for line in lines if line.strip()), "")
        errors[key] = first.strip()
    failures: list[tuple[str, str, str, str]] = []
    for raw in _CASE_LINE.findall(context):
        try:
            case = json.loads(raw)
        except ValueError:  # pragma: no cover - a clipped chunk boundary
            continue
        if case.get("outcome") not in {"failed", "error"}:
            continue
        node_id = str(case.get("node_id") or "").strip()
        if not node_id:
            continue
        failures.append(
            (
                f"[{case.get('report', '')}]",
                node_id,
                str(case.get("outcome")),
                errors.get(str(case.get("case")), ""),
            )
        )
    return failures


def _chunk_runs(context: str) -> list[tuple[str, str]]:
    """Return ``(run_id, one-line description)`` for each run a raw chunk states."""
    runs: list[tuple[str, str]] = []
    for label, raw in _RUN_LINE.findall(context):
        try:
            run = json.loads(raw)
        except ValueError:  # pragma: no cover - a clipped chunk boundary
            continue
        run_id = str(run.get("run_id", "?"))
        where = f"{run.get('dag_id', '?')}/{run_id}"
        counts = " ".join(
            f"{name}={run.get(name, 0)}"
            for name in ("total", "passed", "failed", "errors", "skipped")
        )
        runs.append((run_id, f"{label} {where} {counts}"))
    return runs


def _keep_runs(summary: str, context: str) -> str:
    """Restore which run each label is when the model's output does not say.

    ``[R1]`` identifies a report to the citation machinery and means nothing to a reader:
    asked what changed between runs, an answer could contrast R1 with R2 without ever
    naming ``run_c``, which is the only part anyone can act on. One line per run, and only
    when the model named none of them.
    """
    runs = _chunk_runs(context)
    if not runs:
        return summary
    # Judged on the run id, which is what a reader would recognise -- and on what the
    # model wrote, not on how this line happens to be formatted.
    if any(run_id in summary for run_id, _ in runs):
        return summary
    return "\n".join([line for _, line in runs[:_MAX_RESTORED_FAILURES]] + [summary])


def _keep_failures(summary: str, context: str) -> str:
    """Restore the failures a chunk stated when the model's output does not name them.

    The reducer prompt asks for extraction and a capable model obeys it. The models small
    enough to run in-process beside an API server frequently do not: measured on
    Qwen2.5-0.5B, a chunk naming two failing node ids, their outcomes and their error
    messages came back as one sentence of prose, and the final answer was then "the
    evidence contains no data about tests" -- true of what the model produced, false of
    the archive it was given.

    A summary is only a *loss* when the facts are gone, and the chunk's own CASE lines say
    exactly what they were, so this is restoration rather than invention. A model that
    named most of the failures is left alone: choosing which of forty to carry is the work
    it is there to do.
    """
    failures = _chunk_failures(context)
    if not failures:
        return summary
    named = sum(1 for _, node_id, _, _ in failures if node_id in summary)
    if named >= len(failures) * _MIN_NAMED_SHARE:
        return summary
    lines = [
        f"{label} {node_id} {outcome}"
        + (f" - {clip_utf8(error, _MAX_RESTORED_ERROR_CHARS)}" if error else "")
        for label, node_id, outcome, error in failures[:_MAX_RESTORED_FAILURES]
    ]
    if len(failures) > _MAX_RESTORED_FAILURES:
        lines.append(f"...and {len(failures) - _MAX_RESTORED_FAILURES} more failures")
    return "\n".join([*lines, summary])


def _pack_partials(partials: list[str], max_bytes: int) -> tuple[list[str], bool]:
    header = _GROUP_HEADER + "\n\n"
    budget = max(256, max_bytes - len(header.encode("utf-8")))
    groups: list[str] = []
    current: list[str] = []
    used = 0
    truncated = False
    for index, partial in enumerate(partials, 1):
        record = f"PARTIAL {index}\n{partial}"
        if len(record.encode("utf-8", "replace")) > budget:
            record = clip_utf8(record, budget)
            truncated = True
        cost = len((record + "\n\n").encode("utf-8"))
        if current and used + cost > budget:
            groups.append(header + "\n\n".join(current))
            current = []
            used = 0
        current.append(record)
        used += cost
    if current:
        groups.append(header + "\n\n".join(current))
    return groups, truncated


__all__ = ["ReducedEvidence", "reduce_context_tree"]
