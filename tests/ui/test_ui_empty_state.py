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

"""Browser checks for the first-run dashboard state."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui


def test_empty_dashboard_offers_a_localized_accessible_help_link(page, empty_base_url):
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: (
            errors.append(f"console.error: {msg.text}") if msg.type == "error" else None
        ),
    )
    page.set_viewport_size({"width": 375, "height": 760})
    page.goto(empty_base_url)

    empty = page.locator(".report-empty")
    link = page.locator("#empty-help")
    expect(empty).to_be_visible()
    expect(empty.locator(".report-empty-copy strong")).to_have_text("No reports yet")
    expect(link).to_have_text("Open setup guide")
    expect(link).to_have_attribute("href", "/help")
    box = link.bounding_box()
    assert box is not None and box["height"] >= 44
    link.focus()
    expect(link).to_be_focused()
    assert (
        page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 2
    )

    page.evaluate("localStorage.setItem('i18nextLng', 'ru')")
    expect(empty.locator(".report-empty-copy strong")).to_have_text(
        "Отчётов пока нет", timeout=3_000
    )
    expect(link).to_have_text("Открыть руководство")
    link.click()
    page.wait_for_url("**/help")
    expect(page.locator("body")).to_contain_text("Pytest")
    assert errors == []
