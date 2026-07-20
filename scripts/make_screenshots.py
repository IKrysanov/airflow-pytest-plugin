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

"""Regenerate docs/screenshots/*.png.

Boots the standalone dev server on a seeded report tree and drives it with Playwright, so
the images always match the current UI. Run from the repository root:

    pip install -e '.[web,ui-test]' && playwright install chromium
    python scripts/make_screenshots.py

The seed is deliberately RICH -- several suites, ~25 runs each, coverage, Allure results and
an email history -- so the screenshots show what a real, busy install looks like rather than
a bare board with half the benches missing. Tweak SPECS/NRUNS below to change the story.

Email screenshots (email_*.png) are not produced here: they are renderings of the alert
HTML, not the UI, and only need redoing when that template changes.
"""

import json
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
from airflow_pytest_plugin.layout import ALLURE_DIRNAME, META_FILENAME, ReportLayout
from airflow_pytest_plugin.models import ReportRef

OUT = pathlib.Path("docs/screenshots")
root = tempfile.mkdtemp(prefix="shots-")

# A believable board: several suites, a couple of them troubled, ~25 runs each.
SPECS = [
    ("etl_daily", True),
    ("api_gateway", True),
    ("ml_training", False),
    ("reporting", False),
    ("ingest_hourly", True),
    ("smoke_checks", False),
]
NRUNS = 25
c._seed(root, SPECS, NRUNS)
c._add_alert_history(root, "etl_daily", f"r{NRUNS - 1:03d}")

lay = ReportLayout()
for dag, _ in SPECS:
    for i in range(NRUNS):
        d = lay.dir_for(root, ReportRef(dag, f"r{i:03d}", "suite", 1, -1))
        mp = os.path.join(d, META_FILENAME)
        if not os.path.exists(mp):
            continue
        meta = json.load(open(mp))
        # Coverage that drifts per suite, so the card shows both green and red states.
        base = {
            "etl_daily": 0.91,
            "api_gateway": 0.63,
            "ml_training": 0.88,
            "reporting": 0.47,
            "ingest_hourly": 0.86,
            "smoke_checks": 0.79,
        }[dag]
        meta["coverage"] = round(min(0.99, base + (i % 5) * 0.012), 3)
        # Allure results on the newest runs -> the download button is visible.
        if i >= NRUNS - 3:
            ad = os.path.join(d, ALLURE_DIRNAME)
            os.makedirs(ad, exist_ok=True)
            for k in range(3):
                json.dump(
                    {"uuid": f"{dag}-{i}-{k}", "name": f"test_{k}", "status": "passed"},
                    open(os.path.join(ad, f"{k}-result.json"), "w"),
                )
            meta["allure"] = True
        json.dump(meta, open(mp, "w"))

s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
env = dict(os.environ)
env["PYTHONPATH"] = "src"
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
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
base_url = f"http://127.0.0.1:{port}"
for _ in range(80):
    try:
        urllib.request.urlopen(base_url + "/api/health", timeout=1)
        break
    except Exception:
        time.sleep(0.3)


def shot(page, name, sel=None):
    time.sleep(0.8)
    (page.locator(sel) if sel else page).screenshot(path=str(OUT / f"{name}.png"))
    print("  ->", name)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1050}, device_scale_factor=2)
    pg.goto(base_url)
    pg.wait_for_selector("#kpis .kpi")
    pg.wait_for_selector("#kpi-slow .value:not(:has-text('…'))", timeout=20000)
    pg.wait_for_timeout(2500)
    shot(pg, "overview")

    # Settings — the new 0.6.2 feature.
    pg.click("#settings-btn")
    pg.wait_for_timeout(500)
    shot(pg, "settings", "dialog#settings")
    pg.click("#settings-close")
    pg.wait_for_timeout(400)

    # Detail on a run that has coverage + allure + an email history.
    pg.click("tr.lgrp:has-text('etl_daily')")
    pg.locator("tr.clickable").first.click()
    pg.wait_for_selector(".donut-pct")
    pg.wait_for_timeout(900)
    shot(pg, "detail", "dialog#detail")

    pg.click("#flk-btn")
    pg.wait_for_selector("#flk-list .fk-row")
    shot(pg, "flaky", "dialog#flaky")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(400)

    pg.click("#hm-btn")
    pg.wait_for_timeout(1200)
    shot(pg, "heatmap", "dialog#heatmap")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(700)

    pg.click("#kpi-failures")
    pg.wait_for_selector("#cl-list .cl-row")
    shot(pg, "failures", "dialog#failures")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)

    pg.click("#kpi-slow")
    pg.wait_for_selector("#sl-list")
    pg.wait_for_timeout(600)
    shot(pg, "slow", "dialog#slow")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)

    pg.click("#kpi-unique")
    pg.wait_for_selector("dialog#unique")
    pg.wait_for_timeout(600)
    shot(pg, "unique", "dialog#unique")
    pg.keyboard.press("Escape")
    b.close()
proc.terminate()
shutil.rmtree(root, ignore_errors=True)
print("готово")
