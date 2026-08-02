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

"""Browser checks for the lazy, read-only report assistant dialog."""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui


def test_assistant_asks_real_offline_api_and_opens_evidence(assistant_dash):
    page = assistant_dash.page
    button = page.locator("#assistant-btn")
    expect(button).to_be_visible()
    expect(button).to_contain_text("AI assistant")

    button.click()
    expect(page.locator("#assistant-dialog")).to_be_visible()
    expect(page.locator("#ast-context")).to_be_hidden()
    expect(page.locator("#ast-title-text")).to_have_text("Report assistant")
    expect(page.locator("#ast-title .ast-beta")).to_have_text("BETA")
    expect(page.locator("#ast-provider")).to_contain_text("fake")
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()

    answer = page.locator(".ast-msg.assistant .ast-answer").last
    expect(answer).to_contain_text("Offline assistant", timeout=15_000)
    prompt_meta = page.locator(".ast-msg.user .ast-msg-meta").last
    expect(prompt_meta).to_contain_text("Sent to LLM")
    rows = prompt_meta.locator(".ast-prompt-row")
    expect(rows).to_have_count(6)
    expect(rows.nth(0)).to_contain_text("System")
    expect(rows.nth(1)).to_contain_text("User")
    expect(rows.nth(2)).to_contain_text("Context data")
    expect(rows.nth(3)).to_contain_text("History")
    expect(rows.nth(3).locator("code")).to_have_text("0 B")
    expect(rows.nth(4)).to_contain_text("Prompt structure")
    expect(rows.nth(5)).to_contain_text("Total")
    expect(rows.nth(5).locator("code")).to_contain_text("KiB")
    answer_meta = page.locator(".ast-msg.assistant .ast-msg-meta").last
    expect(answer_meta).not_to_contain_text("Context was limited")
    expect(page.locator(".ast-msg.assistant .ast-copy").last).to_be_visible()
    limits_box = page.locator(".ast-limit-button").bounding_box()
    send_box = page.locator("#ast-send").bounding_box()
    clear_box = page.locator("#ast-clear").bounding_box()
    assert limits_box is not None and send_box is not None and clear_box is not None
    limits_center = limits_box["y"] + limits_box["height"] / 2
    send_center = send_box["y"] + send_box["height"] / 2
    assert abs(limits_center - send_center) <= 1
    source = page.locator(".ast-source").first
    expect(source).to_be_visible()
    source.click()
    expect(page.locator("dialog#detail")).to_be_visible()
    assert assistant_dash.errors == []


def test_assistant_is_full_width_on_mobile_and_restores_focus(assistant_dash):
    page = assistant_dash.page
    page.set_viewport_size({"width": 375, "height": 800})
    button = page.locator("#assistant-btn")
    expect(button).to_be_visible()
    button.click()

    dialog = page.locator("#assistant-dialog")
    expect(dialog).to_be_visible()
    box = dialog.bounding_box()
    assert box is not None and abs(box["width"] - 375) <= 1
    assert (
        page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 2
    )

    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(button).to_be_focused()
    assert assistant_dash.errors == []


def test_assistant_is_centered_and_restores_its_window_settings(assistant_dash):
    page = assistant_dash.page
    page.set_viewport_size({"width": 1440, "height": 900})
    page.locator("#assistant-btn").click()

    dialog = page.locator("#assistant-dialog")
    expect(dialog).to_be_visible()
    expect(page.locator("#ast-reset-size")).to_have_count(0)
    default_box = dialog.bounding_box()
    assert default_box is not None
    assert default_box["width"] >= 900
    assert abs(default_box["x"] - (1440 - default_box["width"]) / 2) <= 2

    page.evaluate(
        """() => {
          const dialog = document.querySelector("#assistant-dialog");
          dialog.style.width = "820px";
          dialog.style.height = "600px";
        }"""
    )
    page.wait_for_timeout(300)
    resized_box = dialog.bounding_box()
    assert resized_box is not None
    assert abs(resized_box["width"] - 820) <= 2
    assert abs(resized_box["height"] - 600) <= 2

    page.locator("#ast-close").click()
    page.locator("#assistant-btn").click()
    reopened_box = dialog.bounding_box()
    assert reopened_box is not None
    assert abs(reopened_box["width"] - 820) <= 2
    assert abs(reopened_box["height"] - 600) <= 2

    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    expect(dialog).to_be_visible()
    restored_box = dialog.bounding_box()
    assert restored_box is not None
    assert abs(restored_box["width"] - 820) <= 2
    assert abs(restored_box["height"] - 600) <= 2

    assert assistant_dash.errors == []


def test_assistant_scope_updates_as_soon_as_runs_are_selected(assistant_dash):
    page = assistant_dash.page
    page.locator("tr.lgrp:has-text('alpha') .gsel").check()
    page.locator("#assistant-btn").click()

    scope = page.locator("#ast-scope")
    expect(page.locator("#ast-context")).to_be_visible()
    expect(page.locator("#ast-context-label")).to_have_count(0)
    expect(scope).to_contain_text("6")
    expect(scope).not_to_contain_text("alpha")
    processing = page.locator("#ast-processing")
    tooltip = processing.locator("#ast-limit-tooltip")
    expect(tooltip).to_be_hidden()
    copy = tooltip.locator(".ast-processing-copy")
    expect(copy).to_contain_text("Readable in this scope: 6")
    expect(copy.locator("code")).to_have_text("6")
    expect(copy).to_be_hidden()
    limits_button = processing.locator(".ast-limit-button")
    expect(limits_button).to_have_text("Limits")
    expect(processing.locator(".ast-limit-mark")).to_have_count(0)
    expect(limits_button).to_have_attribute("aria-expanded", "false")
    limits_button.hover()
    expect(tooltip).to_be_hidden()
    limits_button.click()
    expect(limits_button).to_have_attribute("aria-expanded", "true")
    expect(tooltip).to_be_visible()
    expect(copy).to_be_visible()
    limits = processing.locator(".ast-limit code")
    expect(limits).to_have_count(4)
    expect(limits.nth(0)).to_have_text("summaries ≤ 100 newest")
    expect(limits.nth(1)).to_have_text("all report evidence in this request ≤ 48 KiB")
    expect(limits.nth(2)).to_have_text("traceback ≤ 3 KiB / test")
    expect(limits.nth(3)).to_have_text("stdout/stderr/log ≤ 2 KiB / test")
    page.locator("#ast-title").click()
    expect(tooltip).to_be_hidden()
    limits_button.focus()
    expect(tooltip).to_be_hidden()
    limits_button.click()
    expect(tooltip).to_be_visible()
    page.keyboard.press("Escape")
    expect(tooltip).to_be_hidden()
    expect(limits_button).to_be_focused()
    view_list = page.locator("#ast-scope-list")
    expect(view_list).to_be_visible()
    page.set_viewport_size({"width": 375, "height": 800})
    limits_button.click()
    expect(tooltip).to_be_visible()
    tooltip_box = tooltip.bounding_box()
    assert tooltip_box is not None
    assert tooltip_box["x"] >= 0
    assert tooltip_box["x"] + tooltip_box["width"] <= 375
    limits_button.click()
    view_list.click()

    dialog = page.locator("#ast-scope-dialog")
    expect(dialog).to_be_visible()
    box = dialog.bounding_box()
    assert box is not None and box["width"] <= 375
    assert (
        page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 2
    )
    expect(dialog.locator(".ast-scope-run")).to_have_count(6)
    expect(dialog).to_contain_text("alpha")
    expect(dialog).to_contain_text("suite")
    expect(dialog).to_contain_text("r005")
    assert assistant_dash.errors == []


def test_assistant_thinking_message_is_a_compact_bubble(assistant_dash):
    page = assistant_dash.page
    held_routes = []

    def hold_reply(route):
        held_routes.append(route)

    page.route("**/api/assistant/query", hold_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Wait for this answer")
    page.locator("#ast-send").click()

    waiting = page.locator(".ast-msg.ast-waiting")
    expect(waiting).to_be_visible()
    expect(waiting.locator(".ast-thinking i")).to_have_count(3)
    expect(waiting.locator(".ast-copy")).to_have_count(0)
    box = waiting.bounding_box()
    assert box is not None and box["width"] < 80

    assert held_routes
    held_routes[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(
            {
                "answer": "Done [R1].",
                "evidence": [],
                "provider": "fake",
                "model": "offline-fake",
                "context_model": None,
                "reports_considered": 1,
                "truncated": False,
                "scope": "all readable reports",
            }
        ),
    )
    expect(waiting).to_have_count(0)
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_have_count(1)
    assert assistant_dash.errors == []


def test_assistant_copies_raw_answer_with_fallback_and_failure_feedback(
    assistant_dash,
):
    page = assistant_dash.page
    raw_answer = "## Result\n\nUse **bold** and `node_id` [R1]."

    def answer_reply(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "answer": raw_answer,
                    "evidence": [],
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": None,
                    "reports_considered": 1,
                    # A long traceback was clipped, but no report/case was lost to the
                    # shared evidence budget. This must not show the scary warning.
                    "truncated": True,
                    "context_limited": False,
                    "scope": "all readable reports",
                    "provider_input_bytes": 1_024,
                    "prompt_bytes": {
                        "system": 1,
                        "user": 1_021,
                        "context": 1,
                        "history": 0,
                        "structure": 1,
                        "total": 1_024,
                    },
                    "token_usage": {
                        "input_tokens": 1_234,
                        "output_tokens": 56,
                        "total_tokens": 1_290,
                        "cached_input_tokens": 0,
                    },
                }
            ),
        )

    page.route("**/api/assistant/query", answer_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Copy this")
    page.locator("#ast-send").click()
    copy = page.locator(".ast-msg.assistant .ast-copy").last
    expect(copy).to_be_visible()
    prompt_rows = page.locator(".ast-msg.user .ast-prompt-row")
    expect(prompt_rows.nth(3).locator("code")).to_have_text("0 B")
    expect(prompt_rows.nth(5).locator("code")).to_have_text("1 KiB")
    answer_meta = page.locator(".ast-msg.assistant .ast-msg-meta").last
    expect(answer_meta).to_contain_text(
        "LLM tokens: input 1,234 · output 56 · total 1,290"
    )
    expect(answer_meta).not_to_contain_text("Context was limited")

    page.evaluate(
        """() => {
          Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: {writeText: async text => { window.__assistantCopied = text; }}
          });
        }"""
    )
    copy.click()
    expect(copy).to_have_text("Copied")
    assert page.evaluate("window.__assistantCopied") == raw_answer

    page.locator("#ast-question").fill("Copy with fallback")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_have_count(2)
    copy = page.locator(".ast-msg.assistant .ast-copy").last
    expect(copy).to_be_visible()

    page.evaluate(
        """() => {
          Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: undefined
          });
          Object.defineProperty(document, "execCommand", {
            configurable: true,
            value: command => {
              window.__assistantLegacyCopied = document.activeElement.value;
              return command === "copy";
            }
          });
        }"""
    )
    assert page.evaluate("navigator.clipboard === undefined") is True
    copy.click()
    page.wait_for_timeout(100)
    expect(copy).to_have_text("Copied")

    page.locator("#ast-question").fill("Copy should fail")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_have_count(3)
    copy = page.locator(".ast-msg.assistant .ast-copy").last
    expect(copy).to_be_visible()
    page.evaluate(
        """Object.defineProperty(document, "execCommand", {
          configurable: true, value: () => false
        })"""
    )
    copy.click()
    expect(copy).to_have_text("Copy failed")
    assert assistant_dash.errors == []


def test_assistant_marks_actual_shared_budget_loss_as_context_limited(
    assistant_dash,
):
    page = assistant_dash.page

    def limited_reply(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "answer": "Only the fitting evidence was inspected [R1].",
                    "evidence": [],
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": None,
                    "reports_considered": 100,
                    "truncated": True,
                    "context_limited": True,
                    "scope": "all readable reports",
                    "token_usage": None,
                }
            ),
        )

    page.route("**/api/assistant/query", limited_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Inspect the full scope")
    page.locator("#ast-send").click()

    meta = page.locator(".ast-msg.assistant .ast-msg-meta").last
    expect(meta).to_contain_text("100 reports · Context was limited")
    assert assistant_dash.errors == []


def test_assistant_prompt_breakdown_counts_followup_history(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()

    for question in ("First question", "Follow-up question"):
        page.locator("#ast-question").fill(question)
        page.locator("#ast-send").click()
        expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
            "Offline assistant", timeout=15_000
        )

    first_history = page.locator(".ast-msg.user .ast-prompt-row").nth(3)
    second_history = page.locator(".ast-msg.user .ast-prompt-row").nth(9)
    expect(first_history.locator("code")).to_have_text("0 B")
    expect(second_history.locator("code")).not_to_have_text("0 B")
    assert assistant_dash.errors == []


def test_assistant_restores_chat_after_refresh_and_can_clear_it(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Keep this answer after refresh")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=15_000
    )

    # Airflow recreates the plugin iframe on a full refresh, so child history.state is
    # not stable even though this tab's sessionStorage is.
    page.evaluate("history.replaceState(null, document.title)")
    page.reload()
    page.wait_for_selector("#kpis:not([hidden])", timeout=20_000)
    expect(page.locator("#assistant-btn")).to_be_visible()
    expect(page.locator("#assistant-dialog")).to_be_visible()
    expect(page.locator(".ast-msg.user .ast-answer")).to_contain_text(
        "Keep this answer"
    )
    expect(page.locator(".ast-msg.assistant .ast-answer")).to_contain_text(
        "Offline assistant"
    )
    restored_meta = page.locator(".ast-msg.user .ast-msg-meta")
    expect(restored_meta).to_contain_text("Sent to LLM")
    expect(restored_meta.locator(".ast-prompt-row")).to_have_count(6)
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_be_visible()

    page.locator("#ast-clear").click()
    expect(page.locator(".ast-msg")).to_have_count(0)
    expect(page.locator(".ast-empty")).to_be_visible()
    assert assistant_dash.errors == []


def test_assistant_does_not_restore_unscoped_legacy_history(assistant_dash):
    page = assistant_dash.page
    page.evaluate(
        """() => {
          const key = "airflow-pytest-plugin:assistant:v1:" + location.pathname
            + ":old-frame-key";
          sessionStorage.setItem(key, JSON.stringify({version: 1, messages: [
            {role: "user", text: "Recovered question", evidence: [], reports: null,
              truncated: false},
            {role: "assistant", text: "## Recovered answer", evidence: [], reports: 2,
              truncated: false}
          ]}));
        }"""
    )

    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    expect(page.locator("#assistant-btn-label")).to_have_text("AI assistant")
    page.locator("#assistant-btn").click()

    expect(page.locator(".ast-msg")).to_have_count(0)
    expect(page.locator(".ast-empty")).to_be_visible()
    expect(page.locator("#ast-clear")).to_be_hidden()
    assert assistant_dash.errors == []


def test_assistant_restores_legacy_total_when_prompt_parts_are_invalid(assistant_dash):
    page = assistant_dash.page
    page.evaluate(
        """async () => {
          const status = await fetch("api/assistant/status").then(response => response.json());
          const key = "airflow-pytest-plugin:assistant:v2:" + location.pathname + ":"
            + status.storage_namespace;
          sessionStorage.setItem(key, JSON.stringify({version: 1, messages: [
            {role: "user", text: "Legacy prompt", evidence: [], reports: null,
              promptBytes: 1023,
              promptParts: {system: -1, user: 1, context: 1, history: 0, structure: 1},
              truncated: false},
            {role: "assistant", text: "Legacy answer", evidence: [], reports: 1,
              truncated: false}
          ]}));
        }"""
    )

    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()
    meta = page.locator(".ast-msg.user .ast-msg-meta")
    expect(meta.locator(".ast-prompt-row")).to_have_count(1)
    expect(meta).to_contain_text("Total")
    expect(meta.locator("code")).to_have_text("1023 B")
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_be_visible()
    assert assistant_dash.errors == []


def test_assistant_controls_follow_airflow_locale_without_refresh(assistant_dash):
    page = assistant_dash.page
    page.evaluate("localStorage.setItem('i18nextLng', 'en')")
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("tr.lgrp:has-text('alpha') .gsel").check()
    page.locator("#assistant-btn").click()
    expect(page.locator("#ast-title-text")).to_have_text("Report assistant")
    expect(page.locator("#ast-title .ast-beta")).to_have_text("BETA")
    expect(page.locator("#ast-send-label")).to_have_text("Send")
    expect(page.locator(".ast-limit-button")).to_have_text("Limits")
    expect(page.locator("#ast-scope-list")).to_have_text("View list")
    expect(page.locator(".ast-limit code").nth(0)).to_have_text(
        "summaries ≤ 100 newest"
    )

    page.evaluate("localStorage.setItem('i18nextLng', 'ru')")
    expect(page.locator("#assistant-btn-label")).to_have_text(
        "AI-ассистент", timeout=3_000
    )
    expect(page.locator("#ast-send-label")).to_have_text("Отправить", timeout=3_000)
    expect(page.locator("#ast-title-text")).to_have_text("Помощник по отчётам")
    expect(page.locator("#ast-title .ast-beta")).to_have_text("BETA")
    expect(page.locator(".ast-limit-button")).to_have_text("Ограничения")
    expect(page.locator("#ast-scope-list")).to_have_text("Список")
    expect(page.locator("#ast-close")).to_have_attribute(
        "aria-label", "Закрыть помощника"
    )
    expect(page.locator(".ast-limit code").nth(0)).to_have_text(
        "сводки ≤ 100 последних"
    )
    expect(page.locator(".ast-limit code").nth(1)).to_have_text(
        "данные всех отчётов в запросе ≤ 48 KiB"
    )

    page.locator("#ast-question").fill("Что отправлено модели?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=15_000
    )
    expect(page.locator(".ast-msg.user .ast-msg-meta").last).to_contain_text(
        "Отправлено в LLM"
    )

    page.locator("#ast-scope-list").click()
    expect(page.locator("#ast-scope-dialog-title")).to_have_text("Выбранные прогоны")
    page.evaluate("localStorage.setItem('i18nextLng', 'en')")
    expect(page.locator("#ast-scope-dialog-title")).to_have_text(
        "Selected runs", timeout=3_000
    )
    expect(page.locator(".ast-msg.user .ast-msg-meta").last).to_contain_text(
        "Sent to LLM"
    )
    page.evaluate("localStorage.removeItem('i18nextLng')")
    assert assistant_dash.errors == []


def test_assistant_renders_safe_markdown_without_executing_model_html(assistant_dash):
    page = assistant_dash.page
    page.set_viewport_size({"width": 800, "height": 800})
    answer = (
        "## What I can do\n\n"
        "1. **Find regressions**\n"
        "2. Show `node_id` values\n\n"
        "| Report | Run | Total | Passed | Failed | Failure |\n"
        "| --- | --- | ---: | ---: | ---: | --- |\n"
        "| [R1] | manual_1 | 8 | 7 | 1 | `assert 1 == 2` |\n"
        "| [R2] | manual_2 | 8 | 7 | 1 | `assert 1 == 2` |\n\n"
        '<img src=x onerror="window.__assistantXss = true">'
    )

    def markdown_reply(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "answer": answer,
                    "evidence": [],
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": None,
                    "reports_considered": 2,
                    "truncated": False,
                    "scope": "all readable reports",
                }
            ),
        )

    page.route("**/api/assistant/query", markdown_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Show markdown")
    page.locator("#ast-send").click()

    rendered = page.locator(".ast-msg.assistant .ast-answer").last
    expect(rendered.locator("h3")).to_have_text("What I can do")
    expect(rendered.locator("ol li")).to_have_count(2)
    expect(rendered.locator("strong")).to_have_text("Find regressions")
    expect(rendered.locator("code").first).to_have_text("node_id")
    expect(rendered.locator("table")).to_have_count(1)
    expect(rendered.locator("thead th")).to_have_count(6)
    expect(rendered.locator("tbody tr")).to_have_count(2)
    table_metrics = rendered.locator(".ast-table-wrap").evaluate(
        "el => ({client: el.clientWidth, scroll: el.scrollWidth})"
    )
    assert table_metrics["scroll"] > table_metrics["client"]
    assert (
        page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 2
    )
    expect(rendered.locator("img")).to_have_count(0)
    expect(rendered).to_contain_text("<img src=x")
    assert page.evaluate("window.__assistantXss === true") is False
    assert assistant_dash.errors == []


def test_assistant_renders_code_after_underscore_labels_and_nested_emphasis(
    assistant_dash,
):
    page = assistant_dash.page
    answer = (
        "- **[R1]** — DAG `pytest_reports_example`, run_id "
        "`manual__2026-08-01T13:49:15+00:00`, task `run_tests`\n"
        "- **Failure in `tests/test_orders.py::test_create`**\n"
        "- Similar model quotes: ´test_api´ and ｀test_worker｀"
    )

    def markdown_reply(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "answer": answer,
                    "evidence": [],
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": None,
                    "reports_considered": 1,
                    "truncated": False,
                    "scope": "all readable reports",
                }
            ),
        )

    page.route("**/api/assistant/query", markdown_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Show identifiers")
    page.locator("#ast-send").click()

    rendered = page.locator(".ast-msg.assistant .ast-answer").last
    expect(rendered.locator("em")).to_have_count(0)
    expect(rendered.locator("code")).to_have_count(6)
    expect(rendered.locator("code").nth(1)).to_have_text(
        "manual__2026-08-01T13:49:15+00:00"
    )
    expect(rendered.locator("strong code")).to_have_text(
        "tests/test_orders.py::test_create"
    )
    assert assistant_dash.errors == []


def test_assistant_explains_local_full_tree_mode_before_submit(assistant_dash):
    page = assistant_dash.page

    def local_status(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": "local.gguf",
                    "context_mode": "local-full-tree",
                    "storage_namespace": "local-ui-test",
                    "max_question_chars": 4000,
                    "max_history_messages": 12,
                    "max_scope_reports": 100,
                    "direct_max_summaries": 100,
                    "direct_max_detail_reports": None,
                    "direct_max_failures_per_report": None,
                    "max_context_bytes": 49_152,
                    "max_failure_bytes": 3_072,
                    "max_capture_bytes": 2_048,
                    "local_complete_tree": True,
                    "local_input_bytes": 9_000,
                }
            ),
        )

    page.route("**/api/assistant/status", local_status)
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()

    processing = page.locator("#ast-processing")
    expect(processing).to_contain_text(
        "local model will process the complete test tree"
    )
    expect(processing).to_contain_text("only compacted evidence leaves the server")
    limits = processing.locator(".ast-limit code")
    expect(limits).to_have_count(5)
    expect(limits.nth(0)).to_have_text("reports processed: 18")
    expect(limits.nth(1)).to_have_text("test cases: all in scope")
    expect(limits.nth(4)).to_have_text("external evidence ≤ 48 KiB")
    assert assistant_dash.errors == []
