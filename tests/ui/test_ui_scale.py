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

"""UI regression at scale: the same layout invariants must hold on a LARGE corpus
(40 dag·tasks × 80 runs = 3200 runs) so nothing "разъезжается" on heavy data — the chart
carousel, the long group list, the donut, the KPIs and the mobile layout all stay intact.
"""

from __future__ import annotations

import math

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui

_RICH_NEWEST = (
    "d36"  # newest "rich" group (i%4==0): its latest run has tiny fail/error slices
)


def test_large_dashboard_loads_without_js_errors(large_dash):
    page = large_dash.page
    expect(page.locator("#kpis")).to_be_visible()
    expect(page.locator(".chart-bars")).to_be_visible()
    expect(page.locator("#flaky-list")).to_be_visible()
    assert page.locator("#kpis .kpi").count() == 5
    # Grouped list shows every dag·task header.
    assert page.locator("tr.lgrp").count() == 40
    assert large_dash.errors == [], f"JS/console errors at scale: {large_dash.errors}"


def test_large_kpis_populate(large_dash):
    page = large_dash.page
    # 10 rich groups, each latest run has 1 failed + 1 error -> 20 current failures.
    assert int(page.locator("#kpi-failures .value").inner_text().strip()) == 20
    for kid in ("kpi-slow", "kpi-unique"):
        expect(page.locator(f"#{kid} .value")).not_to_have_text("…", timeout=20000)
        assert int(page.locator(f"#{kid} .value").inner_text().strip()) > 0


def test_large_chart_scrolls_and_window_indicator_updates(large_dash):
    page = large_dash.page
    # 3200 runs >> the visible window -> the carousel is scrollable (arrows render).
    expect(page.locator("#ch-older")).to_be_visible()
    first = page.locator("#chart-range").inner_text()
    assert "/ 3200" in first.replace(" ", "") or "/3200" in first.replace(" ", "")
    page.click("#ch-older")
    page.wait_for_timeout(400)
    assert page.locator("#chart-range").inner_text() != first  # window moved


def test_large_donut_small_slices_do_not_overlap(large_dash):
    page = large_dash.page
    page.click(f"tr.lgrp:has-text('{_RICH_NEWEST}')")  # expand a rich group
    page.locator("tr.clickable").first.click()  # newest run: tiny fail + error slices
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
        assert gap >= SW - 1, (
            f"{a['status']}->{b['status']} overlap at scale: gap={gap:.1f}px"
        )
    wrap = (segs[0]["start"] + C) - (segs[-1]["start"] + segs[-1]["drawn"])
    assert wrap >= SW - 1, f"wrap overlap at scale: gap={wrap:.1f}px"


def test_large_group_selection_scopes_board(large_dash):
    page = large_dash.page
    # Scope to a single green-latest group: the flaky panel + chip narrow to it.
    page.locator("tr.lgrp:has-text('d01') .gsel").check()
    expect(page.locator("#flk-scope")).to_be_visible()
    expect(page.locator("#chart-filter")).to_be_visible()
    assert page.locator("#flaky-count").inner_text().strip() == "1"
    assert (
        page.locator("#kpi-failures .value").inner_text().strip() == "0"
    )  # d01 latest is green


def test_large_failures_modal_renders(large_dash):
    page = large_dash.page
    page.click("#kpi-failures")
    expect(page.locator("dialog#failures")).to_be_visible()
    page.wait_for_selector("#cl-list .cl-row")
    assert page.locator("#cl-list .cl-row").count() >= 1


def test_large_mobile_has_no_horizontal_scroll(large_dash):
    page = large_dash.page
    page.set_viewport_size({"width": 375, "height": 800})
    page.wait_for_timeout(400)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 2, f"horizontal overflow at 375px with 3200 runs: {overflow}px"
    assert large_dash.errors == []
