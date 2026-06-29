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

"""Playwright UI tests for the test×run heatmap modal.

Opt-in (marker ``ui``). The SMALL seed's "alpha" group is rich: 16 passing tests + a flaky
test (flips by run parity) + a persistently-broken test + an error test + a slow-but-passing
test = 20 tests across 6 runs, every test present in every run. So alpha's matrix is exactly
20 rows × 6 columns with no "didn't run" gaps, and the two all-failing rows sort to the top.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui


def _open_group_heatmap(page, name: str) -> None:
    page.locator(f"tr.lgrp:has-text('{name}') .lgrp-hm").first.click()
    expect(page.locator("dialog#heatmap")).to_be_visible()
    page.wait_for_selector(".hm-cells")


def test_heatmap_opens_from_group_header(dash):
    page = dash.page
    _open_group_heatmap(page, "alpha")
    expect(page.locator(".hm-names .hm-name")).to_have_count(20)  # rows = tests
    expect(page.locator(".hm-rhead")).to_have_count(6)  # columns = runs
    assert dash.errors == [], f"JS/console errors: {dash.errors}"


def test_heatmap_cells_aligned_no_missing(dash):
    page = dash.page
    _open_group_heatmap(page, "alpha")
    # 20 tests × 6 runs, all present -> 120 data cells, zero "didn't run" gaps.
    expect(page.locator(".hm-cells .hm-cell")).to_have_count(120)
    assert page.locator(".hm-cells .hm-miss").count() == 0


def test_heatmap_sorts_most_broken_first(dash):
    page = dash.page
    _open_group_heatmap(page, "alpha")
    first = page.locator(".hm-names .hm-name").first.get_attribute("data-node")
    # broken (all failed) and err (all error) both top the order; node_id breaks the tie.
    assert "test_broken_00" in first


def test_heatmap_name_click_opens_history(dash):
    page = dash.page
    _open_group_heatmap(page, "alpha")
    page.locator(".hm-names .hm-name").first.click()
    expect(page.locator("dialog#history")).to_be_visible()


def test_heatmap_cell_click_opens_run_and_expands_that_test(dash):
    page = dash.page
    _open_group_heatmap(page, "alpha")
    # first row is the all-failing test_broken_00; its first cell -> open that run + jump.
    node = page.locator(".hm-names .hm-name").first.get_attribute("data-node")
    page.locator(".hm-cells .hm-cell:not(.hm-miss)").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    expanded = page.locator('#detail tr.case[aria-expanded="true"]')
    expect(expanded).to_have_count(1)  # the targeted test was auto-expanded
    assert expanded.locator(".case-node").inner_text().strip() == node


def test_heatmap_jittery_click_still_opens_run(dash):
    """A click with a few px of pointer movement (common with a real mouse) must still open
    the run — regression guard for the drag-suppression eating ordinary clicks."""
    page = dash.page
    _open_group_heatmap(page, "alpha")
    box = page.locator(".hm-cells .hm-cell:not(.hm-miss)").first.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 5, cy)  # small jitter
    page.mouse.up()
    expect(page.locator("dialog#detail")).to_be_visible()


def test_heatmap_real_pan_does_not_open_run(large_dash):
    page = large_dash.page
    page.locator("tr.lgrp:has-text('d00') .lgrp-hm").first.click()
    page.wait_for_selector(".hm-cells")
    page.select_option("#hm-win", "100")  # 80 runs -> wide, pannable
    page.wait_for_selector(".hm-cells")
    box = page.locator(".hm-cells .hm-cell:not(.hm-miss)").first.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 60, cy)  # a real horizontal pan
    page.mouse.up()
    page.wait_for_timeout(200)
    expect(page.locator("dialog#heatmap")).to_be_visible()  # still open
    expect(page.locator("dialog#detail")).to_be_hidden()  # the pan didn't open a run


def test_heatmap_embedded_reopen_lifts_iframe(page, base_url):
    """Embedded-in-Airflow guard: the heatmap modal must lift the iframe + dim the parent
    every time it opens (it's registered in updateParentDim). Regression for "open once,
    then clicks fall through to Airflow (вылет на главную)" — the reopen must re-lift."""
    parent = base_url + "/__parent_sim"
    page.route(
        parent,
        lambda r: r.fulfill(
            content_type="text/html",
            body='<!doctype html><body style="margin:0"><iframe id="f" src="'
            + base_url
            + '/" style="width:100vw;height:100vh;border:0"></iframe></body>',
        ),
    )
    page.goto(parent)
    page.wait_for_selector("iframe#f")
    fr = next(
        f for f in page.frames if f.url.startswith(base_url) and "__parent" not in f.url
    )
    fr.wait_for_selector("#kpis:not([hidden])")
    fr.wait_for_selector(".chart-bars")

    def overlay():
        return page.evaluate("() => !!document.getElementById('apx-modal-dim')")

    def open_hm():
        fr.locator("tr.lgrp:has-text('alpha') .lgrp-hm").first.click()
        fr.wait_for_selector(".hm-cells")

    open_hm()
    assert overlay(), "heatmap should dim the parent / lift the iframe"
    fr.locator(".hm-cells .hm-cell:not(.hm-miss)").first.click()
    fr.wait_for_selector("dialog#detail", state="visible")
    fr.locator("#d-close").click()
    fr.wait_for_timeout(150)
    assert not overlay(), "closing should drop the parent dim"
    open_hm()
    assert overlay(), "REOPEN must re-lift the iframe (the bug: it didn't)"
    fr.locator(".hm-cells .hm-cell:not(.hm-miss)").nth(1).click()
    fr.wait_for_selector(
        "dialog#detail", state="visible"
    )  # opens again, no fall-through


def test_heatmap_cell_opens_after_backdrop_close(dash):
    """Closing a run via the BACKDROP (empty area, not the X) must not break the next
    heatmap cell click. Regression: a stale backdrop-close guard + focusCaseRow's synthetic
    tr.click() (coords 0,0 read as 'outside') closed the just-opened detail."""
    page = dash.page
    _open_group_heatmap(page, "alpha")
    page.locator(".hm-cells .hm-cell:not(.hm-miss)").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    page.mouse.click(6, 6)  # close via backdrop (top-left empty area)
    expect(page.locator("dialog#detail")).to_be_hidden()
    # reopen + click another cell -> must still open (was closing itself immediately)
    _open_group_heatmap(page, "alpha")
    page.locator(".hm-cells .hm-cell:not(.hm-miss)").nth(2).click()
    expect(page.locator("dialog#detail")).to_be_visible()


def test_heatmap_first_cell_not_clipped(dash):
    """The first cell must sit inside the scroll pane with room for its hover outline
    (regression for the left-edge clipping)."""
    page = dash.page
    _open_group_heatmap(page, "alpha")
    gap = page.evaluate(
        "() => { const sc=document.querySelector('.hm-scroll'),"
        " c=document.querySelector('.hm-cells .hm-cell');"
        " return Math.round(c.getBoundingClientRect().left - sc.getBoundingClientRect().left); }"
    )
    assert gap >= 3, f"first cell clipped at left edge (gap {gap}px)"


def test_heatmap_legend_focuses_status(dash):
    page = dash.page
    _open_group_heatmap(page, "alpha")
    page.click('#hm-legend button[data-o="f"]')  # focus failures -> dims the rest
    page.wait_for_selector(".hm-cells.foc.foc-f")
    expect(page.locator("#hm-legend .hm-reset")).to_be_visible()
    page.click("#hm-legend .hm-reset")
    expect(page.locator("#hm-legend .hm-reset")).to_have_count(0)
    expect(page.locator(".hm-cells.foc")).to_have_count(0)
    assert dash.errors == [], f"JS/console errors: {dash.errors}"


def test_heatmap_opens_from_run_detail_toolbar(dash):
    page = dash.page
    page.click("tr.lgrp:has-text('alpha')")  # expand the group
    page.locator("tr.clickable").first.click()  # open a run
    expect(page.locator("dialog#detail")).to_be_visible()
    page.click("#hm-btn")
    expect(page.locator("dialog#heatmap")).to_be_visible()
    page.wait_for_selector(".hm-cells")
    assert dash.errors == [], f"JS/console errors: {dash.errors}"


def test_heatmap_window_selector_reloads(dash):
    page = dash.page
    _open_group_heatmap(page, "alpha")
    page.select_option("#hm-win", "10")
    expect(page.locator(".hm-cells")).to_be_visible()
    expect(page.locator(".hm-rhead")).to_have_count(6)  # only 6 runs exist
    assert dash.errors == [], f"JS/console errors: {dash.errors}"


def test_heatmap_mobile_no_page_horizontal_scroll(dash):
    page = dash.page
    page.set_viewport_size({"width": 375, "height": 800})
    _open_group_heatmap(page, "alpha")
    page.wait_for_timeout(200)
    # The wide matrix scrolls inside .hm-scroll; the page itself must not overflow.
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 2, f"page h-scroll at 375px: {overflow}px"
    assert dash.errors == [], f"JS/console errors: {dash.errors}"


def test_heatmap_large_clamps_window_and_caps_rows(large_dash):
    page = large_dash.page
    page.locator("tr.lgrp:has-text('d00') .lgrp-hm").first.click()
    expect(page.locator("dialog#heatmap")).to_be_visible()
    page.wait_for_selector(".hm-cells")
    expect(page.locator(".hm-rhead")).to_have_count(
        30
    )  # window clamps to 30 of 80 runs
    expect(page.locator(".hm-names .hm-name")).to_have_count(20)  # rich group's tests
    assert page.locator(".hm-note").count() == 0  # 20 rows < cap -> not truncated
    assert large_dash.errors == [], f"JS/console errors: {large_dash.errors}"


def test_heatmap_carousel_scrolls_under_fixed_names(large_dash):
    """With many runs the cell pane scrolls horizontally while the name column stays put,
    and cells are clipped by the pane so they can never ride over the names."""
    page = large_dash.page
    page.locator("tr.lgrp:has-text('d00') .lgrp-hm").first.click()
    page.wait_for_selector(".hm-cells")
    page.select_option("#hm-win", "100")  # 80 runs -> pane is far wider than the dialog
    page.wait_for_selector(".hm-cells")
    name_x = page.locator(".hm-names .hm-name").first.bounding_box()["x"]
    page.eval_on_selector(".hm-scroll", "el => { el.scrollLeft = 600; }")
    page.wait_for_timeout(120)
    assert (
        page.eval_on_selector(".hm-scroll", "el => el.scrollLeft") > 100
    )  # it scrolled
    # the name column didn't move, and it sits entirely left of the scrolling pane
    assert (
        abs(page.locator(".hm-names .hm-name").first.bounding_box()["x"] - name_x) <= 1
    )
    names_box = page.locator(".hm-names").bounding_box()
    scroll_box = page.locator(".hm-scroll").bounding_box()
    assert names_box["x"] + names_box["width"] <= scroll_box["x"] + 1, (
        "names overlap the map"
    )
    assert large_dash.errors == [], f"JS/console errors: {large_dash.errors}"
