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
import re

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


def test_chart_tooltip_below_left_of_cursor(dash):
    # The runs-chart tooltip appears just BELOW the cursor, offset to its left (flips to the
    # right only near the left edge). Regression guard against the old "pinned far above" look.
    page = dash.page
    # Hover a bar toward the right so there's room on the left for the tooltip.
    bars = page.locator(".chart-bars .bar")
    n = bars.count()
    box = bars.nth(max(0, n - 2)).bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.wait_for_timeout(500)
    r = page.evaluate(
        "() => { const t=document.getElementById('tip');"
        " if(!t || getComputedStyle(t).display==='none') return null;"
        " const b=t.getBoundingClientRect(); return {top: b.top, right: b.right}; }"
    )
    assert r is not None, "chart tooltip did not show"
    assert r["top"] > cy, "tooltip should sit below the cursor"
    assert r["right"] <= cx + 2, "tooltip should sit to the left of the cursor"


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


def test_group_flaky_chip_shown_for_flaky_groups(dash):
    # Every seeded group has a flaky test -> each group row shows the amber warning chip
    # (with a warning icon). Guard for the per-group flaky indicator.
    page = dash.page
    expect(page.locator("tr.lgrp")).to_have_count(3)
    chips = page.locator(".lgrp-flk")
    expect(chips).to_have_count(3)
    assert chips.first.locator("svg").count() == 1  # warning triangle icon


def test_nested_modal_single_dim(dash):
    # A popup opened from inside the run detail must not stack a second dim -- exactly one
    # full-screen overlay regardless of how many dialogs are open. Regression for double-dark.
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")
    page.locator("tr.clickable").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    page.click("#hm-btn")
    expect(page.locator("dialog#heatmap")).to_be_visible()
    open_dialogs = page.evaluate(
        "() => [...document.querySelectorAll('dialog')].filter(d => d.open).length"
    )
    assert open_dialogs == 2, "both the detail and the heatmap should be open"
    assert page.locator("#apx-local-dim").count() == 1, "dim must not double up"


def test_cluster_status_square_does_not_shrink(dash):
    # In the failure-clusters list a long test name wraps -- the status square must keep its
    # fixed size (flex:0 0 auto), not get squeezed by the wrapping name.
    page = dash.page
    page.click("#kpi-failures")
    expect(page.locator("dialog#failures")).to_be_visible()
    page.wait_for_selector("#cl-list .cl-row")
    page.locator("#cl-list .cl-row").first.click()
    page.wait_for_selector(".cl-item .od")
    st = page.eval_on_selector(
        ".cl-item .od",
        "el => ({shrink: getComputedStyle(el).flexShrink,"
        " w: Math.round(el.getBoundingClientRect().width),"
        " h: Math.round(el.getBoundingClientRect().height)})",
    )
    assert st["shrink"] == "0", "status square must not shrink"
    assert st["w"] == 9 and st["h"] == 9, f"status square should stay 9x9, got {st}"


def test_flaky_ui_absent_when_no_flaky(green_dash):
    # No flaky anywhere: the flaky panel is dropped, the runs chart takes the full board
    # width, and no group shows a flaky chip.
    page = green_dash.page
    expect(page.locator("#flaky-card")).to_be_hidden()
    full = page.evaluate(
        "() => { const c=document.getElementById('chart-card'),"
        " b=document.getElementById('board');"
        " return Math.abs(c.getBoundingClientRect().width - b.getBoundingClientRect().width)"
        " <= 2; }"
    )
    assert full, "chart should span the full board width when the flaky panel is hidden"
    assert page.locator(".lgrp-flk").count() == 0, (
        "no flaky chips when nothing is flaky"
    )
    assert green_dash.errors == [], f"JS/console errors: {green_dash.errors}"


def test_flk_button_absent_in_run_with_no_flaky(green_dash):
    # Opening a run whose dag·task has no flaky tests must NOT show the "Flaky tests" button.
    page = green_dash.page
    page.locator("tr.lgrp").first.click()
    page.locator("tr.clickable").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    assert page.locator("#flk-btn").count() == 0


def test_unique_history_merges_across_dag_tasks(dash):
    # Opening a test's history from the Unique-tests list shows the MERGED timeline across
    # every dag·task the node ran in -- each row is tagged with its dag·task (.hist-loc),
    # which is rendered ONLY in merged mode (scoped history omits it).
    page = dash.page
    expect(page.locator("#kpi-unique .value")).not_to_have_text("…", timeout=15000)
    page.click("#kpi-unique")
    expect(page.locator("dialog#unique")).to_be_visible()
    page.wait_for_selector(".uq-row")
    row = page.locator(".uq-row").first
    expect(row).to_be_visible()
    page.wait_for_timeout(
        300
    )  # let the async catalogue settle so the row doesn't detach
    row.click()
    expect(page.locator("dialog#history")).to_be_visible()
    page.wait_for_selector(".hist-row")
    assert page.locator(".hist-row .hist-loc").count() > 0, (
        "merged history should tag each run with its dag·task"
    )


def test_history_shows_run_count(dash):
    # The history modal states over how many runs the (capped) timeline is shown.
    page = dash.page
    expect(page.locator("#flaky-count")).to_have_text("3")  # flaky loaded
    page.locator("#flaky-list .fb-row").first.click()
    expect(page.locator("dialog#history")).to_be_visible()
    page.wait_for_selector(".hist-count")
    assert page.locator(".hist-row").count() >= 1
    assert re.search(r"\d", page.locator(".hist-count").inner_text())


def test_reliability_pentagon_renders(dash):
    # The 3rd main-board dashboard: a 5-axis reliability radar under the chart.
    page = dash.page
    expect(page.locator("#board2")).to_be_visible()
    expect(page.locator(".rel-svg")).to_be_visible()
    assert page.locator(".rel-lab").count() == 5, "pentagon has 5 axes"
    score = int(page.locator(".rel-score").text_content().strip())  # SVG <text>
    assert 0 <= score <= 100
    # It sits on its own row UNDER the full-width chart, narrower than it (shares the row with
    # flaky), and its labels stay inside the SVG viewBox (adaptive -> never clipped).
    geo = page.evaluate(
        "() => { const c=document.getElementById('chart-card').getBoundingClientRect(),"
        " p=document.getElementById('pentagon-card').getBoundingClientRect(),"
        " svg=document.querySelector('.rel-svg'), vb=svg.viewBox.baseVal;"
        " let lo=1e9, hi=-1e9;"
        " svg.querySelectorAll('.rel-lab').forEach(t => { const b=t.getBBox();"
        " lo=Math.min(lo,b.x); hi=Math.max(hi,b.x+b.width); });"
        " return {below: p.top >= c.bottom - 2, narrower: p.width < c.width - 40,"
        " labelsFit: lo >= 0 && hi <= vb.width}; }"
    )
    assert geo["below"], "radar should sit under the chart"
    assert geo["narrower"], "radar should be narrower than the full-width chart"
    assert geo["labelsFit"], "radar labels should stay inside the viewBox (adaptive)"
    assert dash.errors == [], f"JS/console errors: {dash.errors}"


def test_reliability_pentagon_scopes_to_selection(dash):
    # Selecting a group scopes the radar (like the chart/flaky) and shows the scope chip.
    page = dash.page
    expect(page.locator(".rel-svg")).to_be_visible()
    page.locator("tr.lgrp:has-text('beta') .gsel").check()
    expect(page.locator("#rel-scope")).to_be_visible()
    expect(page.locator(".rel-svg")).to_be_visible()  # still rendered after re-scope
    assert dash.errors == []


def test_reliability_info_modal_explains_each_metric(dash):
    # The ⓘ button opens a popup describing all five axes (with their live values).
    page = dash.page
    page.click("#rel-info-btn")
    expect(page.locator("dialog#rel-info")).to_be_visible()
    page.wait_for_selector("#rel-info-body .rel-info-list li")
    assert page.locator("#rel-info-body .rel-info-list li").count() == 5
    assert page.locator("#rel-info-body .ri-desc").first.inner_text().strip() != ""
    assert dash.errors == []


def test_kpi_all_chip_on_global_counters(dash):
    # RUNS + PASSING RUNS carry an "all" chip: they count every run in view and ignore a
    # group selection (unlike the scoped Failures/Slowdowns).
    page = dash.page
    expect(page.locator("#kpis .kpi-all")).to_have_count(2)


def test_panel_info_popups_open(dash):
    # ⓘ on the runs chart and the flaky panel each open a description popup.
    page = dash.page
    page.click("#chart-info")
    expect(page.locator("dialog#panel-info")).to_be_visible()
    assert page.locator("#panel-info-body p").inner_text().strip() != ""
    page.click("#panel-info-close")
    expect(page.locator("dialog#panel-info")).to_be_hidden()
    page.click("#flaky-info")
    expect(page.locator("dialog#panel-info")).to_be_visible()
    assert page.locator("#panel-info-body p").inner_text().strip() != ""
    assert dash.errors == []


def test_radar_pass_rate_matches_chart_avg_for_a_group(dash):
    # The radar's Pass rate uses the SAME per-run-mean formula as the chart's "avg pass rate",
    # so scoping to one group (whose runs all fit the chart window) reads identically on both.
    page = dash.page
    page.locator("tr.lgrp:has-text('alpha') .gsel").check()
    page.check("#trend-toggle")
    expect(page.locator("#chart-avg")).to_be_visible()
    chart_avg = int(
        re.search(r"(\d+)", page.locator("#chart-avg").inner_text()).group(1)
    )
    radar_pass = int(
        page.locator(".rel-val").first.text_content().strip()
    )  # first axis = pass
    assert abs(chart_avg - radar_pass) <= 1, (
        f"chart avg {chart_avg}% vs radar pass {radar_pass}"
    )


def test_radar_pass_rate_matches_chart_avg_globally(dash):
    # With no selection the chart's avg pass rate now spans ALL runs (not just the visible
    # window), so it equals the radar's Pass rate exactly.
    page = dash.page
    page.check("#trend-toggle")
    expect(page.locator("#chart-avg")).to_be_visible()
    chart_avg = int(
        re.search(r"(\d+)", page.locator("#chart-avg").inner_text()).group(1)
    )
    radar_pass = int(page.locator(".rel-val").first.text_content().strip())
    assert chart_avg == radar_pass, (
        f"global: chart avg {chart_avg}% vs radar pass {radar_pass}%"
    )


def test_flaky_panel_scrolls_within_bounded_card(large_dash):
    # Many flaky tests: the panel fills its (bounded) card and scrolls INSIDE it, rather than
    # stretching the row to fit every row.
    page = large_dash.page
    expect(page.locator(".flaky-scroll")).to_be_visible()
    r = page.evaluate(
        "() => { const fs=document.querySelector('.flaky-scroll'),"
        " fc=document.getElementById('flaky-card');"
        " return {cardH: fc.getBoundingClientRect().height,"
        " scrollable: fs.scrollHeight > fs.clientHeight + 2}; }"
    )
    assert r["cardH"] < 600, f"flaky card must stay bounded, got {r['cardH']}px"
    assert r["scrollable"], "a long flaky list should scroll inside the card"


def test_malicious_test_name_and_message_are_escaped(evil_dash):
    # Security: a test node id / failure message carrying HTML must render as inert text, never
    # execute. Guards the viewer's client-side escaping against stored XSS.
    page = evil_dash.page
    fired = []
    page.on("dialog", lambda d: (fired.append(d.message), d.dismiss()))
    page.click("tr.lgrp")  # expand the evil group
    page.locator("tr.clickable").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    page.wait_for_selector("#detail tr.case")
    page.locator(
        "#detail tr.case"
    ).first.click()  # expand -> render the failure message
    page.wait_for_timeout(300)
    state = page.evaluate(
        "() => ({ xss: !!window.__xss,"
        " injected: document.querySelectorAll('img[onerror], #detail script').length,"
        " node: (document.querySelector('#detail .case-node') || {}).textContent || '' })"
    )
    assert state["xss"] is False, "XSS payload executed"
    assert fired == [], f"unexpected dialog(s): {fired}"
    assert state["injected"] == 0, "hostile HTML was injected as live nodes"
    assert "<script>" in state["node"], "node id should be shown as escaped text"
    assert evil_dash.errors == [], f"JS errors: {evil_dash.errors}"


def test_chart_bar_hover_does_not_change_fill(dash):
    # Hovering a bar must NOT brighten/recolour it (colours "jumping" as you sweep) — it shows
    # a ring instead.
    page = dash.page
    box = page.locator(".chart-bars .bar").nth(3).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(150)
    st = page.evaluate(
        "() => { const el=[...document.querySelectorAll('.bar')].find(e => e.matches(':hover'));"
        " return el ? {filter: getComputedStyle(el).filter,"
        " shadow: getComputedStyle(el).boxShadow} : null; }"
    )
    assert st is not None, "no bar hovered"
    assert st["filter"] in ("none", ""), (
        f"bar hover must not filter the fill, got {st['filter']}"
    )
    assert st["shadow"] not in ("none", ""), "bar hover should show a ring"
