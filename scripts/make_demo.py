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

"""Regenerate docs/demo.webp -- the README's opening demo.

Nothing here is staged: it boots a REAL Airflow 3, triggers two DAGs that run pytest through
``airflow-pytest-operator``, waits for the operator to archive their reports, and then tours
the plugin embedded in Airflow's own UI. Needs an interpreter that has Airflow, the operator,
Playwright and ffmpeg on PATH -- i.e. the throwaway Airflow venv, not the plugin's:

    .venv-airflow/bin/pip install allure-pytest pytest-cov
    .venv-airflow/bin/python scripts/make_demo.py

Two settings are easy to get wrong and cost hours:

* ``PATH`` must contain the venv's ``bin``: ``airflow standalone`` spawns its components by
  running the bare command ``airflow``, so without it they die with ``FileNotFoundError``.
* ``AIRFLOW__CORE__EXECUTION_API_SERVER_URL`` must point at the api-server we actually start.
  It defaults to port 8080; if anything else holds that port (Docker Desktop, commonly) the
  task worker talks to the stranger, and every task fails with "Invalid auth token".
"""

import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, "tests/ui")
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

import conftest as c

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "demo.webp"
VENV_BIN = pathlib.Path(sys.executable).parent

DAGS = ("etl_daily_tests", "api_gateway_tests")

SUITES = {
    "test_checkout.py": """
import time

def test_cart_totals():
    time.sleep(0.05)
    assert 2 + 2 == 4

def test_discount_applied():
    time.sleep(0.04)
    assert True

def test_tax_rounding():
    time.sleep(0.03)
    assert round(1.005, 2) == 1.0

def test_currency_format():
    time.sleep(0.03)
    assert f"{9.5:.2f}" == "9.50"
""",
    "test_gateway.py": """
import time

def test_auth_token():
    time.sleep(0.05)
    assert "tok"

def test_rate_limit():
    time.sleep(0.04)
    assert 100 > 10

def test_retry_policy():
    time.sleep(0.03)
    assert True
""",
}

DAG_FILE = """
from datetime import datetime

from airflow import DAG

from airflow_pytest_operator import PytestOperator
from airflow_pytest_plugin import ArchivingResultParser

SUITE = {suite!r}

for dag_id, path in (
    ("etl_daily_tests", f"{{SUITE}}/test_checkout.py"),
    ("api_gateway_tests", f"{{SUITE}}/test_gateway.py"),
):
    with DAG(
        dag_id,
        start_date=datetime(2026, 1, 1),
        schedule=None,
        catchup=False,
        is_paused_upon_creation=False,
        tags=["pytest"],
    ) as dag:
        PytestOperator(
            task_id="suite",
            test_path=path,
            parser=ArchivingResultParser(allure=True, coverage=True, coverage_source="."),
        )
    globals()[dag_id] = dag
"""


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


work = pathlib.Path(tempfile.mkdtemp(prefix="apx-demo-"))
(work / "dags").mkdir()
(work / "suite").mkdir()
(work / "reports").mkdir()
for name, body in SUITES.items():
    (work / "suite" / name).write_text(body, encoding="utf-8")
(work / "dags" / "demo.py").write_text(
    DAG_FILE.format(suite=str(work / "suite")), encoding="utf-8"
)

# Prior history, so the board opens with a story (a chart worth scrolling, flaky tests, a
# heatmap) instead of the two runs we are about to trigger. The two extra suites are never
# triggered here, so their newest run stays broken -- that keeps the Failures KPI and the
# error clusters populated, the way a real board almost always is.
c._seed(
    str(work / "reports"),
    [(d, True) for d in (*DAGS, "payments_e2e", "search_indexing")],
    18,
)

port = free_port()
env = dict(os.environ)
env.update(
    {
        "PATH": f"{VENV_BIN}{os.pathsep}{env.get('PATH', '')}",
        "AIRFLOW_HOME": str(work / "home"),
        "AIRFLOW__CORE__DAGS_FOLDER": str(work / "dags"),
        "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
        "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS": "True",
        "AIRFLOW__API__PORT": str(port),
        "AIRFLOW__CORE__EXECUTION_API_SERVER_URL": f"http://127.0.0.1:{port}/execution/",
        "AIRFLOW_PYTEST_REPORTS_ROOT": str(work / "reports"),
    }
)
base = f"http://127.0.0.1:{port}"
print("booting Airflow ...")
proc = subprocess.Popen(
    [str(VENV_BIN / "airflow"), "standalone"],
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
for _ in range(120):
    try:
        urllib.request.urlopen(base + "/api/v2/version", timeout=2)
        break
    except Exception:
        time.sleep(1)
else:
    proc.terminate()
    sys.exit("Airflow did not come up; check PATH and the api-server port.")
time.sleep(6)  # let the dag-processor pick the two DAGs up
print("  up on", base)


def reports_count() -> int:
    return len(list((work / "reports").rglob("meta.json")))


before = reports_count()
video_dir = work / "video"

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-US",  # the plugin follows Airflow's language; keep the demo English
        record_video_dir=str(video_dir),
        record_video_size={"width": 1280, "height": 800},
    )
    pg = ctx.new_page()

    # 1. Airflow's DAG list: two suites wired to the operator.
    pg.goto(f"{base}/dags")
    pg.wait_for_selector('[data-testid="trigger-dag-button"]')
    pg.wait_for_timeout(2200)

    # 2. Trigger both, the way a user does: play button -> confirm.
    for i in range(2):
        pg.locator('[data-testid="trigger-dag-button"]').nth(i).click()
        pg.wait_for_selector('[data-testid="trigger-dag-submit"]')
        pg.wait_for_timeout(700)
        pg.locator('[data-testid="trigger-dag-submit"]').click()
        pg.wait_for_timeout(1400)

    # 3. Wait for the operator to actually archive both runs.
    print("  waiting for the runs to finish ...")
    for _ in range(90):
        if reports_count() >= before + 2:
            break
        pg.wait_for_timeout(1000)
    pg.reload()
    pg.wait_for_timeout(2600)  # the rows go green

    # 4. Into the plugin, from Airflow's own sidebar.
    pg.click('a[href="/plugin/pytest-reports"]')
    pg.wait_for_selector("iframe", timeout=30000)
    frame = pg.frame_locator("iframe")
    frame.locator("#kpis .kpi").first.wait_for(timeout=30000)
    pg.wait_for_timeout(2600)

    # 5. Tour the board.
    frame.locator("#settings-btn").click()  # the 0.6.2 settings card
    pg.wait_for_timeout(1600)
    frame.locator("#settings-info").click()
    pg.wait_for_timeout(2400)
    frame.locator("#panel-info-close").click()
    pg.wait_for_timeout(500)
    frame.locator("#settings-close").click()
    pg.wait_for_timeout(900)

    frame.locator(f"tr.lgrp:has-text('{DAGS[0]}')").first.click()  # expand the group
    pg.wait_for_timeout(1100)
    frame.locator("tr.clickable").first.click()  # newest run = the one just triggered
    frame.locator(".donut-pct").wait_for(timeout=20000)
    pg.wait_for_timeout(2800)
    frame.locator("#flk-btn").click()  # flaky tests
    pg.wait_for_timeout(2400)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(600)
    frame.locator("#hm-btn").click()  # test x run heatmap
    pg.wait_for_timeout(2600)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(900)

    frame.locator("#kpi-failures").click()  # failures, clustered by error
    pg.wait_for_timeout(2400)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(1500)

    ctx.close()  # flushes the video
    browser.close()
proc.terminate()

webm = next(video_dir.glob("*.webm"))
print("  video:", round(webm.stat().st_size / 1024 / 1024, 1), "MiB")

# WebP keeps the 11 fps cadence while encoding unchanged regions efficiently. At README
# display sizes, 800 px and the text preset keep the UI legible without GIF's palette cost.
vf = "fps=11,scale=800:-2:flags=lanczos"
OUT.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-i",
        str(webm),
        "-vf",
        vf,
        "-c:v",
        "libwebp_anim",
        "-lossless",
        "0",
        "-preset",
        "text",
        "-quality",
        "75",
        "-loop",
        "0",
        "-an",
        str(OUT),
    ],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print(f"  -> {OUT.relative_to(REPO)}  {OUT.stat().st_size / 1024 / 1024:.1f} MiB")
shutil.rmtree(work, ignore_errors=True)
print("done")
