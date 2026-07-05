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

"""E2E: a REAL pytest suite with ``@pytest.mark.flaky(reruns=3)`` archived over 10 runs.

Each run executes actual pytest in a subprocess: the marked test fails its first two
attempts and passes on the third, so pytest-rerunfailures retries it and the RUN ends
green. The junit is archived through the real ``ArchivingResultParser`` and then read
back through the real ``FileSystemReportSource`` -- verifying the whole pipeline
(parse -> meta -> list/detail/outcomes -> flaky detector -> email notification) copes
with rerun-decorated reports.

The important behavioural finding this pins down: a test that only succeeds via
IN-RUN reruns is invisible to the cross-run flaky detector (junit records the final
outcome), and an ``email=True`` notification for such a run is the green "passed" one.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from airflow_pytest_plugin.notifications import (
    AlertPolicy,
    flaky_nodes_for,
    notify_for_run,
)
from airflow_pytest_plugin.producer import ArchivingResultParser, archiving_parser
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import FakeTI

pytest.importorskip("pytest_rerunfailures")

_RUNS = 10
#: junit classname is the MODULE (no .py): pytest writes classname="test_flaky_rerun".
_NODE = "test_flaky_rerun::test_settles_after_reruns"


class _SpyMailer:
    def __init__(self) -> None:
        self.sends: list[dict] = []

    def send(self, *, subject, body, recipients, html=None, attachments=()) -> None:
        self.sends.append({"subject": subject})


@pytest.fixture
def flaky_project(tmp_path):
    """A real test file whose test fails twice per run, then passes (via reruns=3)."""
    (tmp_path / "test_flaky_rerun.py").write_text(
        textwrap.dedent(
            """
            import os
            import pytest

            @pytest.mark.flaky(reruns=3)
            def test_settles_after_reruns():
                counter = os.environ["APX_ATTEMPTS_FILE"]
                n = int(open(counter).read()) if os.path.exists(counter) else 0
                open(counter, "w").write(str(n + 1))
                assert n >= 2, f"attempt {n + 1} fails on purpose"
            """
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_flaky_rerun_suite_over_ten_runs(flaky_project, reports_root, monkeypatch):
    root = str(reports_root)
    for i in range(_RUNS):
        run_id = f"r{i:03d}"
        ti = FakeTI(dag_id="e2e_dag", task_id="smoke", run_id=run_id, try_number=1)
        monkeypatch.setattr(
            archiving_parser,
            "get_current_context",
            lambda ti=ti, r=run_id: {"ti": ti, "run_id": r},
        )
        parser = ArchivingResultParser(report_root=root)
        req = parser.report_request(str(flaky_project))
        os.makedirs(os.path.dirname(req.report_path), exist_ok=True)

        env = dict(os.environ)
        env["APX_ATTEMPTS_FILE"] = str(
            flaky_project / f"attempts_{run_id}"
        )  # fresh per run
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "test_flaky_rerun.py",
                "-p",
                "no:cacheprovider",
                "-q",
                f"--junitxml={req.report_path}",
            ],
            cwd=flaky_project,
            env=env,
            capture_output=True,
            text=True,
        )
        # The reruns must have rescued the run: pytest exits green.
        assert proc.returncode == 0, (
            f"run {run_id} did not settle:\n{proc.stdout}\n{proc.stderr}"
        )
        result = parser.parse(req.report_path, exit_code=proc.returncode)
        assert result.failed == 0 and result.errors == 0

    src = FileSystemReportSource(report_root=root, scan_cache_ttl=0)
    summaries = src.list_summaries()
    assert len(summaries) == _RUNS
    assert all(s.success for s in summaries), (
        "every rerun-rescued run counts as passing"
    )

    # Detail + per-test outcomes parse cleanly and show the FINAL outcome (passed).
    ref = summaries[0].ref
    detail = src.get_detail(ref)
    assert detail is not None and detail.summary.failed == 0
    outcomes = src.test_outcomes(ref)
    assert outcomes is not None and outcomes[_NODE]["outcome"] == "passed"

    # In-run reruns are invisible across runs: junit stores only the final outcome, so
    # the cross-run flaky detector must NOT flag the test over these 10 green runs.
    assert flaky_nodes_for(src, "e2e_dag", "smoke", window=30, min_score=0.0) == ()

    # And the email=True completion notice for the latest run is the green "passed" one.
    spy = _SpyMailer()
    policy = AlertPolicy(recipients=("team@example.com",))
    out = notify_for_run(src, summaries[0].ref, policy=policy, mailer=spy, always=True)
    assert [a.kind for a in out] == ["passed"]
    assert len(spy.sends) == 1 and "Passed" in spy.sends[0]["subject"]
