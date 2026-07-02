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

"""Tests for the alerting layer: pure classification + HTML rendering with plain data, the
gather/orchestrator against a real temp filesystem source + a spy mailer, config, transport."""

from __future__ import annotations

import json
import os

import pytest

from airflow_pytest_plugin.layout import META_FILENAME, ReportLayout
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.notifications import (
    Alert,
    AlertPolicy,
    RunFact,
    SmtpConfig,
    build_mailer,
    build_run_alert,
    build_run_email,
    classify,
    evaluate_alerts,
    failed_nodes_for,
    flaky_nodes_for,
    notify_after_archive,
    notify_for_run,
    pass_rate_pct,
    run_is_failing,
)
from airflow_pytest_plugin.sources import FileSystemReportSource

_WHEN = "2026-06-01T00:00:00+00:00"
_ACTIVE = AlertPolicy(recipients=("team@example.com",))


# --- helpers -----------------------------------------------------------------------------------
def _fact(
    run="r0",
    *,
    total=10,
    passed=10,
    failed=0,
    errors=0,
    skipped=0,
    dag="dag",
    task="suite",
) -> RunFact:
    return RunFact(
        ref=ReportRef(dag, run, task, 1, -1),
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
    )


def _write_run(root, dag, task, run, rows, when) -> None:
    """Write a full meta (summary counts from ``rows`` + a per-test outcomes map)."""
    ref = ReportRef(dag, run, task, 1, -1)
    out = ReportLayout().dir_for(root, ref)
    os.makedirs(out, exist_ok=True)
    p = sum(1 for _, o in rows if o == "passed")
    f = sum(1 for _, o in rows if o == "failed")
    e = sum(1 for _, o in rows if o == "error")
    sk = sum(1 for _, o in rows if o == "skipped")
    meta = {
        "schema_version": 1,
        "dag_id": dag,
        "run_id": run,
        "task_id": task,
        "try_number": 1,
        "map_index": -1,
        "logical_date": when,
        "created_at": when,
        "report_file": "junit.xml",
        "summary": {
            "total": len(rows),
            "passed": p,
            "failed": f,
            "errors": e,
            "skipped": sk,
            "duration": 0.1 * len(rows),
            "success": (f + e) == 0,
        },
        "tests": [[node, o, 0.1] for node, o in rows],
    }
    with open(os.path.join(out, META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)


class SpyMailer:
    def __init__(self) -> None:
        self.sends: list[dict] = []

    def send(self, *, subject, body, recipients, html=None) -> None:
        self.sends.append(
            {
                "subject": subject,
                "body": body,
                "html": html,
                "recipients": list(recipients),
            }
        )


class BoomMailer:
    def send(self, *, subject, body, recipients, html=None) -> None:
        raise RuntimeError("smtp down")


# --- pure: pass rate + failing bar -------------------------------------------------------------
def test_pass_rate_pct_over_executed_tests():
    assert pass_rate_pct(_fact(total=10, passed=8, failed=2)) == 80
    assert pass_rate_pct(_fact(total=10, passed=8, skipped=2)) == 100  # skipped ignored
    assert pass_rate_pct(_fact(total=0, passed=0)) == 100


def test_run_is_failing_honours_float_threshold():
    strict = AlertPolicy(success_threshold=0.9)
    assert run_is_failing(_fact(total=10, passed=8, failed=2), strict)  # 80% < 90%
    assert not run_is_failing(_fact(total=10, passed=9, failed=1), strict)  # 90% == 90%


def test_classify_passed_flaky_failed():
    assert classify(_fact(passed=10), _ACTIVE, has_flaky=False) == "passed"
    assert classify(_fact(passed=10), _ACTIVE, has_flaky=True) == "flaky"
    assert (
        classify(_fact(total=10, passed=4, failed=6), _ACTIVE, has_flaky=True)
        == "failed"
    )
    # failing beats flaky


# --- pure: HTML rendering ----------------------------------------------------------------------
def test_build_run_email_failed_variant():
    run = _fact(total=25, passed=22, failed=2, errors=1, dag="etl", task="unit")
    a = build_run_email(
        run, "failed", failures=["tests/x.py::test_a"], base_url="http://af"
    )
    assert a.kind == "failed"
    assert "Failed" in a.subject and "88% pass" in a.subject
    assert "#dc2626" in a.html  # red banner
    assert "Failed tests" in a.html and "tests/x.py::test_a" in a.html
    assert "open in Airflow" in a.html and "http://af/dags/etl/" in a.html
    assert "22 passed, 2 failed, 1 errors, 0 skipped of 25" in a.body


def test_build_run_email_passed_and_flaky_variants():
    passed = build_run_email(_fact(passed=10), "passed")
    assert (
        passed.kind == "passed"
        and "#16a34a" in passed.html
        and "Passed" in passed.subject
    )
    flaky = build_run_email(_fact(passed=10), "flaky", flaky=["tests/f.py::test_x"])
    assert flaky.kind == "flaky" and "#b45309" in flaky.html
    assert "Flaky tests" in flaky.html and "tests/f.py::test_x" in flaky.html


def test_build_run_email_escapes_hostile_node_ids():
    # A hostile test id / dag must render as inert text, never as live markup.
    run = _fact(dag="dag<script>", passed=0, failed=1, total=1)
    a = build_run_email(
        run, "failed", failures=["tests/x.py::test_<script>alert(1)</script>"]
    )
    assert "<script>" not in a.html
    assert "&lt;script&gt;" in a.html


def test_build_run_email_caps_long_lists():
    many = [f"tests/x.py::test_{i:03d}" for i in range(30)]
    a = build_run_email(_fact(total=30, passed=0, failed=30), "failed", failures=many)
    assert "+18 more" in a.html and "+18 more" in a.body  # 30 - 12 listed


# --- pure: evaluate_alerts ---------------------------------------------------------------------
def test_evaluate_alerts_silent_on_clean_pass_without_always():
    assert evaluate_alerts(_fact(passed=10), _ACTIVE) == []


def test_evaluate_alerts_emits_on_failed_or_flaky():
    assert [
        a.kind for a in evaluate_alerts(_fact(total=10, passed=1, failed=9), _ACTIVE)
    ] == ["failed"]
    assert [
        a.kind for a in evaluate_alerts(_fact(passed=10), _ACTIVE, flaky=["n"])
    ] == ["flaky"]


def test_evaluate_alerts_always_emits_passed_summary():
    assert [
        a.kind for a in evaluate_alerts(_fact(passed=10), _ACTIVE, always=True)
    ] == ["passed"]


def test_alert_to_dict_roundtrip():
    a = Alert("failed", "dag", "task", "subj", "body", "<b>html</b>")
    assert a.to_dict() == {
        "kind": "failed",
        "dag_id": "dag",
        "task_id": "task",
        "subject": "subj",
        "body": "body",
        "html": "<b>html</b>",
    }


# --- config ------------------------------------------------------------------------------------
def test_policy_from_config_reads_env(monkeypatch):
    monkeypatch.setenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", "a@x.io, b@x.io ; c@x.io")
    monkeypatch.setenv("AIRFLOW_PYTEST_SUCCESS_THRESHOLD", "0.9")
    p = AlertPolicy.from_config()
    assert p.is_active and p.recipients == ("a@x.io", "b@x.io", "c@x.io")
    assert p.success_threshold == 0.9


def test_policy_inactive_without_recipients(monkeypatch):
    monkeypatch.delenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", raising=False)
    assert AlertPolicy.from_config().is_active is False


def test_smtp_config_from_env_and_unset(monkeypatch):
    for var in ("HOST", "PORT", "USER", "PASSWORD", "FROM", "STARTTLS"):
        monkeypatch.delenv(f"AIRFLOW_PYTEST_SMTP_{var}", raising=False)
    assert SmtpConfig.from_config() is None
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_PORT", "587")
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_STARTTLS", "false")
    cfg = SmtpConfig.from_config()
    assert (
        cfg
        and cfg.host == "smtp.example.com"
        and cfg.port == 587
        and cfg.starttls is False
    )


# --- gather (temp fs) --------------------------------------------------------------------------
def test_failed_nodes_for_lists_failures(reports_root):
    _write_run(
        reports_root,
        "dag",
        "suite",
        "r0",
        [("a", "passed"), ("b", "failed"), ("c", "error")],
        _WHEN,
    )
    src = FileSystemReportSource(report_root=reports_root)
    assert failed_nodes_for(src, ReportRef("dag", "r0", "suite", 1, -1)) == ("b", "c")


def test_flaky_nodes_for_detects_flips(reports_root):
    for i, o in enumerate(["passed", "failed", "passed", "failed"]):
        _write_run(
            reports_root,
            "dag",
            "suite",
            f"r{i}",
            [("t", o)],
            f"2026-06-01T0{i}:00:00+00:00",
        )
    src = FileSystemReportSource(report_root=reports_root)
    assert "t" in flaky_nodes_for(src, "dag", "suite", window=30, min_score=0.0)


def test_flaky_nodes_for_isolated_per_dag_task(reports_root):
    # Flips in ANOTHER task -- and in a dag whose id merely CONTAINS ours ("dag" vs "dag2",
    # list_summaries filters by substring) -- must not mark THIS dag·task flaky.
    for i, o in enumerate(["passed", "failed", "passed", "failed"]):
        when = f"2026-06-01T0{i}:00:00+00:00"
        _write_run(reports_root, "dag", "other_task", f"r{i}", [("t", o)], when)
        _write_run(reports_root, "dag2", "suite", f"r{i}", [("t", o)], when)
        _write_run(reports_root, "dag", "suite", f"r{i}", [("t", "passed")], when)
    src = FileSystemReportSource(report_root=reports_root)
    assert flaky_nodes_for(src, "dag", "suite", window=30, min_score=0.0) == ()


# --- build_run_alert (temp fs) -----------------------------------------------------------------
def test_build_run_alert_failed(reports_root):
    _write_run(
        reports_root,
        "dag",
        "suite",
        "r0",
        [("a", "passed"), ("b", "failed"), ("c", "failed")],
        _WHEN,
    )
    src = FileSystemReportSource(report_root=reports_root)
    a = build_run_alert(src, ReportRef("dag", "r0", "suite", 1, -1), _ACTIVE)
    assert a and a.kind == "failed" and "b" in a.html and "c" in a.html


def test_build_run_alert_flaky(reports_root):
    # A node flips across the window but the LATEST run passes -> flaky (not failed, not silent).
    for i, o in enumerate(["passed", "failed", "passed"]):
        _write_run(
            reports_root,
            "dag",
            "suite",
            f"r{i}",
            [("t", o)],
            f"2026-06-01T0{i}:00:00+00:00",
        )
    src = FileSystemReportSource(report_root=reports_root)
    a = build_run_alert(src, ReportRef("dag", "r2", "suite", 1, -1), _ACTIVE)
    assert a and a.kind == "flaky" and "t" in a.html


def test_build_run_alert_clean_pass_is_none_without_always(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("a", "passed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root)
    ref = ReportRef("dag", "r0", "suite", 1, -1)
    assert build_run_alert(src, ref, _ACTIVE) is None  # auto: nothing on a clean pass
    assert (
        build_run_alert(src, ref, _ACTIVE, always=True).kind == "passed"
    )  # manual: green


def test_build_run_alert_missing_run_is_none(reports_root):
    src = FileSystemReportSource(report_root=reports_root)
    assert (
        build_run_alert(
            src, ReportRef("dag", "nope", "suite", 1, -1), _ACTIVE, always=True
        )
        is None
    )


# --- orchestrator ------------------------------------------------------------------------------
def test_notify_for_run_sends_on_failure(reports_root):
    _write_run(
        reports_root,
        "dag",
        "suite",
        "r0",
        [("a", "passed"), ("b", "failed"), ("c", "failed")],
        _WHEN,
    )
    src = FileSystemReportSource(report_root=reports_root)
    spy = SpyMailer()
    out = notify_for_run(
        src, ReportRef("dag", "r0", "suite", 1, -1), policy=_ACTIVE, mailer=spy
    )
    assert [a.kind for a in out] == ["failed"]
    assert spy.sends[0]["recipients"] == ["team@example.com"]
    assert spy.sends[0]["html"] and "#dc2626" in spy.sends[0]["html"]  # HTML delivered


def test_notify_for_run_silent_on_clean_pass(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("a", "passed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root)
    spy = SpyMailer()
    assert (
        notify_for_run(
            src, ReportRef("dag", "r0", "suite", 1, -1), policy=_ACTIVE, mailer=spy
        )
        == []
    )
    assert spy.sends == []


def test_notify_for_run_always_sends_passed(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("a", "passed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root)
    spy = SpyMailer()
    out = notify_for_run(
        src,
        ReportRef("dag", "r0", "suite", 1, -1),
        policy=_ACTIVE,
        mailer=spy,
        always=True,
    )
    assert [a.kind for a in out] == ["passed"] and len(spy.sends) == 1


def test_notify_for_run_dry_run_sends_nothing(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root)
    spy = SpyMailer()
    out = notify_for_run(
        src,
        ReportRef("dag", "r0", "suite", 1, -1),
        policy=_ACTIVE,
        mailer=spy,
        dry_run=True,
    )
    assert out and spy.sends == []


def test_notify_for_run_swallows_send_failure(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root)
    out = notify_for_run(
        src, ReportRef("dag", "r0", "suite", 1, -1), policy=_ACTIVE, mailer=BoomMailer()
    )
    assert [a.kind for a in out] == ["failed"]  # raised internally, not propagated


def test_notify_for_run_no_recipients_is_noop(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root)
    spy = SpyMailer()
    assert (
        notify_for_run(
            src,
            ReportRef("dag", "r0", "suite", 1, -1),
            policy=AlertPolicy(),
            mailer=spy,
        )
        == []
    )
    assert spy.sends == []


def test_notify_after_archive_inactive_needs_no_source(monkeypatch):
    monkeypatch.delenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", raising=False)
    assert notify_after_archive(ReportRef("dag", "r", "t", 1, -1)) == []


def test_notify_after_archive_failure(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    out = notify_after_archive(
        ReportRef("dag", "r0", "suite", 1, -1),
        source=FileSystemReportSource(report_root=reports_root),
        policy=_ACTIVE,
    )
    assert [a.kind for a in out] == ["failed"]


def test_notify_after_archive_always_sends_passed(reports_root):
    # email=True -> always=True: a clean pass still gets a "run finished" completion email.
    _write_run(reports_root, "dag", "suite", "r0", [("a", "passed")], _WHEN)
    out = notify_after_archive(
        ReportRef("dag", "r0", "suite", 1, -1),
        source=FileSystemReportSource(report_root=reports_root),
        policy=_ACTIVE,
        always=True,
    )
    assert [a.kind for a in out] == ["passed"]


# --- transport ---------------------------------------------------------------------------------
def test_smtp_mailer_sends_multipart_text_and_html(monkeypatch):
    from airflow_pytest_plugin import notifications as notif

    seen: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            seen["addr"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            seen["starttls"] = True

        def login(self, user, password):
            seen["login"] = (user, password)

        def send_message(self, msg):
            seen["msg"] = msg

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    cfg = notif.SmtpConfig(
        host="mail", port=2525, user="u", password="p", starttls=True
    )
    notif.SmtpMailer(cfg).send(
        subject="subj", body="plain", html="<b>rich</b>", recipients=["a@b.c", "d@e.f"]
    )
    assert (
        seen["addr"] == ("mail", 2525)
        and seen["starttls"]
        and seen["login"] == ("u", "p")
    )
    msg = seen["msg"]
    assert msg["To"] == "a@b.c, d@e.f" and msg.is_multipart()
    types = {p.get_content_type() for p in msg.walk()}
    assert "text/plain" in types and "text/html" in types


def test_smtp_mailer_strips_header_injection(monkeypatch):
    from airflow_pytest_plugin import notifications as notif

    seen: dict = {}

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send_message(self, msg):
            seen["msg"] = msg

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    notif.SmtpMailer(notif.SmtpConfig(host="mail", starttls=False)).send(
        subject="[pytest] x\r\nBcc: evil@example.com", body="b", recipients=["a@b.c"]
    )
    subj = str(seen["msg"]["Subject"])
    assert "\n" not in subj and "\r" not in subj and seen["msg"]["Bcc"] is None


def test_build_mailer_prefers_explicit_smtp(monkeypatch):
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_HOST", "smtp.example.com")
    from airflow_pytest_plugin.notifications import SmtpMailer

    assert isinstance(build_mailer(), SmtpMailer)  # wins even if Airflow is importable


def test_build_mailer_none_when_no_transport(monkeypatch):
    try:
        import airflow.utils.email  # noqa: F401

        pytest.skip("Airflow present -> a transport always exists")
    except Exception:
        pass
    for var in ("HOST", "PORT", "USER", "PASSWORD", "FROM", "STARTTLS"):
        monkeypatch.delenv(f"AIRFLOW_PYTEST_SMTP_{var}", raising=False)
    assert build_mailer() is None


# --- load ---------------------------------------------------------------------------------------
def test_alerting_is_bounded_on_a_large_history(reports_root):
    # A dag·task with a long history: building an alert must stay cheap -- the flaky scan is
    # window-bounded (reads ~30 runs, not all 400), so it can't walk the whole archive per run.
    import time

    for i in range(400):
        oc = "failed" if i == 399 else "passed"
        when = f"2026-06-01T00:{i // 60:02d}:{i % 60:02d}+00:00"
        _write_run(reports_root, "dag", "suite", f"r{i:04d}", [("t", oc)], when)
    src = FileSystemReportSource(report_root=reports_root)
    t0 = time.perf_counter()
    flaky_nodes_for(src, "dag", "suite", window=30, min_score=0.0)
    alert = build_run_alert(src, ReportRef("dag", "r0399", "suite", 1, -1), _ACTIVE)
    elapsed = time.perf_counter() - t0
    assert alert and alert.kind == "failed"
    assert elapsed < 3.0, (
        f"alerting on 400 runs took {elapsed:.2f}s (should be window-bounded)"
    )


# --- producer hook -----------------------------------------------------------------------------
def test_parser_email_true_notifies(monkeypatch, reports_root):
    from airflow_pytest_plugin import notifications
    from airflow_pytest_plugin.producer import ArchivingResultParser

    calls: list = []
    monkeypatch.setattr(
        notifications, "notify_after_archive", lambda ref, **kw: calls.append(kw)
    )
    parser = ArchivingResultParser(report_root=reports_root, email=True)
    parser._pending_ref = ReportRef("dag", "run1", "task", 1, -1)
    parser._maybe_notify()
    assert (
        len(calls) == 1 and calls[0]["always"] is True
    )  # email=True notifies EVERY run


def test_parser_email_false_is_silent(monkeypatch, reports_root):
    # The ping-spam guard: email=False (default) never calls the notifier at all.
    from airflow_pytest_plugin import notifications
    from airflow_pytest_plugin.producer import ArchivingResultParser

    calls: list = []
    monkeypatch.setattr(
        notifications, "notify_after_archive", lambda ref, **kw: calls.append(kw)
    )
    parser = ArchivingResultParser(report_root=reports_root)  # email defaults False
    parser._pending_ref = ReportRef("dag", "run1", "task", 1, -1)
    parser._maybe_notify()
    assert calls == []
