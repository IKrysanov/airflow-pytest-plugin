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

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airflow_pytest_plugin import config
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.retention import (
    RetentionPolicy,
    RunEntry,
    prune,
    prune_reports,
    select_expired,
)
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import write_tests

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _entry(
    run: str, day: int, *, dag: str = "d", task: str = "t", size: int = 0
) -> RunEntry:
    return RunEntry(
        ReportRef(dag, run, task, 1), f"2026-06-{day:02d}T00:00:00+00:00", size
    )


# -- RetentionPolicy ---------------------------------------------------------


def test_policy_inactive_by_default():
    pol = RetentionPolicy()
    assert pol.is_active is False and pol.needs_sizes is False


def test_policy_is_active_and_needs_sizes():
    assert RetentionPolicy(max_runs_per_task=5).is_active is True
    assert RetentionPolicy(max_total_bytes=1).needs_sizes is True
    assert RetentionPolicy(max_age_days=7).needs_sizes is False


def test_policy_from_config_inactive_when_unset(monkeypatch):
    for env in (
        config.RETENTION_MAX_AGE_DAYS_ENV,
        config.RETENTION_MAX_RUNS_ENV,
        config.RETENTION_MAX_TOTAL_MB_ENV,
    ):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert RetentionPolicy.from_config().is_active is False


def test_policy_from_config_reads_env(monkeypatch):
    monkeypatch.setenv(config.RETENTION_MAX_AGE_DAYS_ENV, "30")
    monkeypatch.setenv(config.RETENTION_MAX_RUNS_ENV, "10")
    monkeypatch.setenv(config.RETENTION_MAX_TOTAL_MB_ENV, "5")
    pol = RetentionPolicy.from_config()
    assert pol.max_age_days == 30 and pol.max_runs_per_task == 10
    assert pol.max_total_bytes == 5 * 1024 * 1024  # MB -> bytes


def test_policy_from_config_ignores_non_positive(monkeypatch):
    monkeypatch.setenv(config.RETENTION_MAX_RUNS_ENV, "0")
    monkeypatch.setenv(config.RETENTION_MAX_AGE_DAYS_ENV, "-3")
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert RetentionPolicy.from_config().is_active is False


def test_policy_rejects_non_positive_limits():
    # Direct construction with a non-positive limit would break keep-newest -> reject.
    for kwargs in (
        {"max_runs_per_task": 0},
        {"max_age_days": -1},
        {"max_total_bytes": 0},
    ):
        with pytest.raises(ValueError):
            RetentionPolicy(**kwargs)


# -- select_expired (pure) ---------------------------------------------------


def test_select_inactive_policy_keeps_all():
    entries = [_entry(f"r{i}", i + 1) for i in range(5)]
    assert select_expired(entries, RetentionPolicy(), now=NOW) == []


def test_select_count_keeps_newest_n_per_task():
    entries = [_entry(f"r{i}", i + 1) for i in range(5)]  # r0 oldest .. r4 newest
    dead = select_expired(entries, RetentionPolicy(max_runs_per_task=2), now=NOW)
    assert sorted(r.run_id for r in dead) == ["r0", "r1", "r2"]  # keep r3, r4


def test_select_count_keeps_all_when_under_limit():
    entries = [_entry(f"r{i}", i + 1) for i in range(3)]
    assert select_expired(entries, RetentionPolicy(max_runs_per_task=10), now=NOW) == []


def test_select_count_is_per_dag_task():
    entries = [
        _entry("a0", 1, task="alpha"),
        _entry("a1", 2, task="alpha"),
        _entry("b0", 1, task="beta"),
        _entry("b1", 2, task="beta"),
    ]
    dead = select_expired(entries, RetentionPolicy(max_runs_per_task=1), now=NOW)
    # newest of each task survives; the older of each goes
    assert sorted(r.run_id for r in dead) == ["a0", "b0"]


def test_select_age_deletes_old_but_keeps_group_newest():
    # all three runs predate the cutoff, yet the newest must survive
    entries = [_entry("r0", 1), _entry("r1", 2), _entry("r2", 3)]
    dead = select_expired(entries, RetentionPolicy(max_age_days=1), now=NOW)
    assert sorted(r.run_id for r in dead) == ["r0", "r1"]  # r2 (newest) kept


def test_select_age_keeps_recent_runs():
    entries = [_entry("old", 1), _entry("new", 25)]  # NOW = Jul 1
    dead = select_expired(entries, RetentionPolicy(max_age_days=30), now=NOW)
    assert dead == []  # both within 30 days, newest protected anyway


def test_select_age_ignores_undateable():
    entries = [
        RunEntry(ReportRef("d", "r0", "t", 1), None),  # no timestamp
        _entry("r1", 2),
    ]
    dead = select_expired(entries, RetentionPolicy(max_age_days=1), now=NOW)
    assert dead == []  # r1 is the newest (kept); r0 undateable (not aged out)


def test_select_size_trims_oldest_until_under_budget():
    # five 100-byte runs (500 total); budget 250 -> delete oldest until <= 250
    entries = [_entry(f"r{i}", i + 1, size=100) for i in range(5)]
    dead = select_expired(entries, RetentionPolicy(max_total_bytes=250), now=NOW)
    assert sorted(r.run_id for r in dead) == ["r0", "r1", "r2"]  # 500->200, keep r3,r4


def test_select_size_never_deletes_group_newest():
    # tiny budget, but each task's newest is protected even if still over budget
    entries = [
        _entry("a0", 1, task="alpha", size=100),
        _entry("a1", 2, task="alpha", size=100),
        _entry("b0", 1, task="beta", size=100),
    ]
    dead = select_expired(entries, RetentionPolicy(max_total_bytes=1), now=NOW)
    assert sorted(r.run_id for r in dead) == ["a0"]  # only non-newest candidate


def test_select_size_under_budget_keeps_all():
    entries = [_entry(f"r{i}", i + 1, size=10) for i in range(3)]  # 30 bytes total
    assert select_expired(entries, RetentionPolicy(max_total_bytes=1000), now=NOW) == []


def test_select_size_keeps_newest_even_when_over_budget():
    # one run per task -> all are the group newest -> nothing deletable, even over budget
    entries = [
        _entry("a0", 1, task="alpha", size=100),
        _entry("b0", 1, task="beta", size=100),
    ]
    assert select_expired(entries, RetentionPolicy(max_total_bytes=1), now=NOW) == []


def test_select_unions_count_and_age():
    entries = [_entry(f"r{i}", i + 1) for i in range(4)]  # r0..r3
    pol = RetentionPolicy(max_runs_per_task=3, max_age_days=1)
    dead = select_expired(entries, pol, now=NOW)
    # count drops r0 (keep newest 3); age drops r0,r1,r2 (all old, keep newest r3)
    assert sorted(r.run_id for r in dead) == ["r0", "r1", "r2"]


# -- prune (orchestrator, real filesystem) -----------------------------------


def _seed(root, run, day, *, dag="d", task="t"):
    write_tests(
        root,
        ReportRef(dag, run, task, 1),
        [["a", "passed"]],
        created_at=f"2026-06-{day:02d}T00:00:00+00:00",
    )


def test_prune_deletes_old_runs_on_disk(reports_root):
    for i in range(4):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    result = prune(src, RetentionPolicy(max_runs_per_task=2), now=NOW)
    assert result.deleted_count == 2 and result.dry_run is False
    remaining = {s.ref.run_id for s in src.list_summaries()}
    assert remaining == {"r2", "r3"}  # newest two survive


def test_prune_dry_run_deletes_nothing(reports_root):
    for i in range(3):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    result = prune(src, RetentionPolicy(max_runs_per_task=1), now=NOW, dry_run=True)
    assert result.dry_run is True and result.deleted_count == 2
    assert len(src.list_summaries()) == 3  # nothing actually removed


def test_prune_inactive_policy_is_noop(reports_root):
    _seed(reports_root, "r0", 1)
    src = FileSystemReportSource(report_root=reports_root)
    result = prune(src, RetentionPolicy(), now=NOW)
    assert result.deleted_count == 0 and result.scanned == 0
    assert len(src.list_summaries()) == 1


def test_prune_size_policy_measures_and_frees(reports_root):
    for i in range(3):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    one = src.report_size(ReportRef("d", "r0", "t", 1))
    assert one > 0  # report_size sums real bytes
    # budget below the smallest run -> trim all non-newest, keep the newest
    result = prune(src, RetentionPolicy(max_total_bytes=one // 2), now=NOW)
    assert result.freed_bytes > 0
    assert {s.ref.run_id for s in src.list_summaries()} == {"r2"}


def test_prune_reports_entry_point_uses_given_source(reports_root):
    for i in range(3):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    result = prune_reports(RetentionPolicy(max_runs_per_task=1), source=src, now=NOW)
    assert result.deleted_count == 2
    assert {s.ref.run_id for s in src.list_summaries()} == {"r2"}


def test_select_age_ignores_malformed_timestamp():
    entries = [
        RunEntry(
            ReportRef("d", "r0", "t", 1), "0bad-timestamp"
        ),  # sorts oldest, unparseable
        _entry("r1", 25),  # newest, protected
    ]
    # r1 is the newest (kept); r0's timestamp can't be parsed -> not aged out.
    assert select_expired(entries, RetentionPolicy(max_age_days=1), now=NOW) == []


def test_select_size_skips_marked_and_stops_at_budget():
    # count marks the oldest; the size pass must skip it (continue) and stop (break).
    entries = [_entry(f"r{i}", i + 1, size=100) for i in range(4)]  # 400 total
    pol = RetentionPolicy(max_runs_per_task=3, max_total_bytes=250)
    dead = select_expired(entries, pol, now=NOW)
    # count -> r0; size: 300 > 250 -> drop r1 (200) -> 200 <= 250 stop
    assert sorted(r.run_id for r in dead) == ["r0", "r1"]


def test_result_to_dict_round_trips(reports_root):
    _seed(reports_root, "r0", 1)
    _seed(reports_root, "r1", 2)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    d = prune(src, RetentionPolicy(max_runs_per_task=1), now=NOW).to_dict()
    assert d["deleted_count"] == 1 and d["dry_run"] is False and len(d["deleted"]) == 1


def test_prune_reports_default_source_inactive_is_noop(monkeypatch):
    # No source -> builds the default FileSystemReportSource; inactive policy -> no scan.
    for env in (
        config.RETENTION_MAX_AGE_DAYS_ENV,
        config.RETENTION_MAX_RUNS_ENV,
        config.RETENTION_MAX_TOTAL_MB_ENV,
    ):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    result = prune_reports(now=NOW)
    assert result.deleted_count == 0 and result.scanned == 0
