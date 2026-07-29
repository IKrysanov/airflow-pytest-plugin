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

"""Browser checks for bulk deletion.

Every delete here is INTERCEPTED and answered by the test: the report fixtures are
session-scoped, so a real delete would quietly hollow out the suite. What is under test is
the client's side of the contract -- how many requests it sends, how big they are, what it
shows while they run, and what it refuses to do mid-flight.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui

_BATCH = 200  # DELETE_BATCH in the viewer, mirrored by _MAX_DELETE_BATCH server-side


def _capture(page, *, delay_ms: int = 0):
    """Answer every bulk delete with success; return the list of captured payloads."""
    seen: list[list[str]] = []
    singles: list[str] = []

    def bulk(route):
        ids = json.loads(route.request.post_data or "{}").get("ids", [])
        seen.append(ids)
        if delay_ms:
            page.wait_for_timeout(delay_ms)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"deleted": len(ids), "failed": [], "forbidden": []}),
        )

    # A per-run DELETE is the regression this whole endpoint exists to prevent. Registered
    # FIRST: Playwright gives a request to the LAST matching handler, and this pattern also
    # covers the bulk URL -- reversing these two sends the batch to the real server, which
    # would really delete out of a fixture the whole session shares.
    page.route(
        "**/api/reports/*",
        lambda route: (
            singles.append(route.request.url) or route.abort()
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )
    page.route("**/api/reports/delete", bulk)
    return seen, singles


def test_deleting_a_group_sends_batches_not_one_request_per_run(page, large_base_url):
    page.goto(large_base_url)
    page.wait_for_selector("#kpis")
    seen, singles = _capture(page)

    # Three suites at 80 runs each: more than one batch, which is the case a per-run
    # request storm used to turn into a browser-queued wait with no progress shown.
    for i in range(3):
        page.locator(".gsel").nth(i).click()
    expect(page.locator(".bulk-bar")).to_contain_text("240")
    page.click("#bulk-del")
    page.click("#c-ok")
    expect(page.locator("#confirm")).not_to_be_visible()

    assert singles == [], "bulk delete must not fall back to per-run DELETEs"
    assert [len(ids) for ids in seen] == [_BATCH, 40]
    assert len({i for ids in seen for i in ids}) == 240  # every run, exactly once


def test_delete_dialog_reports_progress_and_cannot_be_dismissed_mid_flight(
    page, large_base_url
):
    page.goto(large_base_url)
    page.wait_for_selector("#kpis")
    _capture(page, delay_ms=700)

    for i in range(3):
        page.locator(".gsel").nth(i).click()
    page.click("#bulk-del")
    page.click("#c-ok")

    ok = page.locator("#c-ok")
    expect(ok).to_contain_text("240")  # "Deleting… N of 240", not a bare spinner
    # Escape and a backdrop click would hide the only progress there is, while the
    # deletes keep landing -- leaving a list full of runs that no longer exist.
    page.keyboard.press("Escape")
    page.mouse.click(5, 5)
    expect(page.locator("#confirm")).to_be_visible()
    expect(page.locator("#c-cancel")).to_be_disabled()

    expect(page.locator("#confirm")).not_to_be_visible(timeout=15000)


def test_runs_the_server_refused_stay_in_the_list(page, large_base_url):
    page.goto(large_base_url)
    page.wait_for_selector("#kpis")
    kept: list[str] = []

    def bulk(route):
        ids = json.loads(route.request.post_data or "{}").get("ids", [])
        kept.append(ids[0])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"deleted": len(ids) - 1, "failed": [], "forbidden": [ids[0]]}
            ),
        )

    page.route("**/api/reports/delete", bulk)
    group = page.locator("#list tr.lgrp").first.get_attribute("data-key")
    page.locator(".gsel").first.click()
    page.click("#bulk-del")
    page.click("#c-ok")

    # The dialog stays open naming what survived: a run the user may not delete must not
    # vanish from the list as though it had been.
    expect(page.locator("#c-name")).to_contain_text("1")
    expect(page.locator("#confirm")).to_be_visible()
    page.click("#c-cancel")
    # That suite keeps exactly the run the server refused -- the other 79 left the list.
    left = page.evaluate(
        """(key) => {
          const row = [...document.querySelectorAll('#list tr.lgrp')]
            .find(r => r.getAttribute('data-key') === key);
          return row ? row.cells[3].textContent.trim() : null;
        }""",
        group,
    )
    assert left == "1", f"suite shows {left} runs, expected the one refused"
    assert kept, "the batch never reached the server"


def test_a_busy_server_is_retried_instead_of_reported_as_a_failure(
    page, large_base_url
):
    # The server refuses a bulk delete over its concurrency cap with 503 and deletes
    # nothing, so the batch is safe to send again. Surfacing that as "unconfirmed" would
    # make a cap that protects the API look like data loss.
    attempts = {"n": 0}

    def flaky(route):
        attempts["n"] += 1
        if attempts["n"] == 1:
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": "too many bulk deletes in progress"}),
            )
            return
        ids = json.loads(route.request.post_data or "{}").get("ids", [])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"deleted": len(ids), "failed": [], "forbidden": []}),
        )

    page.goto(large_base_url)
    page.wait_for_selector("#kpis")
    page.route("**/api/reports/delete", flaky)

    page.locator(".gsel").first.click()
    page.click("#bulk-del")
    page.click("#c-ok")

    expect(page.locator("#confirm")).not_to_be_visible(timeout=15000)
    assert attempts["n"] == 2, "the refused batch was not retried"
