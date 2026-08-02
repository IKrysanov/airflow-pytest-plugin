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

from collections.abc import Iterable
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


def reduce_context_tree(
    *,
    question: str,
    chunks: Iterable[str],
    reducer: ContextReducer,
    max_bytes: int,
    input_bytes: int | None = None,
) -> ReducedEvidence:
    """Map every raw chunk, then reduce summaries until one provider prompt fits."""
    partials: list[str] = []
    chunks_processed = 0
    for chunk in chunks:
        partials.append(_reduce(reducer, question, chunk))
        chunks_processed += 1
    source_truncated = bool(getattr(chunks, "truncated", False))
    if not partials:
        return ReducedEvidence("", False, source_truncated, 0, 0)

    passes = 1
    for _ in range(_MAX_REDUCTION_PASSES - 1):
        joined = "\n\n".join(partials)
        if len(joined.encode("utf-8", "replace")) <= max_bytes:
            return ReducedEvidence(
                joined, False, source_truncated, passes, chunks_processed
            )

        before = sum(len(item.encode("utf-8", "replace")) for item in partials)
        groups, packing_truncated = _pack_partials(partials, input_bytes or max_bytes)
        next_partials = [_reduce(reducer, question, group) for group in groups]
        passes += 1
        after = sum(len(item.encode("utf-8", "replace")) for item in next_partials)
        if packing_truncated or (
            len(next_partials) >= len(partials) and after >= before
        ):
            fallback = clip_utf8("\n\n".join(next_partials), max_bytes)
            return ReducedEvidence(
                fallback, True, source_truncated, passes, chunks_processed
            )
        partials = next_partials

    return ReducedEvidence(
        clip_utf8("\n\n".join(partials), max_bytes),
        True,
        source_truncated,
        passes,
        chunks_processed,
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
