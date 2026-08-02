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

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .common import ContextReducer, clip_utf8
from .redaction import redact_text

_MAX_REDUCTION_PASSES = 12
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

    ``budget_seconds`` bounds the wall clock spent in the local model. A synchronous
    llama.cpp call cannot be cancelled and the runtime holds its only slot for the whole
    request, so an unbounded tree would otherwise let one question monopolize the
    assistant for as long as it takes to map every chunk. When the budget runs out the
    map phase stops consuming chunks and the caller reports a limited context instead of
    hanging: a partial, honestly-labelled answer beats an unavailable assistant.
    """
    deadline = None if budget_seconds is None else clock() + budget_seconds
    partials: list[str] = []
    chunks_processed = 0
    calls = 0
    budget_exhausted = False
    for chunk in chunks:
        if deadline is not None and clock() >= deadline:
            budget_exhausted = True
            break
        partials.append(_reduce(reducer, question, chunk))
        calls += 1
        chunks_processed += 1
    source_truncated = bool(getattr(chunks, "truncated", False))

    def result(text: str, *, hard: bool, passes: int, spent: bool) -> ReducedEvidence:
        return ReducedEvidence(
            text=text,
            hard_truncated=hard,
            source_truncated=source_truncated,
            passes=passes,
            chunks_processed=chunks_processed,
            budget_exhausted=spent,
            reducer_calls=calls,
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
        next_partials = [_reduce(reducer, question, group) for group in groups]
        calls += len(groups)
        passes += 1
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


def _reduce(reducer: ContextReducer, question: str, context: str) -> str:
    result = reducer.reduce(question=question, context=context).strip()
    if not result:
        raise RuntimeError("the local context model returned an empty summary")
    return redact_text(result)


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
