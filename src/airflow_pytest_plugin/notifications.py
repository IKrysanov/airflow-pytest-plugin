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

"""Alerting: opt-in email notifications about an archived run, with adaptive HTML.

Layered like :mod:`retention` -- the decision is pure and testable, separate from the I/O:

- :class:`AlertPolicy` -- value object (recipients, threshold, flaky window; ``from_config``).
- :class:`RunFact` / :class:`Alert` -- plain data in, a ready-to-send email out (no I/O).
- :func:`classify` / :func:`build_run_email` -- pure: a run's status (passed / flaky / failed)
  and the styled email (subject + plain text + inline-CSS HTML).
- :class:`Mailer` -- transport protocol; :class:`AirflowMailer` (Airflow ``send_email``) and
  :class:`SmtpMailer` (standalone SMTP); :func:`build_mailer` picks one (explicit SMTP wins).
- :func:`build_run_alert` / :func:`notify_for_run` -- gather failures + flaky from a
  ``ReportSource`` and emit/send the email.

**When automatic emails go out** is the producer's per-task ``email=`` flag, NOT here:
``ArchivingResultParser(email=True)`` calls this with ``always=True`` -- a "run finished"
notice for EVERY run (styled by outcome); ``email=False`` (the default) sends nothing, so noisy
ping/smoke suites stay silent. The UI "email this run" action also uses ``always=True``. Public
``notify_*`` functions default to the quieter ``always=False`` (email only on failed / flaky).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import quote

from .compat.airflow import airflow_email_available, send_airflow_email
from .config import (
    DEFAULT_FLAKY_MIN_SCORE,
    DEFAULT_FLAKY_WINDOW,
    DEFAULT_SUCCESS_THRESHOLD,
    get_alerts_recipients,
    get_base_url,
    get_conf_value,
    get_flaky_min_score,
    get_flaky_window,
    get_success_threshold,
)
from .flaky_core import FAIL_OUTCOMES, is_flaky
from .models import ReportRef, ReportSummary, run_succeeds

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .sources import ReportSource

_log = logging.getLogger(__name__)

#: How many failed / flaky test ids to list in an email before "+N more".
_MAX_LISTED = 12


# -- recipients: validation + dedupe ----------------------------------------------------------
#: RFC-5321-bounded address shape: printable local part (dots only BETWEEN atoms -- no
#: leading/trailing/double dots), dot-separated LDH domain labels, alphabetic TLD. The charset
#: excludes whitespace and control chars, which also blocks header injection. ``\Z`` (not
#: ``$``) so a trailing newline can't sneak past the anchor.
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}\Z"
)


def is_valid_email(address: str) -> bool:
    """Whether ``address`` is a sane, safely-mailable email address.

    Adds RFC 5321 length limits (local <= 64, total <= 254) to the shape check, so a passing
    address can go into a header verbatim.
    """
    if not address or len(address) > 254:
        return False
    local, sep, _domain = address.partition("@")
    if not sep or len(local) > 64:
        return False
    return _EMAIL_RE.match(address) is not None


def dedupe_emails(addresses: Sequence[str]) -> tuple[str, ...]:
    """Dedupe case-insensitively (one mailbox = one send); keep first spelling and order."""
    seen: set[str] = set()
    out: list[str] = []
    for a in addresses:
        key = a.lower()
        if key not in seen:
            seen.add(key)
            out.append(a)
    return tuple(out)


# -- policy -----------------------------------------------------------------------------------
#: Upper bound on CONFIGURED recipients (env / cfg). Generous — a team list belongs in a
#: mailing-list address anyway — but keeps a runaway config from turning every archive
#: into a mass mailing. (The manual UI endpoint has its own, much lower cap.)
_MAX_CONFIG_RECIPIENTS = 50


@dataclass(frozen=True)
class AlertPolicy:
    """Who to email, the bar below which a run counts as failing, and the flaky window."""

    recipients: tuple[str, ...] = ()
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD
    flaky_window: int = DEFAULT_FLAKY_WINDOW
    flaky_min_score: float = DEFAULT_FLAKY_MIN_SCORE

    @property
    def is_active(self) -> bool:
        """No recipients -> nothing is sent."""
        return bool(self.recipients)

    @classmethod
    def from_config(cls) -> AlertPolicy:
        """Build from env vars / Airflow cfg.

        Recipients are normalized: invalid addresses dropped with a warning (one typo mustn't
        poison every send) and duplicates collapsed case-insensitively.
        """
        valid = []
        for address in get_alerts_recipients():
            if is_valid_email(address):
                valid.append(address)
            else:
                _log.warning(
                    "dropping invalid alert recipient from config: %r", address
                )
        recipients = dedupe_emails(valid)
        if len(recipients) > _MAX_CONFIG_RECIPIENTS:
            _log.warning(
                "%d alert recipients configured; keeping the first %d "
                "(use a mailing-list address for larger audiences)",
                len(recipients),
                _MAX_CONFIG_RECIPIENTS,
            )
            recipients = recipients[:_MAX_CONFIG_RECIPIENTS]
        return cls(
            recipients=recipients,
            success_threshold=get_success_threshold(),
            flaky_window=get_flaky_window(),
            flaky_min_score=get_flaky_min_score(),
        )


# -- facts + result ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RunFact:
    """What the pure logic needs to know about one run -- no I/O."""

    ref: ReportRef
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int

    @classmethod
    def from_summary(cls, s: ReportSummary) -> RunFact:
        return cls(
            ref=s.ref,
            total=s.total,
            passed=s.passed,
            failed=s.failed,
            errors=s.errors,
            skipped=s.skipped,
        )


@dataclass(frozen=True)
class Alert:
    """One notification to send: a subject, a plain-text body, and a styled HTML body."""

    kind: str  # "passed" | "flaky" | "failed"
    dag_id: str
    task_id: str
    subject: str
    body: str
    html: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "dag_id": self.dag_id,
            "task_id": self.task_id,
            "subject": self.subject,
            "body": self.body,
            "html": self.html,
        }


# -- pure classification + rendering ----------------------------------------------------------
def pass_rate_pct(run: RunFact) -> int:
    """Pass-rate over *executed* tests, as a 0–100 int (100 if nothing ran)."""
    executed = run.passed + run.failed + run.errors
    return round(run.passed / executed * 100) if executed else 100


def run_is_failing(run: RunFact, policy: AlertPolicy) -> bool:
    """Whether the run fell below the policy's success threshold."""
    return not run_succeeds(
        run.passed, run.failed, run.errors, policy.success_threshold
    )


def classify(run: RunFact, policy: AlertPolicy, *, has_flaky: bool) -> str:
    """Alerting status: ``failed`` (below the bar) / ``flaky`` / ``passed``."""
    if run_is_failing(run, policy):
        return "failed"
    return "flaky" if has_flaky else "passed"


#: Per-status label + colours (fixed hex -- email clients have no CSS variables).
_STATUS = {
    "passed": {"label": "Passed", "icon": "✓", "color": "#16a34a", "bg": "#f0fdf4"},
    "flaky": {"label": "Flaky", "icon": "⚠", "color": "#b45309", "bg": "#fffbeb"},
    "failed": {"label": "Failed", "icon": "✗", "color": "#dc2626", "bg": "#fef2f2"},
}


def _counts_text(run: RunFact) -> str:
    return (
        f"{run.passed} passed, {run.failed} failed, {run.errors} errors, "
        f"{run.skipped} skipped of {run.total}"
    )


def evaluate_alerts(
    run: RunFact,
    policy: AlertPolicy,
    *,
    failures: Sequence[str] = (),
    flaky: Sequence[str] = (),
    base_url: str | None = None,
    always: bool = False,
) -> list[Alert]:
    """Pure decision: the email(s) a run warrants.

    Without ``always``, only a FAILED or FLAKY run produces an email. With ``always`` (the
    manual UI send) a passing run yields the green summary too.
    """
    status = classify(run, policy, has_flaky=bool(flaky))
    if not always and status == "passed":
        return []
    return [
        build_run_email(run, status, failures=failures, flaky=flaky, base_url=base_url)
    ]


def build_run_email(
    run: RunFact,
    status: str,
    *,
    failures: Sequence[str] = (),
    flaky: Sequence[str] = (),
    base_url: str | None = None,
) -> Alert:
    """Build the styled email (subject + plain text + inline-CSS HTML) for one run.

    Every dynamic string (dag/task/run ids, test node ids) is HTML-escaped, so a hostile
    ``meta.json`` value renders as inert text and can't inject markup.
    """
    meta = _STATUS.get(status, _STATUS["failed"])
    dag, task, run_id = run.ref.dag_id, run.ref.task_id, run.ref.run_id
    rate = pass_rate_pct(run)
    subject = f"[pytest] {dag}·{task} — {meta['label']} ({rate}% pass)"

    text = f"{meta['label']}: {dag}·{task} run {run_id} — {rate}% pass ({_counts_text(run)})."
    text += _list_text("Failed tests", failures)
    text += _list_text("Flaky tests", flaky)

    return Alert(
        kind=status,
        dag_id=dag,
        task_id=task,
        subject=subject,
        body=text,
        html=_render_html(
            run, meta, rate, failures=failures, flaky=flaky, base_url=base_url
        ),
    )


def _list_text(title: str, items: Sequence[str]) -> str:
    if not items:
        return ""
    shown = "\n".join(f"  - {i}" for i in items[:_MAX_LISTED])
    more = f"\n  … +{len(items) - _MAX_LISTED} more" if len(items) > _MAX_LISTED else ""
    return f"\n\n{title}:\n{shown}{more}"


def _stat_cell(value: int, label: str, color: str) -> str:
    return (
        '<td align="center" style="padding:6px 4px;">'
        f'<div style="font-size:22px;font-weight:700;color:{color};'
        f'font-variant-numeric:tabular-nums;line-height:1.1;">{value}</div>'
        f'<div style="font-size:11px;letter-spacing:.04em;text-transform:uppercase;'
        f'color:#6b7280;margin-top:2px;">{escape(label)}</div></td>'
    )


def _list_section(title: str, items: Sequence[str], accent: str) -> str:
    if not items:
        return ""
    rows = "".join(
        '<div style="font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;'
        'color:#111827;word-break:break-all;padding:4px 0;border-top:1px solid #f3f4f6;">'
        f"{escape(i)}</div>"
        for i in items[:_MAX_LISTED]
    )
    more = (
        f'<div style="color:#6b7280;font-size:12px;padding-top:6px;">'
        f"… +{len(items) - _MAX_LISTED} more</div>"
        if len(items) > _MAX_LISTED
        else ""
    )
    return (
        '<tr><td style="padding:4px 24px 0;">'
        f'<div style="font-size:13px;font-weight:650;color:{accent};margin:14px 0 2px;">'
        f"{escape(title)}</div>{rows}{more}</td></tr>"
    )


def _render_html(
    run: RunFact,
    meta: dict[str, str],
    rate: int,
    *,
    failures: Sequence[str],
    flaky: Sequence[str],
    base_url: str | None,
) -> str:
    dag, task = escape(run.ref.dag_id), escape(run.ref.task_id)
    run_id = escape(run.ref.run_id)
    color, bg = meta["color"], meta["bg"]
    link = ""
    if base_url:
        url = (
            f"{base_url}/dags/{quote(run.ref.dag_id, safe='')}"
            f"/runs/{quote(run.ref.run_id, safe='')}"
            f"/tasks/{quote(run.ref.task_id, safe='')}"
        )
        link = (
            f' · <a href="{escape(url, quote=True)}" '
            f'style="color:#017cee;text-decoration:none;">open in Airflow</a>'
        )
    counts = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin-top:4px;"><tr>'
        + _stat_cell(run.passed, "passed", "#16a34a")
        + _stat_cell(run.failed, "failed", "#dc2626")
        + _stat_cell(run.errors, "errors", "#9333ea")
        + _stat_cell(run.skipped, "skipped", "#6b7280")
        + "</tr></table>"
    )
    return (
        '<div style="margin:0;padding:24px 12px;background:#f4f4f5;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;\">"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background:#ffffff;border:1px solid #e5e7eb;'
        'border-radius:14px;overflow:hidden;">'
        # header bar
        f'<tr><td style="background:{color};padding:18px 24px;color:#ffffff;">'
        f'<div style="font-size:22px;font-weight:700;">{escape(meta["icon"])} {escape(meta["label"])}'
        f'<span style="font-weight:400;opacity:.9;font-size:15px;"> · {rate}% pass</span></div>'
        f'<div style="opacity:.92;font-size:13px;margin-top:3px;">{dag} · {task}</div></td></tr>'
        # pass-rate tint band + counts
        f'<tr><td style="background:{bg};padding:16px 24px;">{counts}</td></tr>'
        # optional lists
        + _list_section("Failed tests", failures, "#dc2626")
        + _list_section("Flaky tests", flaky, "#b45309")
        # footer
        + '<tr><td style="padding:14px 24px;border-top:1px solid #e5e7eb;'
        f'color:#6b7280;font-size:12px;">run {run_id} · try {run.ref.try_number}{link}</td></tr>'
        "</table></td></tr></table></div>"
    )


# -- transport --------------------------------------------------------------------------------
#: One email attachment: (filename, payload bytes).
Attachment = tuple[str, bytes]

#: Attachments above this are skipped (mail servers commonly reject ~25 MB messages, and a huge
#: Allure archive must not stall the producer or API worker).
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
#: Raw Allure results above this aren't even zipped (bounds peak memory before the
#: compressed-size check above); generous vs the attachment cap since results compress well.
_MAX_RAW_ALLURE_BYTES = 50 * 1024 * 1024


class Mailer(Protocol):
    """Sends one alert email. May raise on delivery errors; the orchestrator guards."""

    def send(
        self,
        *,
        subject: str,
        body: str,
        recipients: Sequence[str],
        html: str | None = None,
        attachments: Sequence[Attachment] = (),
    ) -> None: ...


def _header_safe(value: str) -> str:
    """Collapse CR/LF (and stray control chars) so a value can't inject email headers.

    Subjects interpolate ``dag_id``/``task_id``/``run_id`` from a semi-trusted ``meta.json``.
    The stdlib already rejects newlines in a header, so this is defence in depth that also
    keeps a legit alert deliverable instead of raising on an odd character.
    """
    return "".join(" " if c in "\r\n\t" or ord(c) < 32 else c for c in value).strip()


class AirflowMailer:
    """Sends via Airflow's configured SMTP (see ``compat.airflow.send_airflow_email``)."""

    def send(
        self,
        *,
        subject: str,
        body: str,
        recipients: Sequence[str],
        html: str | None = None,
        attachments: Sequence[Attachment] = (),
    ) -> None:
        send_airflow_email(
            to=list(recipients),
            subject=_header_safe(subject),
            html_content=html or _as_html(body),
            attachments=attachments,
        )


_DEFAULT_SENDER = "airflow-pytest@localhost"


def _sanitize_sender(raw: str | None) -> str:
    """A header-safe ``From`` address, falling back to the default on garbage.

    Config is operator-controlled but still deserves defence in depth: a value with
    control characters or whitespace could smuggle extra headers into the message, and
    one without ``@`` is guaranteed to bounce. Deliberately laxer than
    :func:`is_valid_email` so internal relay addresses (``user@mailhost``, no TLD)
    keep working.
    """
    s = (raw or "").strip()
    if not s:
        return _DEFAULT_SENDER
    if "@" not in s or any(ord(ch) <= 32 or ord(ch) == 127 for ch in s):
        _log.warning(
            "ignoring invalid smtp_from %r; sending as %r", s[:100], _DEFAULT_SENDER
        )
        return _DEFAULT_SENDER
    return s


@dataclass(frozen=True)
class SmtpConfig:
    """Standalone SMTP settings (used when ``AIRFLOW_PYTEST_SMTP_HOST`` is set)."""

    host: str
    port: int = 25
    user: str | None = None
    password: str | None = None
    sender: str = _DEFAULT_SENDER
    starttls: bool = True

    @classmethod
    def from_config(cls) -> SmtpConfig | None:
        """Build from env / cfg, or ``None`` when no SMTP host is configured.

        Values are validated, not trusted: a bad port falls back to 25 with a warning,
        the sender is header-sanitized, and a user *or* password alone (login would be
        silently skipped, ending in an opaque 530 from the server) is called out.
        """

        def val(env: str, key: str) -> str | None:
            raw = os.environ.get(env)
            if raw is None or not raw.strip():
                raw = get_conf_value("pytest_reports", key)
            return raw.strip() if raw and raw.strip() else None

        host = val("AIRFLOW_PYTEST_SMTP_HOST", "smtp_host")
        if not host:
            return None
        port_raw = val("AIRFLOW_PYTEST_SMTP_PORT", "smtp_port")
        port = 25
        if port_raw:
            try:
                port = int(port_raw)
            except ValueError:
                _log.warning("invalid smtp_port %r; using 25", port_raw[:20])
                port = 25
            else:
                if not 1 <= port <= 65535:
                    _log.warning("smtp_port %d out of range; using 25", port)
                    port = 25
        user = val("AIRFLOW_PYTEST_SMTP_USER", "smtp_user")
        password = val("AIRFLOW_PYTEST_SMTP_PASSWORD", "smtp_password")
        if bool(user) != bool(password):
            _log.warning(
                "smtp_user and smtp_password must BOTH be set for SMTP login; "
                "only one is configured, so the send will NOT authenticate"
            )
        starttls_raw = (
            val("AIRFLOW_PYTEST_SMTP_STARTTLS", "smtp_starttls") or ""
        ).lower()
        return cls(
            host=host,
            port=port,
            user=user,
            password=password,
            sender=_sanitize_sender(val("AIRFLOW_PYTEST_SMTP_FROM", "smtp_from")),
            starttls=starttls_raw not in {"0", "false", "no", "off", "n", "f"},
        )


class SmtpMailer:
    """Sends via a standalone SMTP server (when ``AIRFLOW_PYTEST_SMTP_*`` is set, or Airflow is
    unavailable). A plain-text + HTML ``multipart/alternative`` message."""

    def __init__(self, cfg: SmtpConfig) -> None:
        self._cfg = cfg

    def send(
        self,
        *,
        subject: str,
        body: str,
        recipients: Sequence[str],
        html: str | None = None,
        attachments: Sequence[Attachment] = (),
    ) -> None:
        import smtplib
        from email.message import EmailMessage

        cfg = self._cfg
        msg = EmailMessage()
        msg["Subject"] = _header_safe(subject)
        msg["From"] = cfg.sender
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
        for name, payload in attachments:
            msg.add_attachment(
                payload,
                maintype="application",
                subtype="zip" if name.endswith(".zip") else "octet-stream",
                filename=os.path.basename(name) or "attachment.bin",
            )
        with smtplib.SMTP(cfg.host, cfg.port, timeout=10) as smtp:
            if cfg.starttls:
                smtp.starttls()
            if cfg.user and cfg.password:
                smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg)


def _as_html(body: str) -> str:
    """Wrap a plain-text body as minimal escaped HTML (fallback when no styled HTML given)."""
    return '<pre style="font: 13px/1.5 monospace">' + escape(body) + "</pre>"


def build_mailer() -> Mailer | None:
    """Pick a transport, preferring an explicitly-configured standalone SMTP.

    If ``AIRFLOW_PYTEST_SMTP_HOST`` is set the operator wants that server, so use it even in
    Airflow (whose own ``[smtp]`` may be unset) -- honouring explicit config avoids silently
    routing through Airflow's ``send_email``. Otherwise fall back to Airflow's ``send_email``
    when importable, else no transport (``None``).
    """
    cfg = SmtpConfig.from_config()
    if cfg is not None:
        return SmtpMailer(cfg)
    if airflow_email_available():
        return AirflowMailer()
    return None


# -- I/O: gather the facts an email needs -----------------------------------------------------
def _summary_for(source: ReportSource, ref: ReportRef) -> ReportSummary | None:
    """The archived summary for exactly ``ref`` (``None`` if not listed)."""
    for s in source.list_summaries(dag_id=ref.dag_id):
        if s.ref == ref:
            return s
    return None


def failed_nodes_for(source: ReportSource, ref: ReportRef) -> tuple[str, ...]:
    """Failed/errored test node ids of one run (empty if per-test data is unavailable)."""
    outcomes = source.test_outcomes(ref) or {}
    return tuple(
        sorted(
            n for n, info in outcomes.items() if info.get("outcome") in FAIL_OUTCOMES
        )
    )


def flaky_nodes_for(
    source: ReportSource,
    dag_id: str,
    task_id: str,
    *,
    window: int,
    min_score: float,
) -> tuple[str, ...]:
    """Node ids flaky across the dag·task's most recent ``window`` runs (empty if <2 runs)."""
    rows = [
        s
        for s in source.list_summaries(dag_id=dag_id)
        if s.ref.dag_id == dag_id and s.ref.task_id == task_id
    ]
    if len(rows) < 2:
        return ()
    rows.sort(key=lambda s: s.created_at or "", reverse=True)
    seqs: dict[str, list[str]] = {}
    for s in sorted(
        rows[:window], key=lambda s: s.created_at or ""
    ):  # oldest -> newest
        for node, info in (source.test_outcomes(s.ref) or {}).items():
            seqs.setdefault(node, []).append(info.get("outcome", ""))
    return tuple(
        sorted(n for n, seq in seqs.items() if is_flaky(seq, min_score=min_score))
    )


def build_run_alert(
    source: ReportSource,
    ref: ReportRef,
    policy: AlertPolicy,
    *,
    always: bool = False,
) -> Alert | None:
    """Gather a run's facts (failures + flaky) and build its styled email, or ``None``.

    ``None`` when the run is gone, or when it passed cleanly and ``always`` is off (so an
    automatic pass sends nothing).
    """
    summ = _summary_for(source, ref)
    if summ is None:
        return None
    run = RunFact.from_summary(summ)
    failing = run_is_failing(run, policy)
    # Only read what the decision needs: no flaky scan for a failing run, no failure list for a
    # passing one. ``evaluate_alerts`` then classifies + applies the ``always`` gate -- one
    # decision point, so the logic isn't duplicated here.
    flaky = (
        ()
        if failing
        else flaky_nodes_for(
            source,
            ref.dag_id,
            ref.task_id,
            window=policy.flaky_window,
            min_score=policy.flaky_min_score,
        )
    )
    failures = failed_nodes_for(source, ref) if failing else ()
    alerts = evaluate_alerts(
        run,
        policy,
        failures=failures,
        flaky=flaky,
        base_url=get_base_url(),
        always=always,
    )
    return alerts[0] if alerts else None


# -- orchestration ----------------------------------------------------------------------------
def allure_attachment(source: ReportSource, ref: ReportRef) -> tuple[Attachment, ...]:
    """The run's raw Allure results as a zip attachment, when present and small enough.

    Empty when the run has no Allure results, the source can't produce them, or the archive
    exceeds ``_MAX_ATTACHMENT_BYTES`` -- skipping keeps the notification deliverable rather
    than failing it.
    """
    try:
        # Bound peak memory: raw results beyond the raw cap aren't zipped in RAM (returns
        # None). The compressed result is still checked below.
        payload = source.allure_archive(ref, max_bytes=_MAX_RAW_ALLURE_BYTES)
    except Exception:  # a corrupt archive must not break the notification itself
        _log.exception("failed to build the Allure attachment for %s", ref.token)
        return ()
    if not payload:
        return ()
    if len(payload) > _MAX_ATTACHMENT_BYTES:
        _log.warning(
            "Allure archive for %s is %d bytes (> %d); sending the email without it",
            ref.token,
            len(payload),
            _MAX_ATTACHMENT_BYTES,
        )
        return ()
    return (("allure-results.zip", payload),)


def record_sent_alert(
    source: ReportSource,
    ref: ReportRef,
    alert: Alert,
    recipients: Sequence[str],
    *,
    ok: bool,
    manual: bool,
) -> None:
    """Best-effort: append this send to the run's notification history."""
    try:
        source.record_alert(
            ref,
            {
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": alert.kind,
                "recipients": list(recipients),
                "ok": ok,
                "manual": manual,
            },
        )
    except Exception:  # history is informational; never fail the send path over it
        _log.exception("failed to record the alert history for %s", ref.token)


def _deliver(
    alert: Alert,
    policy: AlertPolicy,
    mailer: Mailer | None,
    attachments: Sequence[Attachment] = (),
) -> bool:
    """Send one alert; ``True`` on success, ``False`` when skipped or failed (both logged)."""
    transport = mailer if mailer is not None else build_mailer()
    if transport is None:
        _log.warning("alert raised but no mail transport is configured; not sending")
        return False
    try:
        transport.send(
            subject=alert.subject,
            body=alert.body,
            html=alert.html,
            recipients=policy.recipients,
            attachments=attachments,
        )
        return True
    except Exception:
        _log.exception("failed to send %s alert email", alert.kind)
        return False


def notify_for_run(
    source: ReportSource,
    ref: ReportRef,
    *,
    policy: AlertPolicy | None = None,
    mailer: Mailer | None = None,
    dry_run: bool = False,
    always: bool = False,
) -> list[Alert]:
    """Build and (unless ``dry_run``) send the alert for the run at ``ref``.

    The email carries the run's Allure results as a size-capped zip when available, and every
    real send attempt is recorded in the run's notification history. Returns the alert(s)
    raised (sent or not). A send failure is logged and swallowed, so a broken mailer can't fail
    the surrounding task.
    """
    resolved = policy if policy is not None else AlertPolicy.from_config()
    if not resolved.is_active:  # no recipients -> nothing to do
        return []
    alert = build_run_alert(source, ref, resolved, always=always)
    if alert is None:
        return []
    if not dry_run:
        ok = _deliver(alert, resolved, mailer, allure_attachment(source, ref))
        record_sent_alert(source, ref, alert, resolved.recipients, ok=ok, manual=False)
    _log.info(
        "alert: %s for %s·%s (always=%s, dry_run=%s)",
        alert.kind,
        ref.dag_id,
        ref.task_id,
        always,
        dry_run,
    )
    return [alert]


def notify_after_archive(
    ref: ReportRef,
    *,
    report_root: str | None = None,
    source: ReportSource | None = None,
    policy: AlertPolicy | None = None,
    always: bool = False,
) -> list[Alert]:
    """Producer entry point: call right after archiving ``ref`` to email an alert.

    Automatic (``always=False``) sends only on a failed / flaky run. When no recipients are
    configured it logs a warning (email was requested but nothing can be delivered) and
    returns without touching the filesystem.
    """
    resolved = policy if policy is not None else AlertPolicy.from_config()
    if not resolved.is_active:
        # Reached only when a per-task email flag asked us to notify, yet no recipients
        # are configured -> the send would silently do nothing. Warn (once per run) so the
        # misconfiguration is visible instead of leaving the operator guessing, then skip
        # without touching the filesystem.
        _log.warning(
            "email notification requested for %s·%s but no recipients are configured "
            "(set AIRFLOW_PYTEST_ALERTS_EMAIL_TO); nothing sent",
            ref.dag_id,
            ref.task_id,
        )
        return []
    if source is None:
        from .sources import FileSystemReportSource

        source = FileSystemReportSource(report_root=report_root)
    return notify_for_run(source, ref, policy=resolved, always=always)
