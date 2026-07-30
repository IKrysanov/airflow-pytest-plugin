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

"""End-to-end against the REAL pytest-triage, with its offline ``fake`` provider.

Everything else mocks the report; this drives an actual pytest run through the flags the
parser splices in, then archives what pytest-triage really wrote. That pins the parts of
the contract no unit test can see: the flag names, the report schema, and -- the subtle one
-- that pytest's own node ids join to the JUnit parser's dotted ones.

Skipped when pytest-triage isn't installed (it is an optional integration), so the default
suite is unaffected.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

from airflow_pytest_plugin.layout import (
    META_FILENAME,
    TRIAGE_FILENAME,
    VERDICTS_FILENAME,
    ReportLayout,
)
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.producer import ArchivingResultParser, archiving_parser
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import FakeTI

pytest.importorskip("pytest_triage", reason="pip install pytest-triage to run these")

#: A suite that breaks four different ways: a stale expectation, an unreachable service, and
#: two parametrised cases whose failures are as close to identical as pytest allows.
SUITE = textwrap.dedent(
    """
    import pytest


    class TestCheckout:
        def test_total(self):
            subtotal, tax, shipping = 100.0, 8.5, 5.0
            assert subtotal + tax + shipping == 108.5


    def test_db_connection():
        raise ConnectionError("could not connect to db at 10.0.0.5:5432")


    def _reach_payments():
        raise ConnectionError("could not connect to db at 10.0.0.5:5432")


    # Same call, same lines, same message -- as close to a duplicate failure as a suite
    # gets. pytest still prints "case = 'a b'" into each traceback, which is why even this
    # pair misses pytest-triage's cache (see test_the_bill_is_one_provider_call_per_failing_test).
    # The ids also carry a space and a slash, so the node-id round trip is exercised.
    @pytest.mark.parametrize("case", ["a b", "x/y"])
    def test_parametrised(case):
        _reach_payments()


    def test_ok():
        assert True
    """
)


def _run_pytest(suite_dir, args: list[str]):
    """Run the generated suite in a child pytest with ``args`` spliced in."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "tests", *args],
        cwd=suite_dir,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def suite(tmp_path):
    tests = tmp_path / "suite" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_shop.py").write_text(SUITE, encoding="utf-8")
    return str(tmp_path / "suite")


def _archive(monkeypatch, reports_root, suite_dir, *, try_number=1, **parser_kwargs):
    """Archive one real triaged run of ``suite_dir``.

    Returns ``(raw, stdout, report_dir)`` where ``raw`` is what pytest-triage itself wrote,
    captured BEFORE the parser distils and removes it -- the only moment it exists.
    """
    ti = FakeTI(dag_id="shop", task_id="suite", run_id="run1", try_number=try_number)
    monkeypatch.setattr(archiving_parser, "get_current_context", lambda: {"ti": ti})
    parser = ArchivingResultParser(report_root=reports_root, **parser_kwargs)
    req = parser.report_request("/runner/tmp")
    report_dir = os.path.dirname(req.report_path)
    os.makedirs(report_dir, exist_ok=True)
    proc = _run_pytest(suite_dir, list(req.pytest_args))

    raw_path = os.path.join(report_dir, TRIAGE_FILENAME)
    raw = None
    if os.path.exists(raw_path):
        raw = {
            "mode": os.stat(raw_path).st_mode & 0o777,
            "text": open(raw_path, encoding="utf-8").read(),
        }
    parser.parse(req.report_path, exit_code=proc.returncode)
    return raw, proc.stdout, report_dir


def test_a_real_triaged_run_archives_verdicts_that_join_to_their_cases(
    monkeypatch, reports_root, suite
):
    raw, stdout, report_dir = _archive(
        monkeypatch, reports_root, suite, triage_provider="fake"
    )
    assert "pytest-triage:" in stdout, stdout[-2000:]

    # pytest-triage wrote its own report; we distilled it and dropped the original.
    assert raw is not None
    assert not os.path.exists(os.path.join(report_dir, TRIAGE_FILENAME))
    meta = json.load(open(os.path.join(report_dir, META_FILENAME), encoding="utf-8"))
    assert meta["triage"]["total_failures"] == 4
    assert "verdicts" not in meta["triage"]

    detail = FileSystemReportSource(report_root=reports_root).get_detail(
        ReportRef("shop", "run1", "suite", 1)
    )
    judged = {c.node_id: c.verdict for c in detail.cases if c.verdict}
    # Every failure got a verdict, and every verdict found its case: the dotted/slash node-id
    # join is the piece most likely to silently break, so assert the exact ids.
    assert set(judged) == {
        "tests.test_shop.TestCheckout::test_total",
        "tests.test_shop::test_db_connection",
        "tests.test_shop::test_parametrised[a b]",
        "tests.test_shop::test_parametrised[x/y]",
    }
    assert detail.cases[-1].verdict is None  # test_ok passed
    # The fake provider classifies off the exception type, so these are its real answers.
    assert judged["tests.test_shop::test_db_connection"].category == "env"
    assert judged["tests.test_shop.TestCheckout::test_total"].category == "test_bug"
    # A parametrised id survives the round trip, spaces and slashes included.
    assert (
        judged["tests.test_shop::test_parametrised[x/y]"].selector
        == "tests/test_shop.py::test_parametrised[x/y]"
    )
    assert detail.triage.total_verdicts == 4


def _call_stats(stdout: str) -> tuple[int, int]:
    """``(provider calls, cache hits)`` from pytest-triage's terminal summary."""
    line = next(ln for ln in stdout.splitlines() if "provider call(s)" in ln)
    calls, hits = line.split(":")[-1].split(",")
    return int(calls.split()[0]), int(hits.split()[0])


def test_the_bill_is_one_provider_call_per_failing_test(
    monkeypatch, reports_root, suite
):
    # What a run actually costs. pytest-triage does cache, but it keys on the whole
    # traceback -- and pytest prints each test's arguments into that ("case = 'a b'"), so
    # even two parametrised cases of ONE test failing identically hash differently. Measured
    # here rather than assumed: the cache does not fire, and the honest planning number is
    # one call per failing test, bounded by --ai-budget.
    _, stdout, _ = _archive(monkeypatch, reports_root, suite, triage_provider="fake")
    calls, hits = _call_stats(stdout)
    assert (calls, hits) == (4, 0), stdout[-600:]


def test_a_retry_is_triaged_independently_of_its_earlier_try(
    monkeypatch, reports_root, suite
):
    # Each try archives to its own directory, so a retry re-runs the provider on the same
    # failures and pays for them again -- there is no cache across processes. Both tries
    # keep their own analysis, which is what makes "did the retry fail differently?"
    # answerable at all.
    _, out1, dir1 = _archive(
        monkeypatch, reports_root, suite, try_number=1, triage_provider="fake"
    )
    _, out2, dir2 = _archive(
        monkeypatch, reports_root, suite, try_number=2, triage_provider="fake"
    )
    assert dir1 != dir2
    assert [_call_stats(out1)[0], _call_stats(out2)[0]] == [4, 4], (
        "a retry re-spends the full budget -- the cache is in-memory, per pytest process"
    )

    src = FileSystemReportSource(report_root=reports_root)
    for try_number in (1, 2):
        detail = src.get_detail(ReportRef("shop", "run1", "suite", try_number))
        assert detail.triage.total_verdicts == 4, f"try {try_number}"
    assert {s.ref.try_number for s in src.list_summaries()} == {1, 2}


def test_the_budget_caps_what_a_wide_breakage_costs(monkeypatch, reports_root, suite):
    # The knob that bounds the bill -- and the case that proves degraded "verdicts" are not
    # stored as judgements. Past the budget pytest-triage still emits a verdict object per
    # failure, category "unknown", hypothesis "triage budget exhausted". Kept, those three
    # would show as Unclear chips and make the run look fully analysed.
    _, stdout, report_dir = _archive(
        monkeypatch, reports_root, suite, triage_provider="fake", triage_budget=2
    )
    assert _call_stats(stdout)[0] == 2
    doc = json.load(open(os.path.join(report_dir, VERDICTS_FILENAME), encoding="utf-8"))
    assert len(doc["verdicts"]) == 2

    detail = FileSystemReportSource(report_root=reports_root).get_detail(
        ReportRef("shop", "run1", "suite", 1)
    )
    assert detail.triage.total_verdicts == 2 and detail.triage.total_failures == 4
    assert detail.triage.incomplete == "triage budget exhausted"
    assert sum(detail.triage.counts.values()) == 2


def test_a_rejected_api_key_is_reported_as_a_broken_pass_not_as_verdicts(
    monkeypatch, reports_root, suite
):
    # The failure mode a real user hits first. `oauth-fake` needs a token; with the
    # env var it expects unset, every call raises -- and pytest-triage returns
    # category="unknown" verdicts stamped "triage provider error: ...". Surfacing those as
    # AI judgements would tell an on-call engineer their tests are "Unclear" when in truth
    # nothing was analysed and the credentials are wrong.
    monkeypatch.delenv("OAUTH_FAKE_TOKEN", raising=False)
    raw, _, report_dir = _archive(
        monkeypatch, reports_root, suite, triage_provider="fake", triage_budget=1
    )
    # Sanity: the healthy path above this line is what makes the next assertion meaningful.
    report = json.loads(raw["text"])
    degraded = [
        f
        for f in report["failures"]
        if f["verdict"] and f["verdict"]["hypothesis"].startswith("triage ")
    ]
    assert degraded, "expected pytest-triage to stamp its degraded verdicts"

    detail = FileSystemReportSource(report_root=reports_root).get_detail(
        ReportRef("shop", "run1", "suite", 1)
    )
    judged = [c for c in detail.cases if c.verdict]
    assert len(judged) == 1, "only the real verdict is a verdict"
    assert detail.triage.incomplete is not None
    assert all(c.verdict.hypothesis != "triage budget exhausted" for c in judged)


def test_report_only_mode_describes_every_failure_without_a_provider(
    monkeypatch, reports_root, suite
):
    # No provider, no network, no cost -- and still a machine-readable report of every
    # failure. The run reads as triaged, with nothing judged.
    raw, stdout, _ = _archive(monkeypatch, reports_root, suite, triage=True)
    report = json.loads(raw["text"])
    assert report["total_failures"] == 4
    assert all(f["verdict"] is None for f in report["failures"])
    assert "provider call(s)" not in stdout

    detail = FileSystemReportSource(report_root=reports_root).get_detail(
        ReportRef("shop", "run1", "suite", 1)
    )
    assert detail.triage is not None
    assert detail.triage.total_verdicts == 0 and detail.triage.model is None
    # ...and this is what the flag actually buys: every failure still reaches the UI with
    # its exception type and a command that reruns exactly it.
    described = [c for c in detail.cases if c.verdict]
    assert len(described) == 4
    assert all(v.category is None for v in (c.verdict for c in described))
    assert {c.verdict.exc_type for c in described} == {
        "AssertionError",
        "ConnectionError",
    }
    assert all(c.verdict.selector.startswith("tests/test_shop.py::") for c in described)


def test_installing_pytest_triage_changes_nothing_until_asked(
    monkeypatch, reports_root, suite
):
    # The whole feature is opt-in: with no triage flags the archive must look exactly as it
    # did before pytest-triage was on the worker at all.
    _, stdout, report_dir = _archive(monkeypatch, reports_root, suite)
    assert not any(
        os.path.exists(os.path.join(report_dir, name))
        for name in (TRIAGE_FILENAME, VERDICTS_FILENAME)
    )
    meta = json.load(open(os.path.join(report_dir, META_FILENAME), encoding="utf-8"))
    assert meta["triage"] is None
    assert "pytest-triage" not in stdout


def test_a_worker_without_pytest_triage_fails_loudly_not_silently(
    monkeypatch, reports_root, suite
):
    # The flags are spliced onto pytest's command line, so a worker missing the package
    # aborts on an unrecognized argument. Documented, and asserted here so the error stays
    # the obvious one rather than a mysteriously empty archive.
    monkeypatch.setattr(
        archiving_parser,
        "get_current_context",
        lambda: {"ti": FakeTI(dag_id="d", task_id="t", run_id="r")},
    )
    parser = ArchivingResultParser(report_root=reports_root, triage_provider="fake")
    args = list(parser.report_request("/runner/tmp").pytest_args)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:triage",
            "tests",
            *args,
        ],
        cwd=suite,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "unrecognized arguments" in (proc.stderr + proc.stdout)
    assert "--ai-report" in (proc.stderr + proc.stdout)


def test_layout_keeps_the_raw_report_out_of_the_readable_sidecars(
    monkeypatch, reports_root, suite
):
    # pytest-triage writes its report owner-only (0600) because even a redacted traceback
    # may hold residual secrets. That is exactly why the reader never reads it: the api-server
    # may run as another user, and the distilled files carry only the judgement.
    raw, _, report_dir = _archive(
        monkeypatch, reports_root, suite, triage_provider="fake"
    )
    assert raw["mode"] == 0o600, (
        f"pytest-triage changed its permissions: {oct(raw['mode'])}"
    )

    raw_text = raw["text"]
    verdicts_text = open(
        os.path.join(report_dir, VERDICTS_FILENAME), encoding="utf-8"
    ).read()
    assert "Traceback" in raw_text or "assert" in raw_text
    # Nothing captured from the process -- traceback, stdout, logs -- is copied over.
    for leaked in ("traceback", "stdout_tail", "stderr_tail", "log_tail"):
        assert leaked not in verdicts_text
    assert (
        ReportLayout().dir_for(reports_root, ReportRef("shop", "run1", "suite", 1))
        == report_dir
    )
