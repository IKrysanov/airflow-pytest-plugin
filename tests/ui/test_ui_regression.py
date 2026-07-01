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


def test_flaky_modal_quarantine_badge_sits_under_name(dash):
    # Open a run's Flaky modal; a quarantined test's badge must be on its OWN line UNDER
    # the test name (not inline, where a long name pushes it onto another row).
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")  # expand
    page.locator("tr.clickable").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    page.click("#flk-btn")
    page.wait_for_selector("#flk-list .fk-row")
    row = page.locator(".fk-row:has(.flk-q)").first  # a quarantined flaky test
    expect(row).to_be_visible()
    node = row.locator(".fk-main .node").bounding_box()
    badge = row.locator(".fk-sub .flk-q").bounding_box()
    assert badge["y"] >= node["y"] + node["height"] - 2, (
        "quarantine badge not below the name"
    )


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


def test_chart_tooltip_anchored_above_bars(dash):
    # The runs-chart tooltip pins its Y above the bars (follows the cursor's X only) so it
    # doesn't jump up/down as the cursor sweeps -- regression guard.
    page = dash.page
    page.locator(".chart-bars .bar").first.hover()
    page.wait_for_timeout(450)
    r = page.evaluate(
        "() => { const t=document.getElementById('tip'), s=document.querySelector('.chart-bars');"
        " if(!t || getComputedStyle(t).display==='none') return null;"
        " return {tb: t.getBoundingClientRect().bottom, st: s.getBoundingClientRect().top}; }"
    )
    assert r is not None, "chart tooltip did not show"
    assert r["tb"] <= r["st"] + 2, "tooltip should sit above the bars (stable Y anchor)"


def test_list_header_only_label_sorts(dash):
    # In the run list, clicking the empty header space must NOT sort -- only the label text.
    page = dash.page

    def active():
        return page.evaluate(
            '() => document.querySelector(\'th.gsort[aria-sort="ascending"],'
            "th.gsort[aria-sort=\"descending\"]')?.getAttribute('data-key') || 'none'"
        )

    before = active()
    box = page.locator("th.gsort").nth(1).bounding_box()
    page.mouse.click(
        box["x"] + box["width"] - 5, box["y"] + box["height"] / 2
    )  # empty space
    page.wait_for_timeout(150)
    assert active() == before, "clicking empty header space should not sort"
    page.locator("th.gsort .th-lab").nth(1).click()  # the label itself
    page.wait_for_timeout(150)
    assert active() != before, "clicking the label should sort"


def test_case_table_long_names_wrap(dash):
    # Long test ids wrap (not nowrap) so the Time column stays visible without h-scroll.
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")
    page.locator("tr.clickable").first.click()
    page.wait_for_selector(".case-table tr.case")
    ws = page.eval_on_selector(".case-node", "el => getComputedStyle(el).whiteSpace")
    assert ws == "normal", f"case node should wrap, got white-space:{ws}"
    overflow = page.eval_on_selector(
        ".case-table", "el => el.querySelector('table').scrollWidth - el.clientWidth"
    )
    assert overflow <= 3, f"case table overflows horizontally by {overflow}px"
