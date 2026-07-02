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

"""Fixtures for the Playwright UI regression suite.

Seeds a deterministic report tree, boots the standalone dev server against it once per
session, and exposes a ``dash`` helper that navigates to a fresh dashboard and captures
any JS/console errors. These tests are opt-in (marker ``ui``); see ``tests/ui/README.md``.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="install the 'ui-test' extra to run UI tests")

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
sys.path.insert(0, str(_SRC))

from airflow_pytest_plugin.layout import META_FILENAME, ReportLayout  # noqa: E402
from airflow_pytest_plugin.models import ReportRef  # noqa: E402

# --- deterministic seed -------------------------------------------------------
# Two profiles, same generator (so layout is checked on both small and large data):
#  * SMALL  = 3 dag·tasks x 6 runs   -> precise assertions (Flaky=3, Failures=2, Slow=1)
#  * LARGE  = 40 dag·tasks x 80 runs -> stress (carousel scrolls, long group list, many
#                                       flaky/failing groups) for "nothing разъезжается".
# A "rich" group carries a persistently-broken test + an error test (its LATEST run then
# has small adjacent fail/error donut slices) and a test whose recent half runs ~5x slower.
# Every group has a flaky test (flips pass/fail by run parity).
_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_SMALL = [("alpha", True), ("beta", False), ("gamma", False)]
_SMALL_NRUNS = 6
_LARGE = [(f"d{i:02d}", i % 4 == 0) for i in range(40)]  # 10 rich, 30 green-latest
_LARGE_NRUNS = 80


def _cases_for(dag: str, ri: int, nruns: int, rich: bool) -> list[tuple]:
    cases: list[tuple] = [
        (f"tests/t_{dag}.py::test_pass_{ti:02d}", "passed", 0.1) for ti in range(16)
    ]
    # Flaky: fails on even runs, passes on odd -> both outcomes in the window.
    cases.append(
        (f"tests/t_{dag}.py::test_flaky_00", "failed" if ri % 2 == 0 else "passed", 0.1)
    )
    if rich:
        cases.append(
            (
                f"tests/t_{dag}.py::test_broken_00",
                "failed",
                0.1,
                "AssertionError: boom 1 != 2",
            )
        )
        cases.append(
            (f"tests/t_{dag}.py::test_err_00", "error", 0.1, "RuntimeError: kaboom 7")
        )
        # A duration regression: the slow endpoint only looks at the last 30 runs
        # (DEFAULT_FLAKY_WINDOW), so the ~5x jump must sit inside the NEWER half of that
        # window for both the small (6-run) and large (80-run) seeds.
        win = min(30, nruns)
        slow_from = nruns - max(2, win // 3)
        cases.append(
            (
                f"tests/t_{dag}.py::test_slow_00",
                "passed",
                1.0 if ri >= slow_from else 0.2,
            )
        )
    return cases


def _write_run(root: str, dag: str, run: str, when: str, cases: list[tuple]) -> None:
    ref = ReportRef(dag, run, "suite", 1, -1)
    out = ReportLayout().dir_for(root, ref)
    os.makedirs(out, exist_ok=True)
    tc, rows = [], []
    p = f = e = sk = 0
    dur = 0.0
    for c in cases:
        node, oc, d = c[0], c[1], c[2]
        msg = c[3] if len(c) > 3 else ""
        rows.append([node, oc, d])
        dur += d
        cls, name = node.split("::", 1)
        attrs = f'classname="{cls}" name="{name}" time="{d:.3f}"'
        if oc == "passed":
            p += 1
            body = "<system-out>ok</system-out>"
        elif oc == "skipped":
            sk += 1
            body = "<skipped/>"
        else:
            tag = "failure" if oc == "failed" else "error"
            if oc == "failed":
                f += 1
            else:
                e += 1
            body = f'<{tag} message="{msg}">{msg}</{tag}>'
        tc.append(f"<testcase {attrs}>{body}</testcase>")
    total = p + f + e + sk
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite name="pytest" tests="{total}" failures="{f}" '
        f'errors="{e}" skipped="{sk}" time="{dur:.3f}">'
        + "".join(tc)
        + "</testsuite></testsuites>"
    )
    with open(os.path.join(out, "junit.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)
    meta = {
        "schema_version": 1,
        "dag_id": dag,
        "run_id": run,
        "task_id": "suite",
        "try_number": 1,
        "map_index": -1,
        "logical_date": when,
        "created_at": when,
        "report_file": "junit.xml",
        "summary": {
            "total": total,
            "passed": p,
            "failed": f,
            "skipped": sk,
            "errors": e,
            "duration": round(dur, 3),
            "exit_code": 0 if (f + e) == 0 else 1,
            "success": (f + e) == 0,
            "failed_node_ids": [],
        },
        "tests": rows,
    }
    with open(os.path.join(out, META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)


def _seed(root: str, specs: list[tuple[str, bool]], nruns: int) -> None:
    for gi, (dag, rich) in enumerate(specs):
        for ri in range(nruns):
            when = (_BASE + timedelta(hours=gi * nruns + ri)).isoformat()
            _write_run(root, dag, f"r{ri:03d}", when, _cases_for(dag, ri, nruns, rich))


def _seed_green(root: str, nruns: int = 8) -> None:
    """All-passing runs of one dag·task: no flips -> no flaky, no failures -> no clusters.

    Used to check that the flaky panel / group chips / run-detail flaky button all disappear
    when there is nothing flaky (and the runs chart then takes the full board width).
    """
    cases = [(f"tests/g.py::test_ok_{ti:02d}", "passed", 0.1) for ti in range(4)]
    for ri in range(nruns):
        when = (_BASE + timedelta(hours=ri)).isoformat()
        _write_run(root, "green_dag", f"r{ri:03d}", when, cases)


def _seed_declining(root: str, nruns: int = 40) -> None:
    """One dag·task whose health declines over time: the earliest runs all pass, later runs
    fail more and more. Proves the run-health trend line slopes down (delta ▼, negative)."""
    ntests = 10
    for ri in range(nruns):
        frac = (ri / (nruns - 1)) * 0.6  # 0 (first run) -> 0.6 (last run) failing
        nfail = round(frac * ntests)
        cases = [
            (
                f"tests/d.py::test_{ti:02d}",
                "failed" if ti < nfail else "passed",
                0.1,
                "boom" if ti < nfail else "",
            )
            for ti in range(ntests)
        ]
        when = (_BASE + timedelta(hours=ri)).isoformat()
        _write_run(root, "declining_dag", f"r{ri:03d}", when, cases)


#: XSS payload embedded in a test node id + failure message (the failure decodes to live HTML),
#: to regression-test that the UI escapes user-supplied strings client-side.
_XSS_NODE = "tests/x.py::test_<script>window.__xss=1</script>_case"
_XSS_MSG = '"><img src=x onerror="window.__xss=1">'


def _seed_evil(root: str, nruns: int = 3) -> None:
    """One dag·task whose test carries an XSS payload in its node id + failure message.

    The junit is valid (payload XML-escaped, so it parses), but the DECODED strings are hostile
    HTML — the viewer must render them as inert text, never execute them.
    """
    import xml.sax.saxutils as su

    name_attr = su.quoteattr(_XSS_NODE.split("::", 1)[1])
    junit = (
        '<?xml version="1.0"?><testsuites>'
        '<testsuite name="p" tests="1" failures="1" errors="0" skipped="0" time="0.1">'
        f'<testcase classname="tests/x.py" name={name_attr} time="0.1">'
        f"<failure message={su.quoteattr(_XSS_MSG)}>{su.escape(_XSS_MSG)}</failure>"
        "</testcase></testsuite></testsuites>"
    )
    for ri in range(nruns):
        ref = ReportRef("evil", f"r{ri:03d}", "suite", 1, -1)
        out = ReportLayout().dir_for(root, ref)
        os.makedirs(out, exist_ok=True)
        Path(out, "junit.xml").write_text(junit, encoding="utf-8")
        when = (_BASE + timedelta(hours=ri)).isoformat()
        Path(out, META_FILENAME).write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "dag_id": "evil",
                    "run_id": f"r{ri:03d}",
                    "task_id": "suite",
                    "try_number": 1,
                    "map_index": -1,
                    "logical_date": when,
                    "created_at": when,
                    "report_file": "junit.xml",
                    "summary": {
                        "total": 1,
                        "passed": 0,
                        "failed": 1,
                        "skipped": 0,
                        "errors": 0,
                        "duration": 0.1,
                        "exit_code": 1,
                        "success": False,
                        "failed_node_ids": [_XSS_NODE],
                    },
                    "tests": [[_XSS_NODE, "failed", 0.1]],
                }
            ),
            encoding="utf-8",
        )


# --- dev server ---------------------------------------------------------------
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _boot(root: str, *, extra_env: dict | None = None):
    """Start the standalone dev server against ``root``; yield its base URL, then stop it."""
    port = _free_port()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "airflow_pytest_plugin.web",
            "--root",
            root,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode() if proc.stdout else ""
            raise RuntimeError(f"dev server exited early:\n{out}")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.25)
    if not ready:
        proc.terminate()
        raise RuntimeError("dev server did not become ready in 30s")
    try:
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    """Small seed (3 dag·tasks x 6 runs) -> precise assertions."""
    root = tmp_path_factory.mktemp("ui-reports-small")
    _seed(str(root), _SMALL, _SMALL_NRUNS)
    yield from _boot(str(root))


@pytest.fixture(scope="session")
def large_base_url(tmp_path_factory):
    """Large seed (40 dag·tasks x 80 runs = 3200 runs) -> layout stress at scale."""
    root = tmp_path_factory.mktemp("ui-reports-large")
    _seed(str(root), _LARGE, _LARGE_NRUNS)
    yield from _boot(str(root))


@pytest.fixture(scope="session")
def green_base_url(tmp_path_factory):
    """All-green seed (no flaky, no failures) -> flaky UI absent, chart full width."""
    root = tmp_path_factory.mktemp("ui-reports-green")
    _seed_green(str(root))
    yield from _boot(str(root))


@pytest.fixture(scope="session")
def evil_base_url(tmp_path_factory):
    """Seed with an XSS payload in a test name/message -> verify the UI escapes it."""
    root = tmp_path_factory.mktemp("ui-reports-evil")
    _seed_evil(str(root))
    yield from _boot(str(root))


@pytest.fixture(scope="session")
def declining_base_url(tmp_path_factory):
    """Seed whose run health declines over time -> the run-health trend line slopes down."""
    root = tmp_path_factory.mktemp("ui-reports-declining")
    _seed_declining(str(root))
    yield from _boot(str(root))


@pytest.fixture(scope="session")
def email_base_url(tmp_path_factory):
    """Server booted with an SMTP host configured -> a mail transport exists, so
    ``email_available`` is true and the run-detail Email button shows."""
    root = tmp_path_factory.mktemp("ui-reports-email")
    _seed(str(root), _SMALL, _SMALL_NRUNS)
    yield from _boot(
        str(root),
        extra_env={
            "AIRFLOW_PYTEST_SMTP_HOST": "localhost",
            "AIRFLOW_PYTEST_ALERTS_EMAIL_TO": "team@example.com",
        },
    )


@dataclass
class Dash:
    page: object
    errors: list = field(default_factory=list)


def _load_dash(page, url: str) -> Dash:
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: (
            errors.append(f"console.error: {msg.text}") if msg.type == "error" else None
        ),
    )
    page.goto(url)
    page.wait_for_selector("#kpis:not([hidden])", timeout=20000)
    page.wait_for_selector(".chart-bars", timeout=20000)
    return Dash(page=page, errors=errors)


@pytest.fixture
def dash(page, base_url) -> Dash:
    """A loaded SMALL dashboard with JS/console-error capture wired up before navigation."""
    return _load_dash(page, base_url)


@pytest.fixture
def large_dash(page, large_base_url) -> Dash:
    """A loaded LARGE dashboard (3200 runs / 40 groups) for layout-at-scale checks."""
    return _load_dash(page, large_base_url)


@pytest.fixture
def green_dash(page, green_base_url) -> Dash:
    """A loaded dashboard with no flaky tests -> flaky panel/chips/buttons should be absent."""
    return _load_dash(page, green_base_url)


@pytest.fixture
def evil_dash(page, evil_base_url) -> Dash:
    """A loaded dashboard whose data carries an XSS payload -> the UI must escape it."""
    return _load_dash(page, evil_base_url)


@pytest.fixture
def declining_dash(page, declining_base_url) -> Dash:
    """A loaded dashboard whose health declines over time -> the trend line slopes down."""
    return _load_dash(page, declining_base_url)


@pytest.fixture
def email_dash(page, email_base_url) -> Dash:
    """A loaded dashboard whose server has a mail transport -> the Email button is available."""
    return _load_dash(page, email_base_url)


# --- real Airflow (embedded) --------------------------------------------------
@pytest.fixture(scope="session")
def airflow_base_url(tmp_path_factory):
    """Boot a REAL Airflow api-server with the plugin mounted; yield the embedded app URL.

    Uses ``simple_auth_manager_all_admins`` so there's no login wall (everyone is admin),
    which keeps the test about *our* embedded UI, not Airflow's auth chrome. Skips if
    Airflow isn't installed (so the standalone ``ui`` job is unaffected).
    """
    pytest.importorskip(
        "airflow", reason="install Airflow to run the embedded UI tests"
    )
    reports = tmp_path_factory.mktemp("af-reports")
    _seed(str(reports), _SMALL, _SMALL_NRUNS)
    home = tmp_path_factory.mktemp("af-home")
    airflow_bin = str(Path(sys.executable).with_name("airflow"))
    env = dict(os.environ)
    env.update(
        {
            "AIRFLOW_HOME": str(home),
            "AIRFLOW_PYTEST_REPORTS_ROOT": str(reports),
            "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS": "True",
            "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
            "PYTHONPATH": str(_SRC) + os.pathsep + env.get("PYTHONPATH", ""),
        }
    )
    subprocess.run(
        [airflow_bin, "db", "migrate"],
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )
    port = _free_port()
    proc = subprocess.Popen(
        [airflow_bin, "api-server", "-p", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    app_url = f"http://127.0.0.1:{port}/pytest-reports/"
    deadline = time.time() + 120
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode() if proc.stdout else ""
            raise RuntimeError(f"airflow api-server exited early:\n{out[-3000:]}")
        try:
            with urllib.request.urlopen(app_url + "api/health", timeout=2) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(1)
    if not ready:
        proc.terminate()
        raise RuntimeError("airflow api-server did not serve the plugin in 120s")
    try:
        yield app_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


@pytest.fixture
def airflow_dash(page, airflow_base_url) -> Dash:
    """The dashboard EMBEDDED in a real Airflow api-server (plugin mount at /pytest-reports/)."""
    return _load_dash(page, airflow_base_url)
