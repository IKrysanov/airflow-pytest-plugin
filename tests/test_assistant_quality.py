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

"""Answer-quality regression: the evidence must carry the facts an answer needs.

The model itself is not called here -- what is gated is everything the plugin controls.
If context building, redaction, a byte budget or the local reduction path silently drops a
node id, a count or an error string, no model can answer correctly, and that is a
regression this suite catches. ``scripts/grade_reducer.py`` runs the same corpus through a
real GGUF to compare candidate models.
"""

from __future__ import annotations

import pytest

from airflow_pytest_plugin.assistant import (
    AssistantQuery,
    PassthroughReducer,
    ReportContextBuilder,
)
from airflow_pytest_plugin.assistant.reduction import reduce_context_tree
from assistant_quality import SCENARIOS, Scenario, score


def _direct_evidence(scenario: Scenario, *, max_bytes: int = 48 * 1024) -> str:
    return (
        ReportContextBuilder(max_context_bytes=max_bytes)
        .build(
            source=scenario.source(),
            can_read=lambda dag, user: True,
            user=None,
            query=AssistantQuery(question=scenario.question),
        )
        .text
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_direct_evidence_carries_every_required_fact(scenario: Scenario):
    result = score(scenario, _direct_evidence(scenario), full_tree=False)

    assert result.passed, (
        f"{scenario.name}: missing {result.missing}, leaked {result.leaked}"
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_complete_tree_chunks_carry_every_required_fact(scenario: Scenario):
    """The local path must not lose facts before the model even sees them."""
    context = ReportContextBuilder(max_context_bytes=9_714).build_complete(
        source=scenario.source(),
        can_read=lambda dag, user: True,
        user=None,
        query=AssistantQuery(question=scenario.question),
    )
    result = score(scenario, "\n".join(context.chunks))

    assert result.passed, (
        f"{scenario.name}: missing {result.missing}, leaked {result.leaked}"
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_a_faithful_reducer_keeps_every_fact_through_reduction(scenario: Scenario):
    """A reducer that keeps its input must not lose facts to the reduction machinery."""
    context = ReportContextBuilder(max_context_bytes=9_714).build_complete(
        source=scenario.source(),
        can_read=lambda dag, user: True,
        user=None,
        query=AssistantQuery(question=scenario.question),
    )
    reduced = reduce_context_tree(
        question=scenario.question,
        chunks=context.chunks,
        reducer=_Faithful(),
        max_bytes=256 * 1024,
        input_bytes=9_714,
    )
    result = score(scenario, reduced.text)

    assert result.passed, (
        f"{scenario.name}: missing {result.missing}, leaked {result.leaked}"
    )


class _Faithful:
    """Stands in for a perfect local model: returns exactly what it was given."""

    name = "faithful.gguf"

    def reduce(self, *, question: str, context: str) -> str:
        del question
        return context

    def close(self) -> None:
        return None


def test_the_corpus_actually_discriminates():
    """A scorer that passes anything would silently gate nothing."""
    for scenario in SCENARIOS:
        empty = score(scenario, "no evidence at all")
        assert not empty.passed
        assert empty.ratio == 0.0
        assert set(empty.missing) == {fact.name for fact in scenario.facts}


def test_direct_mode_is_not_asked_for_facts_only_the_full_tree_can_carry():
    """Direct mode details failed cases only; the corpus records that difference."""
    scenario = next(
        item for item in SCENARIOS if any(fact.full_tree_only for fact in item.facts)
    )
    evidence = _direct_evidence(scenario)

    assert score(scenario, evidence, full_tree=False).passed
    assert not score(scenario, evidence, full_tree=True).passed


def test_forbidden_claims_are_detected():
    scenario = next(item for item in SCENARIOS if item.forbidden)
    poisoned = (
        _direct_evidence(scenario) + "\ntests/test_load.py::test_reads_csv failed"
    )

    result = score(scenario, poisoned)

    assert result.leaked and not result.passed


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_a_tight_byte_budget_is_reported_not_hidden(scenario: Scenario):
    """When facts do not fit, the answer must be flagged rather than quietly thinned."""
    context = ReportContextBuilder(max_context_bytes=4_096).build(
        source=scenario.source(),
        can_read=lambda dag, user: True,
        user=None,
        query=AssistantQuery(question=scenario.question),
    )
    result = score(scenario, context.text, full_tree=False)

    assert result.passed or context.context_limited, (
        f"{scenario.name} lost {result.missing} without setting context_limited"
    )


def test_passthrough_reducer_is_a_no_op_for_the_direct_path():
    scenario = SCENARIOS[0]
    evidence = _direct_evidence(scenario)

    assert (
        PassthroughReducer().reduce(question=scenario.question, context=evidence)
        == evidence
    )
