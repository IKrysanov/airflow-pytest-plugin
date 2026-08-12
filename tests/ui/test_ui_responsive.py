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

"""Every surface at every width, checked for the one failure a narrow screen shows first.

Horizontal overflow of the *page* is the symptom worth automating: it is objective, it is
what a phone surfaces immediately, and it has a single cause -- something wider than its
parent that was never told it could shrink. A table or a heatmap may of course scroll
inside its own container; that is the design. The body may not.

The dashboard is embedded in Airflow's chrome, so these widths are the viewport the plugin
is handed rather than the device: 360 a phone, 768 a tablet, 1024 a laptop beside Airflow's
navigation, 1280 a desktop.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui

WIDTHS = [
    (360, "phone"),
    (414, "large phone"),
    (768, "tablet"),
    (1024, "laptop"),
    (1280, "desktop"),
]


def _overflow(page) -> int:
    """How many pixels the document is wider than the window, if any."""
    return page.evaluate(
        "() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)"
    )


def _offenders(page) -> list[str]:
    """Name what sticks out, so a failure says what to fix rather than that it broke."""
    return page.evaluate(
        """() => {
            const limit = window.innerWidth;
            const out = [];
            document.querySelectorAll('body *').forEach((el) => {
                const rect = el.getBoundingClientRect();
                if (!rect.width || rect.right <= limit + 1) return;
                out.push(
                    `${el.tagName.toLowerCase()}#${el.id || '-'}` +
                    `.${(el.className || '').toString().slice(0, 24)} ` +
                    `right=${Math.round(rect.right)}`
                );
            });
            return out.slice(0, 6);
        }"""
    )


def _scrolls_itself(page, selector: str) -> bool:
    """Whether the element or an ancestor takes the horizontal scroll on its own."""
    return page.evaluate(
        """(sel) => {
            let el = document.querySelector(sel);
            while (el && el !== document.body) {
                const style = getComputedStyle(el);
                if (style.overflowX === 'auto' || style.overflowX === 'scroll') return true;
                el = el.parentElement;
            }
            return false;
        }""",
        selector,
    )


@pytest.mark.parametrize(("width", "label"), WIDTHS)
def test_the_dashboard_never_scrolls_the_page_sideways(page, base_url, width, label):
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.set_viewport_size({"width": width, "height": 900})
    dash = _load_dash(page, base_url)
    page.wait_for_timeout(150)

    assert _overflow(page) == 0, (
        f"{label} ({width}px): the page is {_overflow(page)}px too wide. {_offenders(page)}"
    )
    assert dash.errors == [], dash.errors


@pytest.mark.parametrize(("width", "label"), [(360, "phone"), (414, "large phone")])
def test_the_run_table_scrolls_itself_rather_than_the_page(
    page, base_url, width, label
):
    """The table is wider than a phone by design; what matters is who scrolls.

    If the table takes the scroll, a reader swipes the columns. If the page takes it, the
    whole dashboard drifts sideways and the header leaves the screen with it.
    """
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.set_viewport_size({"width": width, "height": 900})
    _load_dash(page, base_url)

    assert _overflow(page) == 0, _offenders(page)
    assert _scrolls_itself(page, "table"), (
        f"at {width}px the run table is wider than the screen and nothing around it "
        "scrolls, so the page would have to"
    )


@pytest.mark.parametrize(("width", "label"), WIDTHS)
def test_a_run_detail_fits_every_width(page, base_url, width, label):
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.set_viewport_size({"width": width, "height": 900})
    _load_dash(page, base_url)

    # The name cell, not the row and not its first cell: a row wider than its scroll
    # container has its geometric centre over empty space, so clicking "the row" hits
    # nothing at some widths -- and the first cell is the selection checkbox.
    page.locator("tr.lgrp:has-text('alpha') td:nth-child(2)").first.click()
    page.locator("tr.clickable td:nth-child(2)").first.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    page.wait_for_timeout(150)

    assert _overflow(page) == 0, (
        f"{label} ({width}px): the detail dialog widens the page. {_offenders(page)}"
    )
    box = page.locator("dialog#detail").bounding_box()
    assert box is not None
    assert box["x"] >= -1 and box["x"] + box["width"] <= width + 1, (
        f"the dialog spans {box['x']}..{box['x'] + box['width']} on a {width}px screen"
    )


@pytest.mark.parametrize(("width", "label"), WIDTHS)
def test_the_assistant_panel_fits_every_width(page, assistant_base_url, width, label):
    """The panel floats over the dashboard, which is the easy way to overflow it."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.set_viewport_size({"width": width, "height": 900})
    _load_dash(page, assistant_base_url)

    page.click("#assistant-btn")
    expect(page.locator("#assistant-dialog")).to_be_visible()
    page.wait_for_timeout(150)

    assert _overflow(page) == 0, (
        f"{label} ({width}px): the open panel widens the page. {_offenders(page)}"
    )
    box = page.locator("#assistant-dialog").bounding_box()
    assert box is not None
    assert box["x"] >= -1, f"the panel starts off-screen at {box['x']}"
    assert box["x"] + box["width"] <= width + 1, (
        f"the panel ends at {box['x'] + box['width']} on a {width}px screen"
    )

    # The two controls somebody needs on a phone must be reachable, not merely present.
    for selector in ("#ast-question", "#ast-send"):
        control = page.locator(selector)
        expect(control).to_be_visible()
        spot = control.bounding_box()
        assert spot is not None and spot["width"] > 0
        assert spot["x"] + spot["width"] <= width + 1, f"{selector} runs off {width}px"


@pytest.mark.parametrize(("width", "label"), [(360, "phone"), (768, "tablet")])
def test_the_assistant_context_overview_fits_a_narrow_screen(
    page, assistant_base_url, width, label
):
    """It holds the evidence block, which is the widest text the panel ever shows."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.set_viewport_size({"width": width, "height": 900})
    _load_dash(page, assistant_base_url)

    # The button lists the *selected* reports, so there has to be a selection first.
    page.locator("tr.lgrp:has-text('alpha') .gsel").check()
    page.click("#assistant-btn")
    expect(page.locator("#assistant-dialog")).to_be_visible()

    button = page.locator("#ast-scope-list")
    button.wait_for(state="visible", timeout=10000)
    button.click()
    page.wait_for_timeout(200)

    assert _overflow(page) == 0, (
        f"{label} ({width}px): the context overview widens the page. {_offenders(page)}"
    )
