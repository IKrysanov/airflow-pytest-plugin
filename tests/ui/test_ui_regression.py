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


def test_reliability_trend_renders(dash):
    # A run-health sparkline sits under the radar: a current value, a delta chip, and a line.
    page = dash.page
    expect(page.locator("#rel-trend .rt-spark")).to_be_visible()
    now = int(page.locator(".rt-now").text_content().strip())
    assert 0 <= now <= 100
    # The line has >= 2 points and an even 2px stroke everywhere (non-scaling under the
    # stretched viewBox -> no thickness "walk", the same guarantee as the chart hover ring).
    pts = page.eval_on_selector(".rt-line", "el => el.getAttribute('points')")
    assert pts and len(pts.split()) >= 2
    assert (
        page.eval_on_selector(".rt-line", "el => getComputedStyle(el).strokeWidth")
        == "2px"
    )
    # The delta arrow agrees with its sign class (▲ up / ▼ down / → flat).
    txt = page.locator(".rt-delta").text_content().strip()
    cls = page.get_attribute(".rt-delta", "class")
    arrow = txt[0]
    assert (
        (arrow == "▲" and "rt-up" in cls)
        or (arrow == "▼" and "rt-down" in cls)
        or (arrow == "→" and "rt-flat" in cls)
    ), f"arrow/class mismatch: {txt!r} / {cls}"
    assert dash.errors == []


def test_reliability_trend_declines_on_degrading_history(declining_dash):
    # When run health falls over time, the trend reads as a decline (▼, negative, red).
    page = declining_dash.page
    expect(page.locator("#rel-trend .rt-spark")).to_be_visible()
    txt = page.locator(".rt-delta").text_content().strip()
    cls = page.get_attribute(".rt-delta", "class")
    assert "rt-down" in cls, f"expected a declining trend, got {cls} / {txt!r}"
    assert txt.startswith("▼")
    assert int(re.search(r"-?\d+", txt).group()) < 0
    assert int(page.locator(".rt-now").text_content().strip()) < 100
    assert declining_dash.errors == []


def test_reliability_info_modal_covers_the_trend(dash):
    # The ⓘ popup appends a paragraph explaining the trend (so radar vs trend is self-evident).
    page = dash.page
    page.click("#rel-info-btn")
    expect(page.locator("dialog#rel-info")).to_be_visible()
    page.wait_for_selector("#rel-info-body .rel-info-list li")
    # Two intro paragraphs: the axes intro + the appended trend note.
    assert page.locator("#rel-info-body .rel-info-intro").count() == 2
    assert (
        page.locator("#rel-info-body .rel-info-intro").last.inner_text().strip() != ""
    )


def _open_first_run(page):
    page.click("tr.lgrp:has-text('beta')")  # expand a group
    page.locator("tr.clickable").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()


def test_email_button_hidden_without_transport(dash):
    # The default server has no mail transport -> email_available is false -> button hidden.
    page = dash.page
    _open_first_run(page)
    expect(page.locator("#d-email")).to_be_hidden()
    assert dash.errors == []


def test_alerts_bench_lists_recipients_and_status(dash):
    # The run's toolbar shows an ✉ bench with the send count; clicking it opens the log
    # listing each send's recipients with a delivered ✓ / failed ✗ mark.
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")
    page.locator(
        "tr.clickable"
    ).first.click()  # alpha's newest run carries 2 alert entries
    expect(page.locator("dialog#detail")).to_be_visible()
    btn = page.locator("#alerts-btn")
    expect(btn).to_be_visible()
    assert btn.locator(".af-count").inner_text().strip() == "2"
    btn.click()
    expect(page.locator("dialog#alerts-dlg")).to_be_visible()
    rows = page.locator("#al-list .al-row")
    assert rows.count() == 2
    # Newest first: the manual failed send (2 recipients, ✗) then the auto delivered one (✓).
    first, second = rows.nth(0), rows.nth(1)
    assert (
        "me@example.com" in first.inner_text()
        and "boss@example.com" in first.inner_text()
    )
    expect(first.locator(".al-fail")).to_be_visible()
    assert "team@example.com" in second.inner_text()
    expect(second.locator(".al-ok")).to_be_visible()
    page.click("#al-close")
    expect(page.locator("dialog#alerts-dlg")).to_be_hidden()
    assert dash.errors == []


def test_alerts_bench_absent_without_history(dash):
    # A run that was never emailed shows no ✉ bench at all.
    page = dash.page
    page.click("tr.lgrp:has-text('beta')")
    page.locator("tr.clickable").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    expect(page.locator("#alerts-btn")).to_have_count(0)


def test_trend_shows_its_time_span(dash):
    # The run-health line now carries an explicit time axis: the dates of the first and
    # last run in view sit under the sparkline, so "over time" is visible, not implied.
    page = dash.page
    expect(page.locator("#rel-trend .rt-spark")).to_be_visible()
    labels = page.locator(".rt-axis span")
    assert labels.count() == 2
    assert labels.nth(0).inner_text().strip() != ""
    assert labels.nth(1).inner_text().strip() != ""
    # The axis must sit inside the reliability card (no overflow).
    card = page.locator("#pentagon-card").bounding_box()
    axis = page.locator(".rt-axis").bounding_box()
    assert axis["x"] >= card["x"] - 1
    assert axis["x"] + axis["width"] <= card["x"] + card["width"] + 1


def test_trend_dates_differ_over_a_long_history(large_dash):
    # 3200 runs spread over months: the left (oldest) and right (newest) dates differ.
    page = large_dash.page
    expect(page.locator("#rel-trend .rt-spark")).to_be_visible()
    labels = page.locator(".rt-axis span")
    assert labels.nth(0).inner_text().strip() != labels.nth(1).inner_text().strip()


def test_case_table_sorts_by_outcome(dash):
    # OUTCOME sorts like the other case columns: ascending puts broken tests first,
    # descending puts passing ones first.
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")
    page.locator("tr.clickable").first.click()  # 17 pass / 1 fail / 1 error
    expect(page.locator("dialog#detail")).to_be_visible()
    page.wait_for_selector("#case-head th.sortable[data-key='outcome']")
    page.click("#case-head th.sortable[data-key='outcome']")  # asc: worst first
    first_badge = (
        page.locator("#d-body tbody tr").first.locator("td").first.inner_text()
    )
    assert "pass" not in first_badge.lower(), f"worst-first sort, got {first_badge!r}"
    page.click("#case-head th.sortable[data-key='outcome']")  # desc: passing first
    first_badge = (
        page.locator("#d-body tbody tr").first.locator("td").first.inner_text()
    )
    assert "pass" in first_badge.lower(), f"passing-first sort, got {first_badge!r}"
    assert dash.errors == []


def test_email_dialog_validates_client_side_before_any_request(email_dash):
    # A malformed recipient is rejected INSTANTLY in the dialog (readable message naming the
    # address) and no request is even sent -- the server still re-validates as defence.
    page = email_dash.page
    _open_first_run(page)
    expect(page.locator("#d-email")).to_be_visible()
    page.click("#d-email")
    expect(page.locator("dialog#email-dlg")).to_be_visible()
    posts: list = []
    page.on(
        "request",
        lambda r: (
            posts.append(r.url) if "/email" in r.url and r.method == "POST" else None
        ),
    )
    page.fill("#em-to", "good@example.com, not-an-email")
    page.click("#em-send")
    expect(page.locator("#em-status.err")).to_be_visible()
    assert (
        "not-an-email" in page.locator("#em-status").inner_text()
    )  # names the bad address
    page.wait_for_timeout(300)
    assert posts == [], "invalid input must never reach the server"
    page.click("#em-cancel")
    expect(page.locator("dialog#email-dlg")).to_be_hidden()
    assert email_dash.errors == []  # no console 400s: nothing was sent


def test_email_dialog_dedupes_duplicate_addresses(email_dash):
    # Two identical addresses (any case) -> the request carries the mailbox once.
    page = email_dash.page
    _open_first_run(page)
    page.click("#d-email")
    expect(page.locator("dialog#email-dlg")).to_be_visible()
    payloads: list = []
    page.on(
        "request",
        lambda r: (
            payloads.append(r.post_data)
            if "/email" in r.url and r.method == "POST"
            else None
        ),
    )
    page.fill("#em-to", "dup@example.com, DUP@example.com; dup@example.com")
    page.click("#em-send")
    expect(page.locator("#em-status")).to_be_visible()
    page.wait_for_timeout(400)
    assert len(payloads) == 1
    assert (
        payloads[0].count("dup@example.com") + payloads[0].count("DUP@example.com") == 1
    )


def test_toolbar_buttons_adapt_to_any_viewport(dash):
    # A run accumulates many toolbar actions (links, compare, flaky, heatmap, clusters,
    # emails) -- at ANY width they must wrap into rows without overlapping or overflowing.
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")
    page.locator("tr.clickable").first.click()  # the busiest run (incl. the ✉ bench)
    expect(page.locator("dialog#detail")).to_be_visible()
    for width in (1280, 900, 640, 480, 375):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(200)
        geo = page.evaluate(
            "() => { const d=document.getElementById('detail');"
            " const boxes=[...d.querySelectorAll('.af-link')].map(e=>e.getBoundingClientRect());"
            " let overlap=false;"
            " for (let i=0;i<boxes.length;i++) for (let j=i+1;j<boxes.length;j++) {"
            "   const a=boxes[i], b=boxes[j];"
            "   if (a.left < b.right-1 && b.left < a.right-1 && a.top < b.bottom-1 && b.top < a.bottom-1) overlap=true; }"
            " const dr=d.getBoundingClientRect();"
            " const outside=boxes.some(b=>b.right > dr.right+1 || b.left < dr.left-1);"
            " return {n: boxes.length, overlap, outside,"
            "  hscroll: d.scrollWidth - d.clientWidth}; }"
        )
        assert geo["n"] >= 5, f"expected a busy toolbar, got {geo['n']} buttons"
        assert not geo["overlap"], f"toolbar buttons overlap at {width}px"
        assert not geo["outside"], (
            f"toolbar buttons spill out of the dialog at {width}px"
        )
        assert geo["hscroll"] <= 2, (
            f"horizontal scroll at {width}px: {geo['hscroll']}px"
        )
    assert dash.errors == []


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
