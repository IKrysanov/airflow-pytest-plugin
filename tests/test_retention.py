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

import json
import os
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
from conftest import write_report, write_tests

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


# -- what the store actually did ---------------------------------------------


def test_prune_does_not_report_space_it_never_freed(reports_root, monkeypatch):
    # A nightly job that logs "deleted 500 runs, freed 3 GB" while a read-only mount kept
    # every file is how a full disk goes unnoticed for weeks. Only confirmed removals are
    # counted; the rest come back named, and loudly.
    from airflow_pytest_plugin.sources import filesystem

    for i in range(4):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    monkeypatch.setattr(
        filesystem.shutil,
        "rmtree",
        lambda *a, **kw: (_ for _ in ()).throw(PermissionError("read-only")),
    )

    result = prune(src, RetentionPolicy(max_runs_per_task=2), now=NOW)

    assert result.deleted == () and result.freed_bytes == 0
    assert result.failed_count == 2
    assert result.to_dict()["failed_count"] == 2
    assert len(src.list_summaries()) == 4  # and every run is still there


def test_prune_keeps_going_when_one_delete_raises(reports_root):
    # One exploding run must not abort the sweep: the rest of the tree still needs pruning
    # tonight, not after someone notices the maintenance DAG has been red for a week.
    for i in range(4):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    real = FileSystemReportSource.delete

    def exploding(self, ref):
        if ref.run_id == "r0":
            raise RuntimeError("storage went away")
        return real(self, ref)

    FileSystemReportSource.delete = exploding
    try:
        result = prune(src, RetentionPolicy(max_runs_per_task=1), now=NOW)
    finally:
        FileSystemReportSource.delete = real

    assert result.deleted_count == 2  # r1 and r2 went
    assert result.failed_count == 1
    assert {s.ref.run_id for s in src.list_summaries()} == {"r0", "r3"}


def test_prune_never_leaves_a_dag_task_without_its_latest_run(reports_root):
    # The one promise the docs make about retention. Checked with every limit at its most
    # aggressive at the same time, which is how a tight config is actually written.
    for dag in ("alpha", "beta"):
        for i in range(5):
            _seed(reports_root, f"r{i}", i + 1, dag=dag)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)

    result = prune(
        src,
        RetentionPolicy(max_age_days=1, max_runs_per_task=1, max_total_bytes=1),
        now=NOW,
    )

    left = {(s.ref.dag_id, s.ref.run_id) for s in src.list_summaries()}
    assert left == {("alpha", "r4"), ("beta", "r4")}
    assert result.deleted_count == 8 and result.failed_count == 0


def test_prune_never_reaches_outside_the_report_root(tmp_path):
    # A run directory can be a symlink -- the archive is written by worker code, which
    # could point one at anything the api-server may delete. The run below is a complete,
    # valid, and the OLDEST one, so if either the scan or the delete ever followed the
    # link, retention would pick it first and wipe the target.
    import os
    import shutil as _shutil

    from airflow_pytest_plugin.layout import ReportLayout

    root = tmp_path / "reports"
    outside = tmp_path / "precious"
    for i in range(3):
        _seed(str(root), f"r{i}", i + 1)
    oldest = ReportLayout().dir_for(str(root), ReportRef("d", "r0", "t", 1))
    _shutil.move(oldest, outside)
    (outside / "keep.txt").write_text("do not delete", encoding="utf-8")
    os.symlink(outside, oldest)

    src = FileSystemReportSource(report_root=str(root), scan_cache_ttl=0)
    listed = {s.ref.run_id for s in src.list_summaries()}
    result = prune(src, RetentionPolicy(max_runs_per_task=1), now=NOW)

    # Not even visible: the tree walk does not descend into a symlinked directory.
    assert "r0" not in listed
    assert result.deleted_count == 1  # r1 went, r2 (newest) stayed
    # ...and the direct route is closed too: the realpath guard refuses the ref outright.
    assert src.delete(ReportRef("d", "r0", "t", 1)) is False
    assert (outside / "keep.txt").exists()
    assert (outside / "meta.json").exists()


def test_prune_survives_a_run_that_vanishes_mid_sweep(reports_root):
    # Between listing and deleting, another prune, an operator, or the viewer may have
    # removed the same run. That is not a failure -- it is the outcome retention wanted.
    for i in range(3):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    entries = src.list_summaries()
    src.delete(next(s.ref for s in entries if s.ref.run_id == "r0"))

    result = prune(src, RetentionPolicy(max_runs_per_task=1), now=NOW)

    # r0 is already gone; r1 goes now; r2 (newest) stays. Nothing is reported as failed
    # that the sweep itself did not have to remove.
    assert {s.ref.run_id for s in src.list_summaries()} == {"r2"}
    assert result.failed_count == 0


def test_size_policy_compensates_when_the_oldest_run_cannot_be_deleted(
    reports_root, monkeypatch
):
    # The size budget is planned assuming every selected run goes. When the OLDEST one is
    # refused, the tree stays over its limit while deletable runs sit right behind it --
    # and the next sweep re-plans around the same stuck run and frees nothing at all,
    # forever. Reproduced: 6 runs, a 3-run budget, the oldest undeletable; the first sweep
    # freed 2 of 3 and every later sweep freed 0.
    import os
    import shutil as _shutil

    from airflow_pytest_plugin.layout import ReportLayout
    from airflow_pytest_plugin.sources import filesystem

    for i in range(6):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    one = src.report_size(ReportRef("d", "r0", "t", 1))
    budget = one * 3

    stuck = ReportLayout().dir_for(reports_root, ReportRef("d", "r0", "t", 1))
    real = _shutil.rmtree

    def refuse_the_oldest(path, *a, **kw):
        if os.path.realpath(path) == os.path.realpath(stuck):
            raise PermissionError("read-only file system")
        return real(path, *a, **kw)

    monkeypatch.setattr(filesystem.shutil, "rmtree", refuse_the_oldest)

    result = prune(src, RetentionPolicy(max_total_bytes=budget), now=NOW)

    on_disk = sum(
        os.path.getsize(os.path.join(base, name))
        for base, _dirs, names in os.walk(reports_root)
        for name in names
    )
    assert on_disk <= budget, f"{on_disk} bytes left against a {budget} budget"
    assert result.failed_count == 1  # and the stuck run is still named
    left = {s.ref.run_id for s in src.list_summaries()}
    assert "r0" in left and "r5" in left  # refused, and the group's newest, both kept


def test_size_policy_stops_when_only_protected_runs_are_left(reports_root, monkeypatch):
    # A refused run bigger than the whole budget can never be compensated for. The sweep
    # must free what it can and stop, not spin re-planning against a target it cannot meet.
    import os
    import shutil as _shutil

    from airflow_pytest_plugin.layout import ReportLayout
    from airflow_pytest_plugin.sources import filesystem

    for i in range(4):
        _seed(reports_root, f"r{i}", i + 1)
    huge = ReportLayout().dir_for(reports_root, ReportRef("d", "r0", "t", 1))
    with open(os.path.join(huge, "junit.xml"), "a", encoding="utf-8") as fh:
        fh.write(" " * 200_000)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    real = _shutil.rmtree
    monkeypatch.setattr(
        filesystem.shutil,
        "rmtree",
        lambda p, *a, **kw: (
            (_ for _ in ()).throw(PermissionError("read-only"))
            if os.path.realpath(p) == os.path.realpath(huge)
            else real(p, *a, **kw)
        ),
    )

    result = prune(src, RetentionPolicy(max_total_bytes=1000), now=NOW)

    # Everything deletable went; the newest of the group and the refused run remain.
    assert {s.ref.run_id for s in src.list_summaries()} == {"r0", "r3"}
    assert result.deleted_count == 2 and result.failed_count == 1


def test_select_expired_counts_skipped_runs_towards_the_budget():
    # A run the store refused is still occupying the disk, so its bytes must keep counting
    # -- dropping them from the total would make the policy think it is already under
    # budget and stop one run too early.
    entries = [_entry(f"r{i}", i + 1, size=100) for i in range(5)]
    policy = RetentionPolicy(max_total_bytes=250)

    without_skip = select_expired(entries, policy, now=NOW)
    with_skip = select_expired(entries, policy, now=NOW, skip={entries[0].ref.token})

    assert entries[0].ref in without_skip  # normally the oldest goes first
    assert entries[0].ref not in with_skip  # skipped: never selected again
    # ...but its 100 bytes still count, so the same amount has to come from elsewhere.
    assert len(with_skip) == len(without_skip)


def test_freed_bytes_is_reported_under_age_and_count_policies_too(reports_root):
    # Sizes are measured up front only when the budget needs them. Without measuring what
    # is about to go, a sweep that deleted 500 runs under an age limit reported "freed 0
    # bytes" -- which reads as a sweep that did nothing.
    for i in range(4):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)

    result = prune(src, RetentionPolicy(max_runs_per_task=1), now=NOW)

    assert result.deleted_count == 3
    assert result.freed_bytes > 0
    assert result.to_dict()["freed_bytes"] == result.freed_bytes


def test_a_run_that_vanished_before_the_sweep_is_not_a_storage_failure(reports_root):
    # Another sweep, an operator or the viewer may remove a run between the listing and the
    # delete. That is the outcome the policy asked for; calling it "storage refused" sends
    # someone to check a disk that is fine, and blocks the run from the plan for nothing.
    import shutil as _shutil

    from airflow_pytest_plugin.layout import ReportLayout

    for i in range(4):
        _seed(reports_root, f"r{i}", i + 1)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    listing = src.list_summaries

    def list_then_remove_the_oldest(*a, **kw):
        out = listing(*a, **kw)
        _shutil.rmtree(
            ReportLayout().dir_for(reports_root, ReportRef("d", "r0", "t", 1)),
            ignore_errors=True,
        )
        return out

    src.list_summaries = list_then_remove_the_oldest  # type: ignore[method-assign]
    result = prune(src, RetentionPolicy(max_runs_per_task=1), now=NOW)

    assert result.failed == ()
    assert result.deleted_count == 3  # including the one that went by itself


def test_a_run_with_an_unparsable_meta_still_counts_and_is_reclaimed(
    reports_root, monkeypatch
):
    # A run the viewer cannot fully read is still bytes on disk. If it dropped out of the
    # listing, the size budget would stop counting it and no sweep would reclaim it: the
    # tree would sit permanently over its limit while every sweep reported success.

    # ``fat`` is the older of the two, so the newest-run-always-kept rule leaves it
    # eligible; a size budget must then reach it like any other run.
    fat = ReportRef("dag", "fat", "task", 1)
    newer = ReportRef("dag", "newer", "task", 1)
    out = write_report(
        reports_root, fat, passed=1, created_at="2026-01-01T00:00:00+00:00"
    )
    write_report(reports_root, newer, passed=1, created_at="2026-01-02T00:00:00+00:00")
    meta_path = os.path.join(out, "meta.json")
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    meta["tests"] = [[f"tests/t.py::test_{i}", "passed", 0.1] for i in range(5000)]
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    monkeypatch.setenv(
        "AIRFLOW_PYTEST_MAX_META_MIB", str((os.path.getsize(meta_path) - 1) / 2**20)
    )

    src = FileSystemReportSource(report_root=reports_root)
    fat_bytes = src.report_size(fat)
    assert fat_bytes > 0

    result = prune(src, RetentionPolicy(max_total_bytes=fat_bytes // 2), dry_run=False)

    assert fat.token in set(result.deleted)
    assert result.freed_bytes >= fat_bytes
    assert not os.path.exists(meta_path)


# -- A number nobody meant ---------------------------------------------------


@pytest.mark.parametrize(
    "days",
    [
        10**21,  # a pasted account number, a typo, a value in seconds
        999_999_999_999,
        10**10,
    ],
)
def test_an_absurd_age_limit_does_not_stop_the_prune(days):
    """`timedelta` refuses a number of days this large, and the prune runs unattended.

    The failure is quiet in the worst way: retention stops running, nothing is deleted,
    and the first anyone hears of it is a full disk. Every other setting in this plugin
    clamps a too-large value to its documented maximum rather than taking it literally
    or failing on it, and this one is no different -- a limit further away than any
    stored run simply keeps everything.
    """
    entries = [_entry("r1", 1), _entry("r2", 2), _entry("r3", 3)]

    picked = select_expired(entries, RetentionPolicy(max_age_days=days), now=NOW)

    assert picked == []


def test_an_absurd_age_limit_from_the_environment_is_clamped(monkeypatch):
    monkeypatch.setenv(config.RETENTION_MAX_AGE_DAYS_ENV, str(10**21))

    policy = RetentionPolicy.from_config()

    assert policy.max_age_days is not None
    assert policy.max_age_days <= config.MAX_RETENTION_DAYS
    # And it still prunes by that dimension rather than switching the limit off.
    assert policy.is_active


def test_an_absurd_age_limit_still_deletes_what_is_older_than_it(monkeypatch):
    """Clamping must not turn "keep for ages" into "delete everything"."""
    monkeypatch.setenv(config.RETENTION_MAX_AGE_DAYS_ENV, str(10**21))
    policy = RetentionPolicy.from_config()

    # Older than the clamp itself (100 years), so the dimension is provably still live.
    ancient = RunEntry(
        ReportRef("d", "ancient", "t", 1), "1900-01-01T00:00:00+00:00", 0
    )
    entries = [_entry("r1", 1), ancient]

    picked = select_expired(entries, policy, now=NOW)

    assert [ref.run_id for ref in picked] == ["ancient"]
