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

"""Playwright UI regression tests for the viewer dashboard.

Opt-in (marker ``ui``); run with the ``ui-test`` extra installed:
    pip install -e '.[web,ui-test]' && playwright install chromium
    pytest -m ui
Each test loads a fresh dashboard (selection/scroll state resets on reload) backed by the
deterministic seed in ``conftest.py`` and asserts on stable hooks (ids / data-* / geometry)
rather than translatable text, so they don't break on copy or locale changes.
"""

from __future__ import annotations

import math

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui


def _kpi(page, kid: str) -> str:
    return page.locator(f"#{kid} .value").inner_text().strip()


def test_dashboard_loads_with_no_js_errors(dash):
    page = dash.page
    expect(page.locator("#kpis")).to_be_visible()
    expect(page.locator(".chart-bars")).to_be_visible()
    expect(page.locator("#flaky-list")).to_be_visible()
    assert page.locator("#kpis .kpi").count() == 5
    assert dash.errors == [], f"JS/console errors on load: {dash.errors}"


def test_failures_kpi_reflects_current_state(dash):
    # Only "alpha"'s latest run is broken (1 failed + 1 error); beta/gamma are green.
    assert _kpi(dash.page, "kpi-failures") == "2"


def test_slowdowns_kpi_counts_regressions(dash):
    val = dash.page.locator("#kpi-slow .value")
    expect(val).not_to_have_text("…", timeout=15000)  # loads async
    assert val.inner_text().strip() == "1"


def test_unique_tests_kpi_loads(dash):
    val = dash.page.locator("#kpi-unique .value")
    expect(val).not_to_have_text("…", timeout=15000)
    assert int(val.inner_text().strip()) > 0


def test_donut_small_slices_do_not_overlap(dash):
    """Regression guard: a tiny fail/error share must stay a separated dot, never overlap."""
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")  # expand the group
    page.locator(
        "tr.clickable"
    ).first.click()  # its newest run (17 pass / 1 fail / 1 error)
    page.wait_for_selector(".dseg")
    segs = page.eval_on_selector_all(
        ".dseg",
        "els => els.map(c => ({"
        " drawn: parseFloat(c.getAttribute('stroke-dasharray').split(' ')[0]),"
        " start: -parseFloat(c.getAttribute('stroke-dashoffset')),"
        " status: c.getAttribute('data-status')}))",
    )
    assert len(segs) >= 3, f"expected pass+fail+error slices, got {segs}"
    SW, C = 12, 2 * math.pi * 50
    segs.sort(key=lambda s: s["start"])
    for a, b in zip(segs, segs[1:], strict=False):
        gap = b["start"] - (a["start"] + a["drawn"])
        assert gap >= SW - 1, f"{a['status']}->{b['status']} overlap: gap={gap:.1f}px"
    wrap = (segs[0]["start"] + C) - (segs[-1]["start"] + segs[-1]["drawn"])
    assert wrap >= SW - 1, f"wrap-around overlap: gap={wrap:.1f}px"


def test_run_detail_opens_with_donut(dash):
    page = dash.page
    page.click("tr.lgrp:has-text('beta')")
    page.locator("tr.clickable").first.click()
    expect(page.locator(".donut-pct")).to_be_visible()
    assert page.locator(".dseg").count() >= 1


def test_group_selection_scopes_chart_flaky_and_kpis(dash):
    page = dash.page
    # Baseline: 3 flaky (one per group), 2 current failures (alpha only). expect() waits
    # for the flaky panel's async load (one-shot reads race on slow CI).
    expect(page.locator("#flaky-count")).to_have_text("3")
    expect(page.locator("#kpi-failures .value")).to_have_text("2")
    # Scope to "beta" (a green-latest group): the whole board narrows to it.
    page.locator("tr.lgrp:has-text('beta') .gsel").check()
    expect(page.locator("#flk-scope")).to_be_visible()
    expect(page.locator("#chart-filter")).to_be_visible()
    expect(page.locator("#flaky-count")).to_have_text("1")
    expect(page.locator("#kpi-failures .value")).to_have_text(
        "0"
    )  # beta latest is green


def test_failures_modal_opens_clusters(dash):
    page = dash.page
    page.click("#kpi-failures")
    expect(page.locator("dialog#failures")).to_be_visible()
    page.wait_for_selector("#cl-list .cl-row")
    assert page.locator("#cl-list .cl-row").count() >= 1


def test_slow_modal_opens(dash):
    page = dash.page
    expect(page.locator("#kpi-slow .value")).not_to_have_text("…", timeout=15000)
    page.click("#kpi-slow")
    expect(page.locator("dialog#slow")).to_be_visible()
    page.wait_for_selector("#sl-list")


def test_unique_modal_opens(dash):
    page = dash.page
    expect(page.locator("#kpi-unique .value")).not_to_have_text("…", timeout=15000)
    page.click("#kpi-unique")
    expect(page.locator("dialog#unique")).to_be_visible()


def test_legend_focus_filter_resets(dash):
    page = dash.page
    base = page.locator("tr.lgrp").count()
    assert base == 3
    page.click('#legend button[data-status="passed"]')  # focus -> reset button appears
    expect(page.locator("#legend .leg-reset")).to_be_visible()
    page.click("#legend .leg-reset")
    expect(page.locator("#legend .leg-reset")).to_have_count(0)
    assert page.locator("tr.lgrp").count() == base


def test_chart_trend_toggle_shows_threshold_and_range(dash):
    page = dash.page
    page.check("#trend-toggle")
    expect(page.locator(".trend-thresh span")).to_be_visible()
    assert "/" in page.locator("#chart-range").inner_text()  # "#a–#b / N"
    assert dash.errors == []


def test_mobile_has_no_horizontal_scroll(dash):
    page = dash.page
    page.set_viewport_size({"width": 375, "height": 800})
    page.wait_for_timeout(300)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 2, f"horizontal overflow at 375px: {overflow}px"
    assert dash.errors == []
