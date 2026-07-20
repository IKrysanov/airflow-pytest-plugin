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
import logging
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
from conftest import write_allure

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
    # A minimal matching junit.xml so ``get_detail`` (which requires it) also works.
    cases = []
    for node, o in rows:
        cls, _, name = node.partition("::")
        body = {
            "failed": "<failure/>",
            "error": "<error/>",
            "skipped": "<skipped/>",
        }.get(o, "")
        cases.append(
            f'<testcase classname="{cls}" name="{name or node}" time="0.1">{body}</testcase>'
        )
    xml = (
        f'<testsuites><testsuite name="pytest" tests="{len(rows)}" failures="{f}" '
        f'errors="{e}" skipped="{sk}" time="1.0">{"".join(cases)}</testsuite></testsuites>'
    )
    with open(os.path.join(out, "junit.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)


class SpyMailer:
    def __init__(self) -> None:
        self.sends: list[dict] = []

    def send(self, *, subject, body, recipients, html=None, attachments=()) -> None:
        self.sends.append(
            {
                "subject": subject,
                "body": body,
                "html": html,
                "recipients": list(recipients),
                "attachments": [(n, len(p)) for n, p in attachments],
            }
        )


class BoomMailer:
    def send(self, *, subject, body, recipients, html=None, attachments=()) -> None:
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


# --- recipients: validation + dedupe -----------------------------------------------------------
def test_is_valid_email_accepts_ordinary_addresses():
    from airflow_pytest_plugin.notifications import is_valid_email

    for addr in (
        "a@x.io",
        "first.last@example.com",
        "user+tag@sub.domain.co.uk",
        "UPPER.case@Example.COM",
        "num123@x9.dev",
    ):
        assert is_valid_email(addr), addr


def test_is_valid_email_rejects_garbage_and_abuse():
    from airflow_pytest_plugin.notifications import is_valid_email

    for addr in (
        "",
        "no-at",
        "a@b",  # no TLD
        "a b@x.io",  # space
        "a@x.io\nBcc: evil@x.io",  # header injection
        "a@x\x00.io",  # control char
        ".dot@x.io",  # leading dot in local part
        "dot.@x.io",  # trailing dot
        "do..t@x.io",  # consecutive dots
        "a@-bad.com",  # label starts with hyphen
        "a@bad-.com",  # label ends with hyphen
        "a@x..io",  # empty domain label
        "x" * 65 + "@x.io",  # local part > 64
        "a@" + "x" * 250 + ".io",  # total > 254
        # TLD must be alphabetic and 2-63 chars: an IP-literal-ish or digit TLD would
        # otherwise sail through into a mail header.
        "a@x.123",  # numeric TLD
        "a@x.i",  # TLD too short
        "a@x." + "t" * 64,  # TLD too long
        "a@x.i-o",  # hyphen in TLD
        "a@127.0.0.1",  # bare IP, no alphabetic TLD
    ):
        assert not is_valid_email(addr), addr


def test_env_recipients_deduped_and_invalid_dropped(monkeypatch):
    # Duplicates (case-insensitive) collapse to one send; invalid entries are dropped
    # (logged) instead of poisoning every send.
    monkeypatch.setenv(
        "AIRFLOW_PYTEST_ALERTS_EMAIL_TO",
        "team@x.io, TEAM@X.IO; not-an-email, b@x.io, team@x.io",
    )
    p = AlertPolicy.from_config()
    assert p.recipients == ("team@x.io", "b@x.io")


def test_duplicate_env_recipients_mail_once(reports_root, monkeypatch):
    # The same address twice in the env -> the email goes out with ONE copy of it.
    monkeypatch.setenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", "team@x.io, team@x.io")
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    spy = SpyMailer()
    notify_for_run(
        src,
        ReportRef("dag", "r0", "suite", 1, -1),
        policy=AlertPolicy.from_config(),
        mailer=spy,
    )
    assert spy.sends[0]["recipients"] == ["team@x.io"]


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


def test_notify_after_archive_warns_when_email_requested_but_no_recipients(
    monkeypatch, caplog
):
    # email=True path reaches the orchestrator, but no recipients configured -> warn once
    # (instead of the old silent no-op) so the misconfiguration is visible.
    monkeypatch.delenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", raising=False)
    with caplog.at_level(logging.WARNING):
        out = notify_after_archive(ReportRef("dag", "suite", "t", 1, -1))
    assert out == []
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("no recipients are configured" in m for m in warnings)


def test_notify_after_archive_no_recipient_warning_when_configured(
    reports_root, caplog
):
    # With recipients present the misconfiguration warning must NOT fire.
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    with caplog.at_level(logging.WARNING):
        notify_after_archive(
            ReportRef("dag", "r0", "suite", 1, -1),
            source=FileSystemReportSource(report_root=reports_root),
            policy=_ACTIVE,
        )
    assert not any(
        "no recipients are configured" in r.getMessage() for r in caplog.records
    )


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


def test_smtp_mailer_delivers_attachment_as_zip_part(monkeypatch):
    # The Allure zip must actually ride along on the real transport (the spy-based tests
    # only prove the orchestrator hands it over), as a separate application/zip part with
    # the filename basename-d so a crafted name can't smuggle a path.
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
        subject="subj",
        body="plain",
        html="<b>rich</b>",
        recipients=["a@b.c"],
        attachments=[("../../evil/allure-results.zip", b"PK\x03\x04payload")],
    )
    parts = {p.get_content_type(): p for p in seen["msg"].walk()}
    assert "application/zip" in parts
    zip_part = parts["application/zip"]
    assert zip_part.get_filename() == "allure-results.zip"  # path stripped
    assert zip_part.get_payload(decode=True) == b"PK\x03\x04payload"


def test_record_sent_alert_swallows_source_failure(reports_root):
    # The send already happened -- a failing history write must never turn into an error
    # for the caller (it is informational only).
    from airflow_pytest_plugin.notifications import record_sent_alert

    class BoomSource:
        def record_alert(self, ref, entry):
            raise OSError("read-only filesystem")

    alert = Alert("failed", "dag", "suite", "subj", "body", "<b>html</b>")
    record_sent_alert(
        BoomSource(),
        ReportRef("dag", "r0", "suite", 1, -1),
        alert,
        ["a@b.c"],
        ok=True,
        manual=False,
    )  # must not raise


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


# --- alert history (meta.json) + allure attachment ---------------------------------------------
def test_notify_records_history_in_meta(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    ref = ReportRef("dag", "r0", "suite", 1, -1)
    notify_for_run(src, ref, policy=_ACTIVE, mailer=SpyMailer())
    alerts = src.get_detail(ref).alerts
    assert len(alerts) == 1
    entry = alerts[0]
    assert entry["ok"] is True and entry["manual"] is False
    assert entry["kind"] == "failed"
    assert entry["recipients"] == ["team@example.com"]
    assert entry["at"]  # ISO timestamp present


def test_notify_records_failed_send_too(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    ref = ReportRef("dag", "r0", "suite", 1, -1)
    notify_for_run(src, ref, policy=_ACTIVE, mailer=BoomMailer())
    alerts = src.get_detail(ref).alerts
    assert len(alerts) == 1 and alerts[0]["ok"] is False


def test_notify_dry_run_records_nothing(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    ref = ReportRef("dag", "r0", "suite", 1, -1)
    notify_for_run(src, ref, policy=_ACTIVE, mailer=SpyMailer(), dry_run=True)
    assert src.get_detail(ref).alerts == ()


def test_notify_attaches_allure_zip(reports_root):

    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    ref = ReportRef("dag", "r0", "suite", 1, -1)
    write_allure(reports_root, ref)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    spy = SpyMailer()
    notify_for_run(src, ref, policy=_ACTIVE, mailer=spy)
    atts = spy.sends[0]["attachments"]
    assert len(atts) == 1 and atts[0][0] == "allure-results.zip" and atts[0][1] > 0


def test_no_allure_means_no_attachment(reports_root):
    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    spy = SpyMailer()
    notify_for_run(
        src, ReportRef("dag", "r0", "suite", 1, -1), policy=_ACTIVE, mailer=spy
    )
    assert spy.sends[0]["attachments"] == []


def test_oversized_allure_archive_is_skipped(reports_root, monkeypatch):
    # LOAD/SECURITY: a huge archive must not be mailed (servers reject it) nor fail the send.
    from airflow_pytest_plugin import notifications as notif

    _write_run(reports_root, "dag", "suite", "r0", [("b", "failed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    # The stub MUST accept ``max_bytes``: allure_attachment passes it, and a stub without it
    # would raise TypeError and be swallowed by the error guard -- passing the assertion below
    # without ever reaching the compressed-size check this test is about.
    monkeypatch.setattr(
        type(src),
        "allure_archive",
        lambda self, ref, *, max_bytes=None: b"x" * (notif._MAX_ATTACHMENT_BYTES + 1),
    )
    spy = SpyMailer()
    out = notify_for_run(
        src, ReportRef("dag", "r0", "suite", 1, -1), policy=_ACTIVE, mailer=spy
    )
    assert (
        out and spy.sends[0]["attachments"] == []
    )  # sent, but without the oversized zip


def test_record_alert_caps_history_and_sanitizes(reports_root):
    # LOAD: 60 appends keep only the newest 50. SECURITY: hostile fields are truncated.
    from airflow_pytest_plugin.sources.filesystem import _ALERTS_CAP

    _write_run(reports_root, "dag", "suite", "r0", [("a", "passed")], _WHEN)
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    ref = ReportRef("dag", "r0", "suite", 1, -1)
    for i in range(60):
        assert src.record_alert(ref, {"at": f"t{i}", "kind": "passed", "ok": True})
    hostile = {
        "at": "x" * 500,
        "kind": "k" * 500,
        "recipients": [f"r{i}@x.io" * 100 for i in range(40)],
        "ok": "truthy-string",
        "manual": 1,
        "extra_field": "dropped",
    }
    assert src.record_alert(ref, hostile)
    alerts = src.get_detail(ref).alerts
    assert len(alerts) == _ALERTS_CAP  # capped
    last = alerts[-1]
    assert len(last["at"]) <= 64 and len(last["kind"]) <= 32
    assert len(last["recipients"]) <= 20
    assert all(len(r) <= 200 for r in last["recipients"])
    assert "extra_field" not in last
    assert last["ok"] is True and last["manual"] is True  # coerced to bool


def test_record_alert_missing_run_is_false(reports_root):
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    assert src.record_alert(ReportRef("dag", "nope", "t", 1, -1), {"ok": True}) is False


def test_detail_tolerates_corrupt_alerts_field(reports_root):
    # A meta whose "alerts" is garbage must not break the detail view.
    import json as _json

    _write_run(reports_root, "dag", "suite", "r0", [("a", "passed")], _WHEN)
    out = ReportLayout().dir_for(reports_root, ReportRef("dag", "r0", "suite", 1, -1))
    meta_path = os.path.join(out, META_FILENAME)
    with open(meta_path, encoding="utf-8") as fh:
        meta = _json.load(fh)
    meta["alerts"] = {"not": "a list"}
    with open(meta_path, "w", encoding="utf-8") as fh:
        _json.dump(meta, fh)
    # junit.xml is required by get_detail; _write_run doesn't create one -> use test_outcomes path
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    from airflow_pytest_plugin.sources.filesystem import _alerts_from_meta

    assert _alerts_from_meta(meta) == ()
    assert src.record_alert(ReportRef("dag", "r0", "suite", 1, -1), {"ok": True})


# --- audit follow-up: helper + edge coverage ---------------------------------------------------
def test_header_safe_strips_control_chars():
    from airflow_pytest_plugin.notifications import _header_safe

    out = _header_safe("a\r\nBcc: evil@x.io")
    assert "\r" not in out and "\n" not in out  # no header injection survives
    assert _header_safe("  x\x00y  ") == "x y"  # NUL -> space, then trimmed
    assert _header_safe("plain subject") == "plain subject"


def test_smtp_config_port_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_HOST", "mail")
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_PORT", "not-a-number")
    cfg = SmtpConfig.from_config()
    assert cfg is not None and cfg.port == 25  # ValueError -> default


def test_flaky_nodes_for_window_edges(reports_root):
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    # < 2 runs -> nothing can flip -> ().
    _write_run(reports_root, "d1", "s", "r0", [("t", "failed")], _WHEN)
    assert flaky_nodes_for(src, "d1", "s", window=30, min_score=0.0) == ()
    # window smaller than history: only the newest `window` runs are considered, so an old
    # flip outside the window doesn't count.
    for i, o in enumerate(["failed", "passed"] + ["passed"] * 4):
        _write_run(
            reports_root, "d2", "s", f"r{i}", [("t", o)], f"2026-06-01T0{i}:00:00+00:00"
        )
    assert (
        flaky_nodes_for(src, "d2", "s", window=2, min_score=0.0) == ()
    )  # last 2 both pass
    assert "t" in flaky_nodes_for(
        src, "d2", "s", window=30, min_score=0.0
    )  # full history flips


def test_allure_attachment_swallows_source_errors(reports_root):
    from airflow_pytest_plugin.notifications import allure_attachment

    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)

    class _Boom(type(src)):
        def allure_archive(self, ref, *, max_bytes=None):
            raise RuntimeError("disk error")

    boom = _Boom(report_root=reports_root, scan_cache_ttl=0)
    assert (
        allure_attachment(boom, ReportRef("dag", "r0", "suite", 1, -1)) == ()
    )  # no raise


def test_allure_archive_max_bytes_skips_oversized(reports_root):
    ref = ReportRef("dag", "r0", "suite", 1, -1)
    _write_run(reports_root, "dag", "suite", "r0", [("a", "passed")], _WHEN)
    write_allure(reports_root, ref, {"big.json": "x" * 5000})
    src = FileSystemReportSource(report_root=reports_root, scan_cache_ttl=0)
    assert src.allure_archive(ref, max_bytes=100) is None  # raw 5000 > 100 -> skipped
    assert src.allure_archive(ref, max_bytes=10_000) is not None  # fits
    assert src.allure_archive(ref) is not None  # unbounded (download path)


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


def test_parser_email_only_fail_notifies_failures_only(monkeypatch, reports_root):
    # email_only_fail=True turns notifications on, but only for a failed / flaky run
    # (always=False downstream) -- teams that don't want success mail use this.
    from airflow_pytest_plugin import notifications
    from airflow_pytest_plugin.producer import ArchivingResultParser

    calls: list = []
    monkeypatch.setattr(
        notifications, "notify_after_archive", lambda ref, **kw: calls.append(kw)
    )
    parser = ArchivingResultParser(report_root=reports_root, email_only_fail=True)
    parser._pending_ref = ReportRef("dag", "run1", "task", 1, -1)
    parser._maybe_notify()
    assert len(calls) == 1 and calls[0]["always"] is False


def test_parser_email_only_fail_overrides_email_true(monkeypatch, reports_root):
    # Both flags set: only-fail wins -- no success mail even though email=True.
    from airflow_pytest_plugin import notifications
    from airflow_pytest_plugin.producer import ArchivingResultParser

    calls: list = []
    monkeypatch.setattr(
        notifications, "notify_after_archive", lambda ref, **kw: calls.append(kw)
    )
    parser = ArchivingResultParser(
        report_root=reports_root, email=True, email_only_fail=True
    )
    parser._pending_ref = ReportRef("dag", "run1", "task", 1, -1)
    parser._maybe_notify()
    assert len(calls) == 1 and calls[0]["always"] is False


# --- AirflowMailer: the compat-shim delegation ------------------------------------------


def test_airflow_mailer_sanitizes_subject_and_builds_fallback_html(monkeypatch):
    # Subject goes through _header_safe (no CR/LF may reach a mail header) and a
    # missing HTML body falls back to the escaped <pre> wrapper of the plain text.
    from airflow_pytest_plugin.notifications import AirflowMailer

    captured: dict = {}

    def fake_send(*, to, subject, html_content, attachments=()):
        captured.update(
            to=to, subject=subject, html=html_content, attachments=attachments
        )

    monkeypatch.setattr(
        "airflow_pytest_plugin.notifications.send_airflow_email", fake_send
    )
    AirflowMailer().send(
        subject="Evil\r\nBcc: attacker@x.io",
        body="<plain & body>",
        recipients=("a@x.io", "b@x.io"),
    )
    assert "\r" not in captured["subject"] and "\n" not in captured["subject"]
    assert "Bcc: attacker@x.io" in captured["subject"]  # collapsed inline, not a header
    assert captured["to"] == ["a@x.io", "b@x.io"]
    assert captured["html"].startswith("<pre")
    assert "&lt;plain &amp; body&gt;" in captured["html"]  # escaped, inert
    assert captured["attachments"] == ()


def test_airflow_mailer_prefers_supplied_html_and_forwards_attachments(monkeypatch):
    from airflow_pytest_plugin.notifications import AirflowMailer

    captured: dict = {}

    def fake_send(*, to, subject, html_content, attachments=()):
        captured.update(html=html_content, attachments=attachments)

    monkeypatch.setattr(
        "airflow_pytest_plugin.notifications.send_airflow_email", fake_send
    )
    payload = (("allure-results.zip", b"PK\x03\x04"),)
    AirflowMailer().send(
        subject="S",
        body="plain",
        recipients=("a@x.io",),
        html="<b>rich</b>",
        attachments=payload,
    )
    assert captured["html"] == "<b>rich</b>"  # supplied HTML wins over the fallback
    assert captured["attachments"] == payload


# --- config validation hardening ---------------------------------------------------------------


def test_smtp_from_with_header_injection_falls_back_to_default(monkeypatch, caplog):
    # A config-borne CRLF in the sender must never reach the From: header.
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_FROM", "evil@x.io\r\nBcc: attacker@x.io")
    with caplog.at_level(logging.WARNING):
        cfg = SmtpConfig.from_config()
    assert cfg is not None and cfg.sender == "airflow-pytest@localhost"
    assert any("smtp_from" in r.getMessage() for r in caplog.records)


def test_smtp_from_keeps_internal_relay_addresses(monkeypatch):
    # Deliberately laxer than is_valid_email: user@mailhost (no TLD) must survive.
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_FROM", "reports@mailhost")
    cfg = SmtpConfig.from_config()
    assert cfg is not None and cfg.sender == "reports@mailhost"


@pytest.mark.parametrize("bad_port", ["0", "70000", "-5", "abc"])
def test_smtp_port_out_of_range_or_garbage_falls_back_to_25(
    monkeypatch, caplog, bad_port
):
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_PORT", bad_port)
    with caplog.at_level(logging.WARNING):
        cfg = SmtpConfig.from_config()
    assert cfg is not None and cfg.port == 25
    assert any("smtp_port" in r.getMessage() for r in caplog.records)


def test_smtp_user_without_password_warns_about_skipped_login(monkeypatch, caplog):
    # The exact misconfiguration behind an opaque "530 Authentication Required".
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AIRFLOW_PYTEST_SMTP_USER", "user@example.com")
    monkeypatch.delenv("AIRFLOW_PYTEST_SMTP_PASSWORD", raising=False)
    with caplog.at_level(logging.WARNING):
        cfg = SmtpConfig.from_config()
    assert cfg is not None
    assert any("NOT authenticate" in r.getMessage() for r in caplog.records)


def test_config_recipients_capped_with_warning(monkeypatch, caplog):
    # 60 configured recipients -> the first 50 kept, loudly.
    many = ",".join(f"user{i:02d}@example.com" for i in range(60))
    monkeypatch.setenv("AIRFLOW_PYTEST_ALERTS_EMAIL_TO", many)
    with caplog.at_level(logging.WARNING):
        policy = AlertPolicy.from_config()
    assert len(policy.recipients) == 50
    assert policy.recipients[0] == "user00@example.com"
    assert policy.recipients[-1] == "user49@example.com"
    assert any("mailing-list" in r.getMessage() for r in caplog.records)


# --- run tracking URL ----------------------------------------------------------------------


def test_run_tracking_url_builds_short_readable_link(monkeypatch):
    # The short ?dag=&run=&task=&try= form — a log viewer can't break it the way it
    # wraps/truncates a ~200-char token, and a human can read where it points.
    from airflow_pytest_plugin import config
    from airflow_pytest_plugin.plugin import run_tracking_url

    monkeypatch.setattr(
        config,
        "get_conf_value",
        lambda section, key: (
            "http://airflow.example.com/" if key == "base_url" else None
        ),
    )
    ref = ReportRef("etl", "manual__2026-07-05T12:00:00+00:00", "unit", 2, -1)
    url = run_tracking_url(ref)
    assert url == (
        "http://airflow.example.com/plugin/pytest-reports"
        "?dag=etl&run=manual__2026-07-05T12%3A00%3A00%2B00%3A00&task=unit&try=2"
    )  # /plugin/<route> = the viewer INSIDE the Airflow chrome, not the bare app
    # '+' MUST be %2B — a raw '+' in a query decodes to a space and misses the run.
    assert "+" not in url.split("?", 1)[1]


def test_run_tracking_url_includes_map_index_only_when_mapped(monkeypatch):
    from airflow_pytest_plugin import config
    from airflow_pytest_plugin.plugin import run_tracking_url

    monkeypatch.setattr(
        config,
        "get_conf_value",
        lambda section, key: "http://af" if key == "base_url" else None,
    )
    plain = run_tracking_url(ReportRef("d", "r", "t", 1, -1))
    mapped = run_tracking_url(ReportRef("d", "r", "t", 1, 3))
    assert plain is not None and "map=" not in plain
    assert mapped is not None and mapped.endswith("&map=3")


def test_run_tracking_url_none_without_base_url(monkeypatch):
    from airflow_pytest_plugin import config
    from airflow_pytest_plugin.plugin import run_tracking_url

    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert run_tracking_url(ReportRef("dag", "r", "t", 1, -1)) is None


def test_parser_logs_tracking_url_after_archive(monkeypatch, caplog):
    from airflow_pytest_plugin import plugin as plugin_mod
    from airflow_pytest_plugin.producer import ArchivingResultParser

    monkeypatch.setattr(
        plugin_mod,
        "run_tracking_url",
        lambda ref: "http://af/pytest-reports/?report=tok",
    )
    parser = ArchivingResultParser()
    parser._pending_ref = ReportRef("dag", "run1", "task", 1, -1)
    with caplog.at_level(logging.INFO):
        parser._log_tracking_url()
    assert any(
        "http://af/pytest-reports/?report=tok" in r.getMessage() for r in caplog.records
    )


def test_parser_logs_coordinates_when_no_base_url(monkeypatch, caplog):
    from airflow_pytest_plugin import plugin as plugin_mod
    from airflow_pytest_plugin.producer import ArchivingResultParser

    monkeypatch.setattr(plugin_mod, "run_tracking_url", lambda ref: None)
    parser = ArchivingResultParser()
    parser._pending_ref = ReportRef("dag", "run1", "task", 1, -1)
    with caplog.at_level(logging.INFO):
        parser._log_tracking_url()
    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("base_url" in m and "run1" in m for m in msgs)


def test_run_tracking_url_encodes_hostile_run_id(monkeypatch):
    # Control characters / spaces in coordinates must be percent-encoded — the URL is
    # logged as one token and must stay clickable and log-injection-proof.
    from airflow_pytest_plugin import config
    from airflow_pytest_plugin.plugin import run_tracking_url

    monkeypatch.setattr(
        config, "get_conf_value", lambda s, k: "http://af" if k == "base_url" else None
    )
    url = run_tracking_url(ReportRef("dag", "run\nid with spaces&x=1", "t", 1, -1))
    assert url is not None
    assert "\n" not in url and " " not in url
    assert "%0A" in url and "%20" in url and "%26" in url  # \n, space, & all encoded


def test_is_valid_email_linear_on_adversarial_input():
    # The validator is split into per-atom LINEAR regexes (no nested quantifiers), so
    # classic polynomial-backtracking payloads finish instantly (CodeQL: poly ReDoS).
    import time

    from airflow_pytest_plugin.notifications import is_valid_email

    hostile = [
        "!" * 253 + "@",  # the CodeQL example: many '!' repetitions
        "a." * 126 + "a",  # maximal atom churn, no @
        ("a" * 63 + ".") * 3 + "@x",  # long atoms, bad domain
    ]
    start = time.perf_counter()
    for address in hostile * 200:
        assert is_valid_email(address) is False
    assert time.perf_counter() - start < 0.5  # 600 hostile inputs, far under a second
