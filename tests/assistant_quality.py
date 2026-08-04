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

"""A fixed "report tree -> facts that must survive" corpus, plus a scorer.

Two jobs, one corpus:

* in CI it gates the deterministic path -- the direct snapshot must contain every required
  fact, so a change to context building, redaction or byte budgets that silently drops
  evidence fails the build;
* on demand it grades a real local model. ``scripts/grade_reducer.py`` runs the same
  scenarios through a GGUF reducer and prints the percentage of facts that survived, which
  is the only way to compare one candidate model against another.

A "fact" is a small, unambiguous probe (a node id, a count, an error string). Probes are
deliberately literal: an LLM-graded rubric would make the corpus itself unreliable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from airflow_pytest_plugin.models import (
    CaseView,
    ReportDetail,
    ReportRef,
    ReportSummary,
)
from airflow_pytest_plugin.sources import ReportSource


@dataclass(frozen=True)
class Fact:
    """One thing the evidence must carry for an answer to be possible."""

    name: str
    pattern: str
    #: Why the answer is wrong without it, for the failure message.
    because: str
    #: Only the local full-tree path can carry this. Direct mode details failed and errored
    #: cases only, so a fact about a test that stayed green is out of its reach by design --
    #: recording that here keeps the two modes' real capabilities honest instead of
    #: pretending direct mode can answer everything.
    full_tree_only: bool = False

    def present_in(self, text: str) -> bool:
        """Whether the evidence carries this fact."""
        return re.search(self.pattern, text, re.IGNORECASE | re.DOTALL) is not None


@dataclass(frozen=True)
class Scenario:
    """A synthetic report tree with a known, checkable ground truth."""

    name: str
    question: str
    runs: list[RunSpec]
    facts: list[Fact]
    #: Claims that must NOT appear: evidence that would make the model hallucinate.
    forbidden: list[Fact] = field(default_factory=list)

    def source(self) -> ReportSource:
        """Return a report source serving exactly this tree."""
        return _ScenarioSource(self.runs)


@dataclass(frozen=True)
class CaseSpec:
    """One test case inside a run."""

    node_id: str
    outcome: str = "passed"
    time: float = 0.1
    message: str | None = None
    output: str | None = None


@dataclass(frozen=True)
class RunSpec:
    """One archived run."""

    dag_id: str
    run_id: str
    task_id: str
    cases: list[CaseSpec]
    created_at: str | None = None

    @property
    def ref(self) -> ReportRef:
        return ReportRef(self.dag_id, self.run_id, self.task_id, 1)

    @property
    def summary(self) -> ReportSummary:
        failed = sum(1 for case in self.cases if case.outcome == "failed")
        errors = sum(1 for case in self.cases if case.outcome == "error")
        skipped = sum(1 for case in self.cases if case.outcome == "skipped")
        passed = len(self.cases) - failed - errors - skipped
        return ReportSummary(
            ref=self.ref,
            total=len(self.cases),
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration=round(sum(case.time for case in self.cases), 3),
            success=not (failed or errors),
            created_at=self.created_at,
        )


class _ScenarioSource(ReportSource):
    def __init__(self, runs: list[RunSpec]) -> None:
        self._runs = runs
        self._by_ref = {run.ref: run for run in runs}

    def list_summaries(
        self, *, dag_id: str | None = None, run_id: str | None = None
    ) -> list[ReportSummary]:
        return [
            run.summary
            for run in self._runs
            if (not dag_id or dag_id in run.dag_id)
            and (not run_id or run_id in run.run_id)
        ]

    def get_detail(self, ref: ReportRef) -> ReportDetail | None:
        run = self._by_ref.get(ref)
        if run is None:
            return None
        return ReportDetail(
            summary=run.summary,
            cases=tuple(
                CaseView(
                    node_id=case.node_id,
                    name=case.node_id.rsplit("::", 1)[-1],
                    classname=case.node_id.split("::", 1)[0],
                    outcome=case.outcome,
                    time=case.time,
                    message=case.message,
                    output=case.output,
                )
                for case in run.cases
            ),
        )

    def delete(self, ref: ReportRef) -> bool:
        del ref
        return False


@dataclass(frozen=True)
class Score:
    """How much of one scenario's ground truth survived into the evidence."""

    scenario: str
    found: list[str]
    missing: list[str]
    leaked: list[str]

    @property
    def ratio(self) -> float:
        total = len(self.found) + len(self.missing)
        return len(self.found) / total if total else 1.0

    @property
    def passed(self) -> bool:
        return not self.missing and not self.leaked


def score(scenario: Scenario, evidence: str, *, full_tree: bool = True) -> Score:
    """Grade one block of evidence against a scenario's ground truth.

    ``full_tree=False`` grades the direct snapshot, which is not expected to carry facts
    about tests that never failed.
    """
    expected = [fact for fact in scenario.facts if full_tree or not fact.full_tree_only]
    found = [fact.name for fact in expected if fact.present_in(evidence)]
    missing = [fact.name for fact in expected if not fact.present_in(evidence)]
    leaked = [fact.name for fact in scenario.forbidden if fact.present_in(evidence)]
    return Score(scenario.name, found, missing, leaked)


def _fail(node: str, message: str) -> CaseSpec:
    return CaseSpec(node_id=node, outcome="failed", time=0.2, message=message)


#: The corpus. Each scenario isolates one thing an answer commonly gets wrong.
SCENARIOS: list[Scenario] = [
    Scenario(
        name="single-failure",
        question="What failed in the latest run?",
        runs=[
            RunSpec(
                dag_id="etl_daily",
                run_id="scheduled__2026-08-01",
                task_id="unit_tests",
                created_at="2026-08-01T08:00:00+00:00",
                cases=[
                    CaseSpec("tests/test_load.py::test_reads_csv"),
                    CaseSpec("tests/test_load.py::test_writes_parquet"),
                    _fail(
                        "tests/test_load.py::test_rejects_bad_header",
                        "AssertionError: expected ValueError, got None",
                    ),
                ],
            )
        ],
        facts=[
            Fact(
                "failing node id",
                r"test_rejects_bad_header",
                "the answer cannot name which test broke",
            ),
            Fact(
                "assertion text",
                r"expected ValueError",
                "the answer cannot explain why it broke",
            ),
            Fact("dag id", r"etl_daily", "the answer cannot locate the run"),
            Fact(
                "failed count", r'"failed":\s*1|failed[^0-9]{0,12}1', "counts are wrong"
            ),
            Fact("total count", r'"total":\s*3|total[^0-9]{0,12}3', "counts are wrong"),
        ],
        forbidden=[
            Fact(
                "passing test presented as failure",
                r"test_reads_csv[^\n]{0,80}(failed|error)",
                "a green test must never be reported as broken",
            )
        ],
    ),
    Scenario(
        name="flaky-across-runs",
        question="Which test is flaky?",
        runs=[
            RunSpec(
                dag_id="ml_train",
                run_id=f"scheduled__2026-08-{day:02d}",
                task_id="suite",
                created_at=f"2026-08-{day:02d}T06:00:00+00:00",
                cases=[
                    CaseSpec("tests/test_model.py::test_deterministic_seed"),
                    (
                        _fail(
                            "tests/test_model.py::test_flaky_sampler",
                            "AssertionError: sampled 0.61, expected < 0.5",
                        )
                        if day % 2 == 0
                        else CaseSpec("tests/test_model.py::test_flaky_sampler")
                    ),
                ],
            )
            for day in range(1, 7)
        ],
        facts=[
            Fact(
                "flaky node id",
                r"test_flaky_sampler",
                "the answer cannot name the flaky test",
            ),
            Fact(
                "both outcomes present",
                r'"outcome":\s*"failed"',
                "without a failure the test looks stable",
            ),
            Fact(
                "several runs present",
                r"scheduled__2026-08-0[13579]",
                "one run cannot show flakiness",
            ),
            Fact(
                "stable test present",
                r"test_deterministic_seed",
                "the answer cannot say what stayed green",
                full_tree_only=True,
            ),
        ],
    ),
    Scenario(
        name="error-vs-failure",
        question="Did anything error rather than fail?",
        runs=[
            RunSpec(
                dag_id="etl_daily",
                run_id="manual__2026-08-02",
                task_id="integration",
                created_at="2026-08-02T09:00:00+00:00",
                cases=[
                    CaseSpec("tests/test_api.py::test_health"),
                    _fail(
                        "tests/test_api.py::test_timeout",
                        "AssertionError: response took 31s",
                    ),
                    CaseSpec(
                        "tests/test_api.py::test_setup_db",
                        outcome="error",
                        message="RuntimeError: could not connect to fixture database",
                    ),
                ],
            )
        ],
        facts=[
            Fact("errored node id", r"test_setup_db", "the answer misses the error"),
            Fact(
                "error outcome",
                r'"outcome":\s*"error"',
                "an error must not be flattened into a failure",
            ),
            Fact(
                "error message",
                r"could not connect to fixture database",
                "the answer cannot explain the error",
            ),
            Fact(
                "failure kept separate",
                r"test_timeout",
                "the failure must survive alongside the error",
            ),
        ],
    ),
    Scenario(
        name="multi-dag-scope",
        question="Which DAGs are broken right now?",
        runs=[
            RunSpec(
                dag_id="etl_daily",
                run_id="scheduled__2026-08-03",
                task_id="suite",
                created_at="2026-08-03T05:00:00+00:00",
                cases=[
                    _fail(
                        "tests/test_etl.py::test_partition",
                        "AssertionError: 3 partitions, expected 4",
                    )
                ],
            ),
            RunSpec(
                dag_id="reporting",
                run_id="scheduled__2026-08-03",
                task_id="suite",
                created_at="2026-08-03T05:30:00+00:00",
                cases=[CaseSpec("tests/test_report.py::test_renders")],
            ),
        ],
        facts=[
            Fact("broken dag", r"etl_daily", "the answer cannot name the broken DAG"),
            Fact("healthy dag", r"reporting", "the answer cannot say what is fine"),
            Fact(
                "failing node id",
                r"test_partition",
                "the answer cannot name the broken test",
            ),
            Fact(
                "partition assertion",
                r"3 partitions, expected 4",
                "the answer cannot explain the break",
            ),
        ],
    ),
]

SCENARIOS_BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}

__all__ = [
    "SCENARIOS",
    "SCENARIOS_BY_NAME",
    "CaseSpec",
    "Fact",
    "RunSpec",
    "Scenario",
    "Score",
    "score",
]
