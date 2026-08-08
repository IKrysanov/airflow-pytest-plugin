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

"""RBAC-filtered report evidence for direct and full local-model paths."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from itertools import islice
from typing import Any

from ..models import CaseView, ReportRef, ReportSummary
from ..sources import ReportSource
from .common import (
    MAX_CAPTURE_BYTES,
    MAX_FAILURE_BYTES,
    MAX_SUMMARIES,
    AssistantContext,
    AssistantEvidence,
    AssistantQuery,
    AssistantScope,
    clip_utf8,
)
from .exceptions import AssistantForbiddenError, AssistantRequestError
from .redaction import redact_text

_MAX_NODE_ID_BYTES = 1_024
_MAX_VERDICT_FIELD_BYTES = 600
_MAX_MODEL_SCOPE_BYTES = 512
_MAX_VERDICT_DEPTH = 4
_MAX_VERDICT_MAPPING_ITEMS = 32
_MAX_VERDICT_SEQUENCE_ITEMS = 64


def _bounded_redacted(text: str | None, limit: int) -> tuple[str, bool]:
    cleaned = redact_text(text or "")
    return clip_utf8(cleaned, limit), len(cleaned.encode("utf-8", "replace")) > limit


def _safe_mapping(
    value: dict[str, Any] | None,
    *,
    depth: int = 0,
) -> tuple[dict[str, Any] | None, bool]:
    if not value:
        return None, False
    result: dict[str, Any] = {}
    truncated = len(value) > _MAX_VERDICT_MAPPING_ITEMS
    for key, item in islice(value.items(), _MAX_VERDICT_MAPPING_ITEMS):
        safe_key, key_clipped = _bounded_redacted(str(key), _MAX_VERDICT_FIELD_BYTES)
        result[safe_key], item_clipped = _safe_value(item, depth=depth + 1)
        truncated = truncated or key_clipped or item_clipped
    return result, truncated


def _safe_value(value: Any, *, depth: int) -> tuple[Any, bool]:
    if isinstance(value, str):
        return _bounded_redacted(value, _MAX_VERDICT_FIELD_BYTES)
    if isinstance(value, dict):
        if depth >= _MAX_VERDICT_DEPTH:
            return "...[truncated]...", True
        return _safe_mapping(value, depth=depth)
    if isinstance(value, (list, tuple)):
        if depth >= _MAX_VERDICT_DEPTH:
            return "...[truncated]...", True
        result: list[Any] = []
        truncated = len(value) > _MAX_VERDICT_SEQUENCE_ITEMS
        for item in value[:_MAX_VERDICT_SEQUENCE_ITEMS]:
            safe_item, item_truncated = _safe_value(item, depth=depth + 1)
            result.append(safe_item)
            truncated = truncated or item_truncated
        return result, truncated
    if value is None or isinstance(value, (bool, int, float)):
        return value, False
    return _bounded_redacted(str(value), _MAX_VERDICT_FIELD_BYTES)


def _summary_record(summary: ReportSummary) -> tuple[dict[str, Any], bool]:
    triage, truncated = _safe_mapping(summary.triage)
    values: dict[str, Any] = {
        "dag_id": summary.ref.dag_id,
        "run_id": summary.ref.run_id,
        "task_id": summary.ref.task_id,
        "try_number": summary.ref.try_number,
        "map_index": summary.ref.map_index,
        "created_at": summary.created_at,
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "errors": summary.errors,
        "skipped": summary.skipped,
        "duration": summary.duration,
        "success": summary.success,
        "triage": triage,
    }
    for key in ("dag_id", "run_id", "task_id", "created_at"):
        item = values[key]
        if isinstance(item, str):
            values[key], clipped = _bounded_redacted(item, _MAX_MODEL_SCOPE_BYTES)
            truncated = truncated or clipped
    return values, truncated


#: A question about how long something took, in either interface language. Per-test detail
#: is otherwise carried only for failures -- which is right, because a traceback is what a
#: failure question needs and a passing test has nothing to say -- but it left the one
#: question whose answer is usually a test that passed unanswerable: asked which test was
#: slowest, the assistant could see the durations of failures and nothing else.
_DURATION_QUESTION = re.compile(
    r"(?i)(slow|slowest|fastest|duration|how long|takes? the most|elapsed|"
    r"медлен|быстр|длительн|дольше|доль|сколько (?:по )?времени|время выполнен)"
)

#: Kept per report while scanning, then ranked across all of them. Both bounds matter:
#: the per-report one keeps the working set small, and the total one stops a wide scope
#: turning "which test is slowest" into a full listing that evicts the failures. Durations
#: are an extra and are appended only once every failure has its place.
_MAX_SLOWEST_CASES = 5
_MAX_SLOWEST_TOTAL = 20


#: Free text is prefixed line by line, so nothing inside it can be read back as one of
#: this format's own records. A test's stdout is untrusted data that is archived verbatim,
#: and a test that printed ``CASE {"node_id": ..., "outcome": "failed"}`` otherwise had
#: that line parsed as a real result -- inventing a failure of a test that never ran and
#: handing it to the answering model with a report label attached. One byte per line.
_FENCE = "| "


def _fenced(text: str) -> str:
    """Return free text that cannot be mistaken for a structural line."""
    return "\n".join(f"{_FENCE}{line}" for line in text.splitlines())


def _json(value: dict[str, Any]) -> str:
    """Serialize a record whose string values were already redacted and bounded."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _case_values(
    case: CaseView, evidence: AssistantEvidence
) -> tuple[dict[str, Any], bool]:
    node_id, truncated = _bounded_redacted(case.node_id, _MAX_NODE_ID_BYTES)
    verdict = case.verdict.to_dict() if case.verdict else None
    safe_verdict, verdict_truncated = _safe_mapping(verdict)
    return (
        {
            "report": evidence.key,
            "node_id": node_id,
            "outcome": case.outcome,
            "duration": case.time,
            "verdict": safe_verdict,
        },
        truncated or verdict_truncated,
    )


class _CompleteChunkStream:
    """Yield raw tree chunks once, keeping only one local-model input in memory."""

    def __init__(
        self,
        *,
        source: ReportSource,
        summaries: list[ReportSummary],
        evidence_by_token: dict[str, AssistantEvidence],
        max_bytes: int,
        header: str,
        max_failure_bytes: int,
        max_capture_bytes: int,
    ) -> None:
        self._source = source
        self._summaries = summaries
        self._evidence_by_token = evidence_by_token
        self._header = header
        header_bytes = len(header.encode("utf-8"))
        self._payload_bytes = max(512, max_bytes - header_bytes - 64)
        self._consumed = False
        self._max_failure_bytes = max_failure_bytes
        self._max_capture_bytes = max_capture_bytes
        self.truncated = False
        self.context_limited = False

    def __iter__(self) -> Iterator[str]:
        if self._consumed:
            raise RuntimeError("complete assistant context can only be consumed once")
        self._consumed = True
        records: list[str] = []
        used = 0
        chunk_number = 0
        for record in self._records():
            if len(record.encode("utf-8", "replace")) > self._payload_bytes:
                record = clip_utf8(record, self._payload_bytes)
                self.truncated = True
                self.context_limited = True
            cost = len((record + "\n").encode("utf-8"))
            if records and used + cost > self._payload_bytes:
                chunk_number += 1
                yield self._render(chunk_number, records)
                records = []
                used = 0
            records.append(record)
            used += cost
        if records:
            chunk_number += 1
            yield self._render(chunk_number, records)

    def _records(self) -> Iterator[str]:
        for summary in self._summaries:
            evidence = self._evidence_by_token[summary.ref.token]
            values, values_truncated = _summary_record(summary)
            self.truncated = self.truncated or values_truncated
            yield f"RUN [{evidence.key}] {_json(values)}"
            detail = self._source.get_detail(summary.ref)
            if detail is None:
                continue
            for index, case in enumerate(detail.cases, 1):
                values, values_truncated = _case_values(case, evidence)
                case_key = f"{evidence.key}:C{index}"
                values["case"] = case_key
                self.truncated = self.truncated or values_truncated
                yield f"CASE {_json(values)}"
                if case.outcome not in {"failed", "error"}:
                    continue
                traceback, traceback_truncated = _bounded_redacted(
                    case.message, self._max_failure_bytes
                )
                captured, captured_truncated = _bounded_redacted(
                    case.output, self._max_capture_bytes
                )
                self.truncated = self.truncated or any(
                    (traceback_truncated, captured_truncated)
                )
                if traceback:
                    yield f"TRACEBACK {case_key}\n{_fenced(traceback)}"
                if captured:
                    yield f"CAPTURED OUTPUT {case_key}\n{_fenced(captured)}"

    def _render(self, chunk_number: int, records: list[str]) -> str:
        return f"{self._header}Chunk: {chunk_number}\n\n" + "\n".join(records)


class ReportContextBuilder:
    """Build direct bounded evidence or a complete, locally reducible report tree."""

    def __init__(
        self,
        *,
        max_context_bytes: int,
        max_summaries: int = MAX_SUMMARIES,
        max_failure_bytes: int = MAX_FAILURE_BYTES,
        max_capture_bytes: int = MAX_CAPTURE_BYTES,
    ) -> None:
        self._max_context_bytes = max(4_096, max_context_bytes)
        self._max_summaries = max(1, max_summaries)
        self._max_failure_bytes = max(0, max_failure_bytes)
        self._max_capture_bytes = max(0, max_capture_bytes)

    def build(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> AssistantContext:
        """Build the deliberately bounded snapshot used without a local model."""
        summaries = self._visible_summaries(source, can_read, user, query.scope)
        reports_considered = len(summaries)
        limited = summaries[: self._max_summaries]
        context_limited = reports_considered > len(limited)
        truncated = context_limited
        scope_label = self._scope_label(query.scope, reports_considered)
        header = (
            f"Scope: {scope_label}\n"
            f"Readable reports in scope: {reports_considered}\n"
            f"Context truncated: {'yes' if truncated else 'no'}\n"
        )
        structural_bytes = len(
            (header + "\nRUN SUMMARIES\n\nFAILED OR ERRORED TESTS\n").encode("utf-8")
        )
        payload_budget = max(0, self._max_context_bytes - structural_bytes)

        evidence_by_token: dict[str, AssistantEvidence] = {}
        summary_lines: list[str] = []
        included_summaries: list[ReportSummary] = []
        used = 0
        for summary in limited:
            evidence = self._evidence(summary, evidence_by_token)
            values, values_truncated = _summary_record(summary)
            truncated = truncated or values_truncated
            line = f"[{evidence.key}] " + _json(values)
            cost = len((line + "\n").encode("utf-8"))
            if used + cost > payload_budget:
                truncated = True
                context_limited = True
                break
            summary_lines.append(line)
            included_summaries.append(summary)
            used += cost

        detail_lines: list[str] = []
        detail_budget = max(0, payload_budget - used)
        detail_used = 0
        wants_durations = bool(_DURATION_QUESTION.search(query.question or ""))
        slowest_pool: list[tuple[float, str]] = []
        candidates = [s for s in included_summaries if s.failed or s.errors]
        if wants_durations:
            # Every report has a slowest test, including the ones where nothing failed.
            seen = {id(item) for item in candidates}
            candidates = candidates + [
                item for item in included_summaries if id(item) not in seen
            ]
        detail_budget_exhausted = False
        for summary in candidates:
            detail = source.get_detail(summary.ref)
            if detail is None:
                continue
            evidence = self._evidence(summary, evidence_by_token)
            failures = [
                case for case in detail.cases if case.outcome in {"failed", "error"}
            ]
            for case in failures:
                record, record_truncated = _case_values(case, evidence)
                traceback, traceback_truncated = _bounded_redacted(
                    case.message, self._max_failure_bytes
                )
                captured, captured_truncated = _bounded_redacted(
                    case.output, self._max_capture_bytes
                )
                record["traceback"] = traceback
                record["captured"] = captured or None
                truncated = truncated or any(
                    (record_truncated, traceback_truncated, captured_truncated)
                )
                line = _json(record)
                cost = len((line + "\n").encode("utf-8"))
                if detail_used + cost > detail_budget:
                    truncated = True
                    context_limited = True
                    detail_budget_exhausted = True
                    break
                detail_lines.append(line)
                detail_used += cost
            if wants_durations:
                slowest = sorted(
                    (case for case in detail.cases if case.time),
                    key=lambda case: -(case.time or 0.0),
                )[:_MAX_SLOWEST_CASES]
                for case in slowest:
                    record, record_truncated = _case_values(case, evidence)
                    truncated = truncated or record_truncated
                    # The traceback is already above for a failure; this block answers
                    # "how long", so it carries nothing else.
                    slowest_pool.append(
                        (
                            float(record["duration"] or 0.0),
                            _json(
                                {
                                    "report": record["report"],
                                    "node_id": record["node_id"],
                                    "outcome": record["outcome"],
                                    "duration": record["duration"],
                                }
                            ),
                        )
                    )
            if detail_budget_exhausted or detail_used >= detail_budget:
                break

        # Appended last, so a duration question is answered with everything a failure
        # question would have had, plus whatever room is left over.
        for _, line in sorted(slowest_pool, key=lambda item: -item[0])[
            :_MAX_SLOWEST_TOTAL
        ]:
            if line in detail_lines:
                continue
            cost = len((line + "\n").encode("utf-8"))
            if detail_used + cost > detail_budget:
                truncated = True
                context_limited = True
                break
            detail_lines.append(line)
            detail_used += cost

        header = (
            f"Scope: {scope_label}\n"
            f"Readable reports in scope: {reports_considered}\n"
            f"Context truncated: {'yes' if truncated else 'no'}\n"
        )
        text = (
            header
            + "\nRUN SUMMARIES\n"
            + ("\n".join(summary_lines) or "(none)")
            + "\n\nFAILED OR ERRORED TESTS\n"
            + ("\n".join(detail_lines) or "(none)")
        )
        clipped_text = clip_utf8(text, self._max_context_bytes)
        if len(text.encode("utf-8", "replace")) > self._max_context_bytes:
            truncated = True
            context_limited = True
        included_evidence = tuple(
            item
            for item in evidence_by_token.values()
            if f"[{item.key}]" in clipped_text
        )
        return AssistantContext(
            text=clipped_text,
            evidence=included_evidence,
            reports_considered=reports_considered,
            truncated=truncated,
            context_limited=context_limited,
            scope_label=scope_label,
        )

    def build_complete(
        self,
        *,
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        query: AssistantQuery,
    ) -> AssistantContext:
        """Build chunks covering every readable run and every case for local reduction."""
        summaries = self._visible_summaries(source, can_read, user, query.scope)
        reports_considered = len(summaries)
        scope_label = self._scope_label(query.scope, reports_considered)
        model_scope, scope_truncated = _bounded_redacted(
            scope_label, _MAX_MODEL_SCOPE_BYTES
        )
        header = (
            f"Scope: {model_scope}\n"
            f"Readable reports in scope: {reports_considered}\n"
            "Coverage: complete report tree; every readable run and test case was "
            "processed locally.\n"
        )
        evidence_by_token: dict[str, AssistantEvidence] = {}
        for summary in summaries:
            self._evidence(summary, evidence_by_token)
        chunks = _CompleteChunkStream(
            source=source,
            summaries=summaries,
            evidence_by_token=evidence_by_token,
            max_bytes=self._max_context_bytes,
            header=header,
            max_failure_bytes=self._max_failure_bytes,
            max_capture_bytes=self._max_capture_bytes,
        )
        return AssistantContext(
            text="",
            chunks=chunks,
            evidence=tuple(evidence_by_token.values()),
            reports_considered=reports_considered,
            truncated=scope_truncated,
            context_limited=False,
            scope_label=scope_label,
        )

    @staticmethod
    def _visible_summaries(
        source: ReportSource,
        can_read: Callable[[str, Any], bool],
        user: Any,
        scope: AssistantScope,
    ) -> list[ReportSummary]:
        summaries = source.list_summaries(dag_id=scope.dag_id, run_id=scope.run_id)
        task = (scope.task_id or "").lower()
        authorization: dict[str, bool] = {}

        def may_read(dag_id: str) -> bool:
            if dag_id not in authorization:
                authorization[dag_id] = can_read(dag_id, user)
            return authorization[dag_id]

        visible = [
            summary
            for summary in summaries
            if (not task or task in summary.ref.task_id.lower())
            and may_read(summary.ref.dag_id)
        ]
        if not scope.report_ids:
            return visible

        requested: list[str] = []
        seen: set[str] = set()
        for token in scope.report_ids:
            try:
                ref = ReportRef.from_token(token)
            except ValueError as exc:
                raise AssistantRequestError(
                    "Malformed report id in assistant scope."
                ) from exc
            if not may_read(ref.dag_id):
                raise AssistantForbiddenError(
                    "You are not authorized to read one of the selected reports."
                )
            canonical = ref.token
            if canonical not in seen:
                requested.append(canonical)
                seen.add(canonical)
        by_token = {summary.ref.token: summary for summary in visible}
        return [by_token[token] for token in requested if token in by_token]

    @staticmethod
    def _evidence(
        summary: ReportSummary,
        evidence_by_token: dict[str, AssistantEvidence],
    ) -> AssistantEvidence:
        token = summary.ref.token
        found = evidence_by_token.get(token)
        if found is not None:
            return found
        item = AssistantEvidence(
            key=f"R{len(evidence_by_token) + 1}",
            report_id=token,
            dag_id=summary.ref.dag_id,
            run_id=summary.ref.run_id,
            task_id=summary.ref.task_id,
            created_at=summary.created_at,
        )
        evidence_by_token[token] = item
        return item

    @staticmethod
    def _scope_label(scope: AssistantScope, count: int) -> str:
        if scope.report_ids:
            return f"{count} selected report(s)"
        parts = [
            value
            for value in (
                f"dag~{scope.dag_id}" if scope.dag_id else None,
                f"task~{scope.task_id}" if scope.task_id else None,
                f"run~{scope.run_id}" if scope.run_id else None,
            )
            if value
        ]
        return " · ".join(parts) if parts else "all readable reports"


__all__ = ["ReportContextBuilder"]
