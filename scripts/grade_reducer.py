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

"""Grade a real GGUF reducer against the answer-quality corpus.

Answers whether a candidate local model is good enough to be worth its RAM and latency.
Runs every scenario in ``tests/assistant_quality.py`` through the actual reduction pipeline
and reports, per model: how many required facts survived, how much it compressed, and how
long a chunk took.

    pip install 'airflow-pytest-plugin[assistant-local]'
    python scripts/grade_reducer.py /models/qwen2.5-3b-instruct-q4_k_m.gguf

Pass several paths to compare candidates. A model that scores below roughly 80% is worse
than sending the deterministic direct snapshot, which scores 100% by construction.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests"))


def _grade(model_path: str, budget: float) -> dict[str, object]:
    os.environ["AIRFLOW_PYTEST_ASSISTANT_PROVIDER"] = "fake"
    os.environ["AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL"] = model_path

    from airflow_pytest_plugin.assistant import AssistantQuery, AssistantSettings
    from airflow_pytest_plugin.assistant.context import ReportContextBuilder
    from airflow_pytest_plugin.assistant.reducers.llama import (
        LlamaCppReducer,
        safe_local_input_bytes,
    )
    from airflow_pytest_plugin.assistant.reduction import reduce_context_tree
    from assistant_quality import SCENARIOS, score

    settings = AssistantSettings.from_env()
    input_bytes = min(settings.max_context_bytes, safe_local_input_bytes(settings))
    reducer = LlamaCppReducer(settings)

    timings: list[float] = []
    ratios: list[float] = []
    found = missing = leaked = 0
    per_scenario: list[str] = []
    try:
        for scenario in SCENARIOS:
            context = ReportContextBuilder(
                max_context_bytes=input_bytes
            ).build_complete(
                source=scenario.source(),
                can_read=lambda dag, user: True,
                user=None,
                query=AssistantQuery(question=scenario.question),
            )
            raw = 0

            class _Timed:
                name = reducer.name

                def reduce(self, *, question: str, context: str) -> str:
                    nonlocal raw
                    raw += len(context.encode())
                    started = time.perf_counter()
                    out = reducer.reduce(question=question, context=context)
                    timings.append(time.perf_counter() - started)
                    return out

                def close(self) -> None:
                    return None

            result = reduce_context_tree(
                question=scenario.question,
                chunks=context.chunks,
                reducer=_Timed(),
                max_bytes=settings.max_context_bytes,
                input_bytes=input_bytes,
                budget_seconds=budget,
            )
            graded = score(scenario, result.text)
            found += len(graded.found)
            missing += len(graded.missing)
            leaked += len(graded.leaked)
            reduced = len(result.text.encode())
            if raw:
                ratios.append(reduced / raw)
            per_scenario.append(
                f"    {scenario.name:<22} {len(graded.found)}/"
                f"{len(graded.found) + len(graded.missing)} facts"
                + (f", missing {graded.missing}" if graded.missing else "")
                + (f", LEAKED {graded.leaked}" if graded.leaked else "")
            )
    finally:
        reducer.close()

    total = found + missing
    return {
        "model": Path(model_path).name,
        "size_mb": round(os.path.getsize(model_path) / 1024 / 1024, 1),
        "facts_kept_pct": round(100 * found / total, 1) if total else 0.0,
        "leaked": leaked,
        "compression": round(statistics.mean(ratios), 2) if ratios else 0.0,
        "p50_s": round(statistics.median(timings), 2) if timings else 0.0,
        "calls": len(timings),
        "detail": per_scenario,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", help="paths to .gguf files")
    parser.add_argument(
        "--budget",
        type=float,
        default=600.0,
        help="wall-clock budget per scenario (default: 600s, generous for grading)",
    )
    args = parser.parse_args()

    rows = []
    for model in args.models:
        if not Path(model).is_file():
            print(f"skipping {model}: not a file", file=sys.stderr)
            continue
        print(f"\n=== {Path(model).name} ===", flush=True)
        row = _grade(model, args.budget)
        rows.append(row)
        for line in row["detail"]:
            print(line)
        print(
            f"    facts kept {row['facts_kept_pct']}%  compression {row['compression']}x"
            f"  p50 {row['p50_s']}s over {row['calls']} calls"
        )

    if len(rows) > 1:
        print("\n=== comparison ===")
        print(f"{'model':<44}{'size':>8}{'facts':>8}{'compr':>8}{'p50':>8}")
        for row in rows:
            print(
                f"{row['model']:<44}{row['size_mb']:>7}M{row['facts_kept_pct']:>7}%"
                f"{row['compression']:>7}x{row['p50_s']:>7}s"
            )
    # A model that keeps less than 80% of the facts is worse than direct mode.
    return 0 if all(row["facts_kept_pct"] >= 80 for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
