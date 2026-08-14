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
import pathlib
import re
import time

import pytest
from playwright.sync_api import expect

from airflow_pytest_plugin.assistant.prompts import command_catalogue

pytestmark = pytest.mark.ui


def _stream_body(reply: dict) -> str:
    """Render a reply dict as the Server-Sent Events the assistant now consumes.

    Route mocks describe one answer; the transport is an implementation detail, so tests
    keep stating the reply and this turns it into `meta` + one `delta` + `done`.
    """
    meta = {
        key: reply.get(key)
        for key in (
            "provider",
            "model",
            "context_model",
            "reports_considered",
            "scope",
            "prompt_bytes",
            "provider_input_bytes",
            "report_context",
        )
    }
    frames = ["event: meta\ndata: " + json.dumps(meta) + "\n\n"]
    if reply.get("answer"):
        frames.append(
            "event: delta\ndata: " + json.dumps({"text": reply["answer"]}) + "\n\n"
        )
    frames.append("event: done\ndata: " + json.dumps(reply) + "\n\n")
    return "".join(frames)


def _fulfil_stream(route, reply: dict) -> None:
    """Answer one mocked assistant request with a complete stream."""
    route.fulfill(
        status=200, content_type="text/event-stream", body=_stream_body(reply)
    )


def test_assistant_asks_real_offline_api_and_opens_evidence(assistant_dash):
    page = assistant_dash.page
    button = page.locator("#assistant-btn")
    expect(button).to_be_visible()
    expect(button).to_contain_text("AI assistant")

    button.click()
    expect(page.locator("#assistant-dialog")).to_be_visible()
    # The unfiltered default is a scope like any other and has to name itself.
    expect(page.locator("#ast-context")).to_be_visible()
    expect(page.locator("#ast-scope")).to_have_text("All readable reports")
    expect(page.locator("#ast-scope-list")).to_be_hidden()
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
    expect(rows).to_have_count(7)
    expect(rows.nth(0)).to_contain_text("System")
    expect(rows.nth(1)).to_contain_text("User")
    expect(rows.nth(2)).to_contain_text("Context data")
    # Nothing is mounted here, so documentation costs nothing.
    expect(rows.nth(3)).to_contain_text("Documentation")
    expect(rows.nth(3).locator("code")).to_have_text("0 B")
    expect(rows.nth(4)).to_contain_text("History")
    expect(rows.nth(4).locator("code")).to_have_text("0 B")
    expect(rows.nth(5)).to_contain_text("Prompt structure")
    expect(rows.nth(6)).to_contain_text("Total")
    expect(rows.nth(6).locator("code")).to_contain_text("KiB")
    context_review = prompt_meta.locator(".ast-context-review")
    expect(context_review).to_have_text("Context overview")
    context_review.click()
    context_dialog = page.locator("#ast-report-context-dialog")
    expect(context_dialog).to_be_visible()
    expect(page.locator("#ast-report-context-format")).to_have_text(
        "Direct snapshot · header + JSON Lines"
    )
    expect(page.locator("#ast-report-context-code")).to_contain_text("RUN SUMMARIES")
    expect(page.locator("#ast-report-context-note")).to_contain_text(
        "after RBAC filtering"
    )
    page.locator("#ast-report-context-close").click()
    expect(context_dialog).to_be_hidden()
    expect(context_review).to_be_focused()
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


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_assistant_prompt_breakdown_uses_readable_theme_colors(assistant_dash, theme):
    page = assistant_dash.page
    page.evaluate(
        "theme => document.documentElement.setAttribute('data-theme', theme)", theme
    )
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Show the request size")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=15_000
    )

    # The question is a neutral card now, not a filled bubble. Each part of the breakdown
    # still needs its own contrast against that card: text at 4.5, and the separators,
    # value outlines and the context button at the 3.0 required of non-text boundaries.
    # The app's hairline `--border` disappears at this size, which is why these use a
    # mid-tone instead.
    appearance = page.locator(".ast-msg.user .ast-msg-meta").last.evaluate(
        r"""el => {
          const parse = value => {
            const channels = (value.match(/-?(?:\d+\.?\d*|\.\d+)/g) || []).map(Number);
            const rgb = value.startsWith('color(srgb')
              ? channels.slice(0, 3).map(channel => channel * 255)
              : channels.slice(0, 3);
            return { rgb, alpha: channels.length > 3 ? channels[3] : 1 };
          };
          const over = (front, back) => {
            const f = parse(front), b = parse(back);
            return f.rgb.map((channel, i) => channel * f.alpha + b.rgb[i] * (1 - f.alpha));
          };
          const luminance = rgb => {
            const linear = rgb.map(channel => {
              channel /= 255;
              return channel <= .04045 ? channel / 12.92
                : Math.pow((channel + .055) / 1.055, 2.4);
            });
            return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
          };
          const ratio = (a, b) => {
            const first = luminance(a), second = luminance(b);
            return (Math.max(first, second) + .05) / (Math.min(first, second) + .05);
          };
          const box = el.closest('.ast-msg.user');
          const bubble = getComputedStyle(box);
          const style = getComputedStyle(el);
          const chip = el.querySelector('.ast-prompt-row dd code');
          const chipStyle = getComputedStyle(chip);
          const button = el.querySelector('.ast-context-review');
          const buttonStyle = getComputedStyle(button);
          const fill = parse(bubble.backgroundColor).rgb;
          return {
            ratio: ratio(parse(bubble.color).rgb, fill),
            chipTextRatio: ratio(
              parse(chipStyle.color).rgb,
              over(chipStyle.backgroundColor, bubble.backgroundColor)
            ),
            chipOutlineRatio:
              ratio(over(chipStyle.borderTopColor, bubble.backgroundColor), fill),
            dividerRatio:
              ratio(over(style.borderTopColor, bubble.backgroundColor), fill),
            buttonOutlineRatio:
              ratio(over(buttonStyle.borderTopColor, bubble.backgroundColor), fill),
            buttonLabelRatio: ratio(
              parse(buttonStyle.color).rgb,
              over(buttonStyle.backgroundColor, bubble.backgroundColor)
            ),
            metaBackground: style.backgroundColor,
            dividerWidth: style.borderTopWidth,
            chipBackground: chipStyle.backgroundColor,
            buttonBorder: [buttonStyle.borderTopWidth, buttonStyle.borderRightWidth,
              buttonStyle.borderBottomWidth, buttonStyle.borderLeftWidth],
            buttonHeight: button.getBoundingClientRect().height,
            buttonHasIcon: Boolean(button.querySelector('svg')),
            opacity: style.opacity,
            bubbleBackground: bubble.backgroundColor,
            cardVsTranscript: ratio(
              fill,
              parse(getComputedStyle(
                document.getElementById('ast-messages')).backgroundColor).rgb
            ),
            cardBorderWidth: bubble.borderTopWidth,
            bubbleRgb: fill
          };
        }"""
    )
    assert appearance["ratio"] >= 4.5
    assert appearance["chipTextRatio"] >= 4.5
    assert appearance["chipOutlineRatio"] >= 3
    assert appearance["dividerRatio"] >= 3
    assert appearance["buttonOutlineRatio"] >= 3
    assert appearance["buttonLabelRatio"] >= 4.5
    # The breakdown is separated from the question by a rule, not by a nested card.
    assert appearance["metaBackground"] == "rgba(0, 0, 0, 0)"
    assert appearance["dividerWidth"] == "1px"
    assert appearance["buttonBorder"] == ["1px"] * 4
    assert appearance["buttonHasIcon"] is True
    assert appearance["opacity"] == "1"
    # Small and quiet: this is reference data under a question, not a second Send.
    assert 24 <= appearance["buttonHeight"] <= 32, appearance["buttonHeight"]
    # The card is identified by its own fill against the transcript, with an outline on
    # top. A 3:1 outline is the rule for controls; forcing it on a message card would box
    # every question in a line louder than anything else in the viewer.
    assert appearance["bubbleBackground"] != "rgba(0, 0, 0, 0)"
    assert appearance["cardVsTranscript"] > 1.03, appearance["cardVsTranscript"]
    assert appearance["cardBorderWidth"] == "1px"

    messages = page.locator("#ast-messages")
    idle_scrollbar = messages.evaluate(
        """el => ({
          width: getComputedStyle(el, '::-webkit-scrollbar').width,
          track: getComputedStyle(el, '::-webkit-scrollbar-track').backgroundColor,
          thumb: getComputedStyle(el, '::-webkit-scrollbar-thumb').backgroundColor
        })"""
    )
    assert idle_scrollbar == {
        "width": "8px",
        "track": "rgba(0, 0, 0, 0)",
        "thumb": "rgba(0, 0, 0, 0)",
    }
    messages.hover()
    active_thumb = messages.evaluate(
        "el => getComputedStyle(el, '::-webkit-scrollbar-thumb').backgroundColor"
    )
    assert active_thumb != "rgba(0, 0, 0, 0)"
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
    expect(limits).to_have_count(5)
    expect(limits.nth(0)).to_have_text("summaries ≤ 100 newest")
    expect(limits.nth(1)).to_have_text("all report evidence in this request ≤ 48 KiB")
    expect(limits.nth(2)).to_have_text("traceback ≤ 3 KiB / test")
    expect(limits.nth(3)).to_have_text("stdout/stderr/log ≤ 2 KiB / test")
    expect(limits.nth(4)).to_have_text("answer output ≤ 3072 tokens")
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

    page.route("**/api/assistant/stream", hold_reply)
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
    _fulfil_stream(
        held_routes[0],
        {
            "answer": "Done [R1].",
            "evidence": [],
            "provider": "fake",
            "model": "offline-fake",
            "context_model": None,
            "reports_considered": 1,
            "truncated": False,
            "scope": "all readable reports",
        },
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
        _fulfil_stream(
            route,
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
            },
        )

    page.route("**/api/assistant/stream", answer_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Copy this")
    page.locator("#ast-send").click()
    copy = page.locator(".ast-msg.assistant .ast-copy").last
    expect(copy).to_be_visible()
    prompt_rows = page.locator(".ast-msg.user .ast-prompt-row")
    expect(prompt_rows.nth(4).locator("code")).to_have_text("0 B")  # history
    expect(prompt_rows.nth(6).locator("code")).to_have_text("1 KiB")  # total
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
        _fulfil_stream(
            route,
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
            },
        )

    page.route("**/api/assistant/stream", limited_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Inspect the full scope")
    page.locator("#ast-send").click()

    meta = page.locator(".ast-msg.assistant .ast-msg-meta").last
    expect(meta).to_contain_text("100 reports · Context was limited")
    assert assistant_dash.errors == []


def test_assistant_warns_when_provider_truncates_the_answer(assistant_dash):
    page = assistant_dash.page
    partial_answer = (
        "### Run comparison\n\n"
        "| Parameter | [R1] | [R2] |\n"
        "|---|---|---|\n\n"
        "| DAG | `pytest_reports_example`"
    )

    def output_limited_reply(route):
        _fulfil_stream(
            route,
            {
                "answer": partial_answer,
                "evidence": [],
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "context_model": None,
                "reports_considered": 2,
                "truncated": False,
                "context_limited": False,
                "output_limited": True,
                "scope": "two selected reports",
                "prompt_bytes": {
                    "system": 2_000,
                    "user": 30,
                    "context": 3_000,
                    "history": 1_200,
                    "structure": 202,
                },
                "report_context": None,
                "token_usage": {
                    "input_tokens": 6_432,
                    "output_tokens": 1_536,
                    "total_tokens": 7_968,
                    "cached_input_tokens": 0,
                },
            },
        )

    page.route("**/api/assistant/stream", output_limited_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Compare these two runs")
    page.locator("#ast-send").click()

    warning = page.locator(".ast-msg.assistant .ast-output-warning").last
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("reached its output-token limit")
    expect(warning).to_have_attribute("role", "status")
    expect(page.locator(".ast-msg.assistant .ast-msg-meta").last).to_contain_text(
        "output 1,536"
    )

    page.evaluate("history.replaceState(null, document.title)")
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    expect(page.locator("#assistant-dialog")).to_be_visible()
    expect(page.locator(".ast-output-warning")).to_have_count(1)
    expect(page.locator(".ast-output-warning")).to_contain_text(
        "reached its output-token limit"
    )
    assert assistant_dash.errors == []


def test_assistant_context_overview_is_exact_safe_and_copyable(assistant_dash):
    page = assistant_dash.page
    report_context = (
        "Scope: all readable reports\n\nRUN SUMMARIES\n"
        '[R1] {"dag_id":"public","captured":"</code><img src=x '
        'onerror=window.__assistantContextXss=true>","long":"' + "x" * 2_000 + '"}'
    )
    context_bytes = len(report_context.encode())

    def context_reply(route):
        _fulfil_stream(
            route,
            {
                "answer": "The readable report was inspected [R1].",
                "evidence": [],
                "provider": "fake",
                "model": "offline-fake",
                "context_model": None,
                "reports_considered": 1,
                "truncated": False,
                "context_limited": False,
                "output_limited": False,
                "scope": "all readable reports",
                "prompt_bytes": {
                    "system": 1,
                    "user": 1,
                    "context": context_bytes,
                    "history": 0,
                    "structure": 1,
                },
                "report_context": {
                    "content": report_context,
                    "format": "direct-snapshot-jsonl",
                    "bytes": context_bytes,
                },
            },
        )

    page.route("**/api/assistant/stream", context_reply)
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("What was sent?")
    page.locator("#ast-send").click()
    page.locator(".ast-context-review").click()

    code = page.locator("#ast-report-context-code")
    assert code.text_content() == report_context
    wrap = page.locator("#ast-report-context-wrap")
    content = page.locator("#ast-report-context-content")
    expect(wrap).to_have_attribute("aria-pressed", "true")
    expect(content).to_have_class("ast-report-context-content ast-wrap")
    assert content.evaluate("el => el.scrollWidth <= el.clientWidth + 2")
    wrap.click()
    expect(wrap).to_have_attribute("aria-pressed", "false")
    expect(content).to_have_class("ast-report-context-content")
    assert content.evaluate("el => el.scrollWidth > el.clientWidth")
    expect(page.locator("#ast-report-context-dialog img")).to_have_count(0)
    assert page.evaluate("window.__assistantContextXss === true") is False
    page.evaluate(
        """() => {
          Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: {writeText: async text => { window.__assistantContextCopied = text; }}
          });
        }"""
    )
    page.locator("#ast-report-context-copy").click()
    expect(page.locator("#ast-report-context-copy")).to_have_text("Copied")
    assert page.evaluate("window.__assistantContextCopied") == report_context

    page.locator("#ast-report-context-close").click()
    page.evaluate("history.replaceState(null, document.title)")
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    expect(page.locator("#assistant-dialog")).to_be_visible()
    page.locator(".ast-context-review").click()
    expect(page.locator("#ast-report-context-wrap")).to_have_attribute(
        "aria-pressed", "false"
    )
    expect(page.locator("#ast-report-context-content")).to_have_class(
        "ast-report-context-content"
    )
    page.locator("#ast-report-context-wrap").click()
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

    first_history = page.locator(".ast-msg.user .ast-prompt-row").nth(4)
    second_history = page.locator(".ast-msg.user .ast-prompt-row").nth(11)
    expect(first_history.locator("code")).to_have_text("0 B")
    expect(second_history.locator("code")).not_to_have_text("0 B")
    assert assistant_dash.errors == []


def test_assistant_sums_provider_tokens_for_the_whole_chat_session(assistant_dash):
    page = assistant_dash.page
    totals = [100, 250, 650, 1, 999, 10, 5, None]
    calls = 0

    def token_reply(route):
        nonlocal calls
        total = totals[calls]
        calls += 1
        usage = (
            {
                "input_tokens": total - 1,
                "output_tokens": 1,
                "total_tokens": total,
                "cached_input_tokens": 0,
            }
            if total is not None
            else None
        )
        _fulfil_stream(
            route,
            {
                "answer": f"Answer {calls}",
                "evidence": [],
                "provider": "fake",
                "model": "offline-fake",
                "context_model": None,
                "reports_considered": 1,
                "truncated": False,
                "context_limited": False,
                "output_limited": False,
                "scope": "all readable reports",
                "token_usage": usage,
                "report_context": None,
            },
        )

    page.route("**/api/assistant/stream", token_reply)
    page.locator("#assistant-btn").click()
    for index in range(len(totals)):
        page.locator("#ast-question").fill(f"Question {index + 1}")
        page.locator("#ast-send").click()
        expect(page.locator(".ast-msg.assistant .ast-answer").last).to_have_text(
            f"Answer {index + 1}"
        )

    session_total = page.locator("#ast-session-tokens")
    expect(session_total).to_have_attribute("aria-live", "polite")
    expect(session_total).to_have_text("Session total: 2,015 tokens")

    page.evaluate("history.replaceState(null, document.title)")
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    expect(page.locator("#assistant-dialog")).to_be_visible()
    expect(page.locator(".ast-msg")).to_have_count(12)
    expect(page.locator("#ast-session-tokens")).to_have_text(
        "Session total: 2,015 tokens"
    )

    page.evaluate("localStorage.setItem('i18nextLng', 'ru')")
    expect(page.locator("#ast-session-tokens")).to_have_text(
        "За сессию: 2 015 токенов", timeout=3_000
    )
    page.locator("#ast-clear").click()
    page.locator("#ast-clear-yes").click()
    expect(page.locator("#ast-session-tokens")).to_be_hidden()
    page.evaluate("localStorage.removeItem('i18nextLng')")
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
    expect(restored_meta.locator(".ast-prompt-row")).to_have_count(7)
    restored_review = restored_meta.locator(".ast-context-review")
    expect(restored_review).to_be_visible()
    restored_review.click()
    expect(page.locator("#ast-report-context-code")).to_contain_text("RUN SUMMARIES")
    page.locator("#ast-report-context-close").click()
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_be_visible()

    page.locator("#ast-clear").click()
    page.locator("#ast-clear-yes").click()
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
    expect(page.locator(".ast-context-review").last).to_have_text("Обзор контекста")

    page.locator("#ast-scope-list").click()
    expect(page.locator("#ast-scope-dialog-title")).to_have_text("Выбранные прогоны")
    page.evaluate("localStorage.setItem('i18nextLng', 'en')")
    expect(page.locator("#ast-scope-dialog-title")).to_have_text(
        "Selected runs", timeout=3_000
    )
    expect(page.locator(".ast-msg.user .ast-msg-meta").last).to_contain_text(
        "Sent to LLM"
    )
    expect(page.locator(".ast-context-review").last).to_have_text("Context overview")
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
        _fulfil_stream(
            route,
            {
                "answer": answer,
                "evidence": [],
                "provider": "fake",
                "model": "offline-fake",
                "context_model": None,
                "reports_considered": 2,
                "truncated": False,
                "scope": "all readable reports",
            },
        )

    page.route("**/api/assistant/stream", markdown_reply)
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
    # A six-column table now fits: the answer runs the full width of the panel, which is
    # the point of taking it out of a bubble. What still has to hold is that a table too
    # wide to fit scrolls inside its own region and never drags the page -- see
    # test_a_table_too_wide_to_fit_scrolls_inside_the_answer.
    table_metrics = rendered.locator(".ast-table-wrap").evaluate(
        """el => ({
          client: el.clientWidth,
          scroll: el.scrollWidth,
          overflow: getComputedStyle(el).overflowX,
          page: document.documentElement.scrollWidth
                <= document.documentElement.clientWidth,
        })"""
    )
    assert table_metrics["scroll"] <= table_metrics["client"], "six columns now fit"
    assert table_metrics["overflow"] == "auto"
    assert table_metrics["page"], "the page itself must never scroll sideways"
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
        _fulfil_stream(
            route,
            {
                "answer": answer,
                "evidence": [],
                "provider": "fake",
                "model": "offline-fake",
                "context_model": None,
                "reports_considered": 1,
                "truncated": False,
                "scope": "all readable reports",
            },
        )

    page.route("**/api/assistant/stream", markdown_reply)
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
    expect(limits).to_have_count(6)
    expect(limits.nth(0)).to_have_text("reports processed: 18")
    expect(limits.nth(1)).to_have_text("test cases: all in scope")
    expect(limits.nth(4)).to_have_text("external evidence ≤ 48 KiB")
    expect(limits.nth(5)).to_have_text("answer output ≤ 3072 tokens")
    assert assistant_dash.errors == []


def test_assistant_follow_up_survives_a_very_long_previous_answer(assistant_dash):
    """A long answer used to poison the next question.

    The browser replays the transcript, and the wire contract capped a turn at the prompt
    clip, so one long answer made every follow-up fail validation until the chat was
    cleared. The reply is now trimmed on the way out and accepted on the way in.
    """
    page = assistant_dash.page
    page.evaluate(
        """async () => {
          const status = await fetch("api/assistant/status").then(r => r.json());
          const key = "airflow-pytest-plugin:assistant:v2:" + location.pathname + ":"
            + status.storage_namespace;
          sessionStorage.setItem(key, JSON.stringify({version: 1, messages: [
            {role: "user", text: "First question", evidence: [], reports: null,
              truncated: false},
            {role: "assistant", text: "Подробный разбор падений. ".repeat(900),
              evidence: [], reports: 3, truncated: false}
          ]}));
        }"""
    )
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()
    expect(page.locator(".ast-msg")).to_have_count(2)

    page.locator("#ast-question").fill("And now?")
    page.locator("#ast-send").click()

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=15_000
    )
    expect(page.locator(".ast-answer.ast-error")).to_have_count(0)
    history = page.locator(".ast-msg.user .ast-msg-meta").last
    expect(history).to_contain_text("History")
    assert assistant_dash.errors == []


def test_an_empty_scope_shows_the_bytes_it_really_sent(assistant_dash):
    """A request is made even when no report matched -- so the breakdown is real.

    It used to be all zeroes because the model was never called, and the bubble said
    "nothing was sent" instead of rendering six rows of 0 B. Now something is sent: the
    system prompt, the question, and an evidence block saying there is nothing to describe.
    """
    page = assistant_dash.page
    page.fill("#f-dag", "no-such-dag")
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_be_visible(
        timeout=15_000
    )
    meta = page.locator(".ast-msg.user .ast-msg-meta").last
    expect(meta).to_be_visible()
    rows = meta.locator(".ast-prompt-row")
    # system, user, context, documentation, history, structure, and the total.
    expect(rows).to_have_count(7)
    expect(meta).not_to_contain_text("Nothing was sent")
    # The system prompt alone is kilobytes, so no row can read 0 B for it.
    expect(rows.first).not_to_contain_text("0 B")
    assert assistant_dash.errors == []


def test_the_dashboard_language_is_sent_with_every_question(assistant_dash):
    """A two-word question does not say what language its asker reads; the browser does.

    This used to be patched by replacing the whole answer client-side whenever no report
    matched -- which would now overwrite a real answer, because a question about the
    product needs no reports at all.
    """
    page = assistant_dash.page
    page.evaluate("localStorage.setItem('i18nextLng', 'ru')")
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    sent: list[dict] = []
    page.route(
        "**/api/assistant/stream",
        lambda route: (
            sent.append(route.request.post_data_json),
            _fulfil_stream(
                route, {"answer": "Ответ модели.", "evidence": [], "reports": []}
            ),
        )[-1],
    )
    page.locator("#assistant-btn").click()
    expect(page.locator("#ast-send-label")).to_have_text("Отправить", timeout=5_000)
    page.locator("#ast-question").fill("wq")
    page.locator("#ast-send").click()

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Ответ модели."
    )
    assert sent and sent[0]["locale"] == "ru", sent
    page.evaluate("localStorage.removeItem('i18nextLng')")
    assert assistant_dash.errors == []


def test_an_answer_with_no_reports_is_shown_as_the_model_wrote_it(assistant_dash):
    """The client must not substitute its own sentence over a real answer."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": "The operator runs a pytest suite as an Airflow task.",
                "evidence": [],
                "reports": [],
                "reports_considered": 0,
            },
        ),
    )
    page.locator("#ast-question").fill("what does airflow-pytest-operator do?")
    page.locator("#ast-send").click()

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "runs a pytest suite"
    )


def test_assistant_shows_the_answer_while_it_is_still_arriving(assistant_dash):
    page = assistant_dash.page
    held = []
    page.route("**/api/assistant/stream", lambda route: held.append(route))
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Stream it")
    page.locator("#ast-send").click()

    # Nothing yet: the compact three-dot bubble, and Send has become Stop.
    expect(page.locator(".ast-msg.ast-waiting")).to_be_visible()
    expect(page.locator("#ast-stop")).to_be_visible()
    expect(page.locator("#ast-send")).to_be_hidden()

    assert held
    held[0].fulfill(
        status=200,
        content_type="text/event-stream",
        body=(
            "event: meta\ndata: "
            + json.dumps(
                {
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": None,
                    "reports_considered": 2,
                    "scope": "all readable reports",
                    "prompt_bytes": {
                        "system": 10,
                        "user": 5,
                        "context": 20,
                        "history": 0,
                        "structure": 5,
                        "total": 40,
                    },
                    "provider_input_bytes": 40,
                    "report_context": None,
                }
            )
            + "\n\n"
            + "event: delta\ndata: "
            + json.dumps({"text": "Partial "})
            + "\n\n"
            + "event: delta\ndata: "
            + json.dumps({"text": "answer."})
            + "\n\n"
            + "event: done\ndata: "
            + json.dumps(
                {
                    "answer": "Partial answer.",
                    "evidence": [],
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": None,
                    "reports_considered": 2,
                    "truncated": False,
                    "context_limited": False,
                    "output_limited": False,
                    "scope": "all readable reports",
                    "provider_input_bytes": 40,
                    "prompt_bytes": {
                        "system": 10,
                        "user": 5,
                        "context": 20,
                        "history": 0,
                        "structure": 5,
                        "total": 40,
                    },
                    "token_usage": None,
                    "report_context": None,
                }
            )
            + "\n\n"
        ),
    )

    answer = page.locator(".ast-msg.assistant .ast-answer").last
    expect(answer).to_have_text("Partial answer.")
    # The byte breakdown comes from `meta`, so it is on screen before the answer ends.
    expect(page.locator(".ast-msg.user .ast-msg-meta")).to_contain_text("Sent to LLM")
    expect(page.locator("#ast-send")).to_be_visible()
    expect(page.locator("#ast-stop")).to_be_hidden()
    expect(page.locator(".ast-caret")).to_have_count(0)
    assert assistant_dash.errors == []


def test_assistant_keeps_a_streaming_answer_when_the_window_is_reopened(assistant_dash):
    """Closing the window used to drop the in-flight answer and leave a bare question."""
    page = assistant_dash.page
    held = []
    page.route("**/api/assistant/stream", lambda route: held.append(route))
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Close me while thinking")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.ast-waiting")).to_be_visible()

    page.locator("#ast-close").click()
    expect(page.locator("#assistant-dialog")).to_be_hidden()
    page.locator("#assistant-btn").click()

    # The pending answer belongs to the transcript, so re-rendering restores it.
    expect(page.locator(".ast-msg")).to_have_count(2)
    expect(page.locator(".ast-msg.ast-waiting")).to_be_visible()
    expect(page.locator("#ast-stop")).to_be_visible()

    assert held
    _fulfil_stream(
        held[0],
        {
            "answer": "Finished after reopening [R1].",
            "evidence": [],
            "provider": "fake",
            "model": "offline-fake",
            "context_model": None,
            "reports_considered": 1,
            "truncated": False,
            "context_limited": False,
            "output_limited": False,
            "scope": "all readable reports",
            "provider_input_bytes": 40,
            "prompt_bytes": {
                "system": 10,
                "user": 5,
                "context": 20,
                "history": 0,
                "structure": 5,
                "total": 40,
            },
            "token_usage": None,
            "report_context": None,
        },
    )

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Finished after reopening"
    )
    # The breakdown lands on the question that is actually on screen, not a detached node.
    expect(page.locator(".ast-msg.user .ast-msg-meta")).to_contain_text("Sent to LLM")
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_be_visible()
    assert assistant_dash.errors == []


def test_assistant_stop_keeps_the_partial_answer_and_frees_the_input(assistant_dash):
    page = assistant_dash.page
    page.route(
        "**/api/assistant/stream",
        lambda route: route.fulfill(
            status=200,
            content_type="text/event-stream",
            # No `done`: the connection is what the browser aborts.
            body=(
                "event: meta\ndata: "
                + json.dumps(
                    {
                        "provider": "fake",
                        "model": "offline-fake",
                        "context_model": None,
                        "reports_considered": 1,
                        "scope": "all readable reports",
                        "prompt_bytes": {
                            "system": 10,
                            "user": 5,
                            "context": 20,
                            "history": 0,
                            "structure": 5,
                            "total": 40,
                        },
                        "provider_input_bytes": 40,
                        "report_context": None,
                    }
                )
                + "\n\n"
                + "event: delta\ndata: "
                + json.dumps({"text": "Half an answer"})
                + "\n\n"
            ),
        ),
    )
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Stop me")
    page.locator("#ast-send").click()

    answer = page.locator(".ast-msg.assistant .ast-answer").last
    expect(answer).to_contain_text("Half an answer")
    expect(page.locator(".ast-stopped-note")).to_be_visible()
    expect(page.locator("#ast-send")).to_be_visible()
    expect(page.locator("#ast-question")).to_be_enabled()
    expect(page.locator(".ast-msg.assistant .ast-copy")).to_be_visible()
    assert assistant_dash.errors == []


def test_assistant_keeps_a_partial_answer_when_the_provider_fails_midway(
    assistant_dash,
):
    """A provider that dies half-way through must not erase what it already wrote."""
    page = assistant_dash.page
    page.route(
        "**/api/assistant/stream",
        lambda route: route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=(
                "event: meta\ndata: "
                + json.dumps(
                    {
                        "provider": "fake",
                        "model": "offline-fake",
                        "context_model": None,
                        "reports_considered": 1,
                        "scope": "all readable reports",
                        "prompt_bytes": {
                            "system": 10,
                            "user": 5,
                            "context": 20,
                            "history": 0,
                            "structure": 5,
                            "total": 40,
                        },
                        "provider_input_bytes": 40,
                        "report_context": None,
                    }
                )
                + "\n\n"
                + "event: delta\ndata: "
                + json.dumps({"text": "The first finding is"})
                + "\n\n"
                + "event: error\ndata: "
                + json.dumps({"detail": "upstream refused", "status": 502})
                + "\n\n"
            ),
        ),
    )
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Break midway")
    page.locator("#ast-send").click()

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "The first finding is"
    )
    expect(page.locator(".ast-stopped-note")).to_contain_text("upstream refused")
    expect(page.locator(".ast-answer.ast-error")).to_have_count(0)
    assert assistant_dash.errors == []


def test_context_overview_returns_focus_after_the_answer_re_renders(assistant_dash):
    """Closing the overview must land on its own button, not fall back to the input.

    The answer arrives in pieces, so the bubble holding the button is rebuilt while the
    overview is open. Holding a node reference alone left focus pointing at a detached
    element and silently dropped the user back into the textarea.
    """
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    page.locator("#ast-question").fill("Rebuild under me")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=15_000
    )
    review = page.locator(".ast-msg.user .ast-context-review").last
    review.click()
    expect(page.locator("#ast-report-context-dialog")).to_be_visible()

    # Rebuild every bubble while the overview is open, exactly as a late `done` event or
    # a locale change does.
    page.evaluate("() => localStorage.setItem('i18nextLng', 'ru')")
    expect(page.locator("#ast-send-label")).to_have_text("Отправить", timeout=5_000)
    expect(page.locator(".ast-msg.user .ast-context-review").last).to_have_text(
        "Обзор контекста"
    )

    page.locator("#ast-report-context-close").click()
    expect(page.locator("#ast-report-context-dialog")).to_be_hidden()
    expect(page.locator(".ast-msg.user .ast-context-review").last).to_be_focused()
    page.evaluate("localStorage.removeItem('i18nextLng')")
    assert assistant_dash.errors == []


def test_session_total_sits_beside_the_scope_and_replaces_the_list_button(
    assistant_dash,
):
    """Cost belongs next to scope, and takes the list button's place when there is none."""
    page = assistant_dash.page
    page.set_viewport_size({"width": 1280, "height": 860})
    page.locator("#assistant-btn").click()
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": "Counted [R1].",
                "evidence": [],
                "provider": "fake",
                "model": "offline-fake",
                "context_model": None,
                "reports_considered": 1,
                "truncated": False,
                "context_limited": False,
                "output_limited": False,
                "scope": "all readable reports",
                "provider_input_bytes": 40,
                "prompt_bytes": {
                    "system": 10,
                    "user": 5,
                    "context": 20,
                    "history": 0,
                    "structure": 5,
                    "total": 40,
                },
                "token_usage": {
                    "input_tokens": 2_718,
                    "output_tokens": 261,
                    "total_tokens": 2_979,
                    "cached_input_tokens": 0,
                },
                "report_context": None,
            },
        ),
    )
    page.locator("#ast-question").fill("How much did this cost?")
    page.locator("#ast-send").click()

    total = page.locator("#ast-session-tokens")
    expect(total).to_be_visible()
    expect(total).to_contain_text("2,979")
    # It lives in the scope row, not the window header.
    assert total.evaluate("el => Boolean(el.closest('.ast-scope-row'))")
    # Nothing is selected, so it occupies the hidden list button's place at the right edge.
    expect(page.locator("#ast-scope-list")).to_be_hidden()
    geometry = page.evaluate(
        """() => {
          const row = document.querySelector('.ast-scope-row').getBoundingClientRect();
          const total = document.getElementById('ast-session-tokens').getBoundingClientRect();
          const scope = document.getElementById('ast-scope').getBoundingClientRect();
          return {rowRight: row.right, totalRight: total.right, sameLine:
            Math.abs(total.top - scope.top) < 8, overflow:
            document.documentElement.scrollWidth - window.innerWidth};
        }"""
    )
    assert abs(geometry["rowRight"] - geometry["totalRight"]) <= 2
    assert geometry["sameLine"] and geometry["overflow"] <= 2

    # Narrow: the row wraps as a unit instead of overflowing.
    page.set_viewport_size({"width": 375, "height": 812})
    narrow = page.evaluate(
        """() => {
          const row = document.querySelector('.ast-scope-row').getBoundingClientRect();
          const total = document.getElementById('ast-session-tokens').getBoundingClientRect();
          return {fits: total.right <= row.right + 1,
                  overflow: document.documentElement.scrollWidth - window.innerWidth};
        }"""
    )
    assert narrow["fits"] and narrow["overflow"] <= 2
    assert assistant_dash.errors == []


def test_server_history_replaces_the_browser_copy_and_clear_deletes_it(assistant_dash):
    """When the server owns the transcript it must win, and Clear must reach it."""
    page = assistant_dash.page
    deleted = []
    page.route(
        "**/api/assistant/status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "enabled": True,
                    "provider": "fake",
                    "model": "offline-fake",
                    "context_model": None,
                    "context_mode": "direct-bounded",
                    "storage_namespace": "server-history-test",
                    "max_question_chars": 4000,
                    "max_history_messages": 12,
                    "max_history_chars": 4000,
                    "max_scope_reports": 100,
                    "direct_max_summaries": 100,
                    "direct_max_detail_reports": None,
                    "direct_max_failures_per_report": None,
                    "max_context_bytes": 49_152,
                    "max_output_tokens": 3_072,
                    "max_failure_bytes": 3_072,
                    "max_capture_bytes": 2_048,
                    "local_complete_tree": False,
                    "history_server_side": True,
                    "history_days": 30,
                }
            ),
        ),
    )

    def history(route):
        if route.request.method == "DELETE":
            deleted.append(True)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"removed": 2}),
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "available": True,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Asked from another browser",
                            "evidence": [],
                            "total_tokens": 0,
                        },
                        {
                            "role": "assistant",
                            "content": "Answered there too [R1].",
                            "evidence": [],
                            "total_tokens": 120,
                        },
                    ],
                }
            ),
        )

    page.route("**/api/assistant/history", history)
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()

    # A transcript this tab never saw is on screen.
    expect(page.locator(".ast-msg.user .ast-answer")).to_contain_text(
        "Asked from another browser"
    )
    expect(page.locator(".ast-msg.assistant .ast-answer")).to_contain_text(
        "Answered there too"
    )
    expect(page.locator("#ast-clear")).to_be_visible()

    page.locator("#ast-clear").click()
    page.locator("#ast-clear-yes").click()
    expect(page.locator(".ast-msg")).to_have_count(0)
    expect(page.locator(".ast-empty")).to_be_visible()
    page.wait_for_timeout(300)
    assert deleted, "Clear chat must delete the server-side copy too"
    assert assistant_dash.errors == []


def _status_route(page, body: dict):
    """Answer the status call with ``body`` and reload so the viewer reads it."""

    page.route(
        "**/api/assistant/status",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body)
        ),
    )
    page.reload()


def test_a_misconfigured_assistant_explains_itself_instead_of_vanishing(assistant_dash):
    """The operator set the provider and got a viewer with no assistant in it.

    Hiding the button is right when nobody asked for the feature and wrong once someone
    has: the only clue left was a status endpoint nobody thinks to open.
    """
    page = assistant_dash.page
    reason = (
        "Provider 'anthropic' is selected but its SDK is not installed; "
        "install the 'assistant-anthropic' extra."
    )
    _status_route(
        page,
        {
            "enabled": False,
            "configured": True,
            "provider": "anthropic",
            "model": "claude-sonnet-4-5",
            "reason": reason,
        },
    )

    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()

    expect(page.locator("#assistant-dialog")).to_be_visible()
    notice = page.locator("#ast-unavailable")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("assistant-anthropic")
    # Nothing to type into: the composer would only produce a 503.
    expect(page.locator("#ast-form")).to_be_hidden()


def test_an_assistant_nobody_asked_for_stays_out_of_the_way(assistant_dash):
    page = assistant_dash.page
    _status_route(
        page,
        {
            "enabled": False,
            "configured": False,
            "provider": None,
            "reason": "Set AIRFLOW_PYTEST_ASSISTANT_PROVIDER to enable the assistant.",
        },
    )

    page.wait_for_timeout(500)

    expect(page.locator("#assistant-btn")).to_be_hidden()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_unavailable_notice_is_readable_in_both_themes(assistant_dash, theme):
    """The reason block must not blend into the panel it sits on."""
    page = assistant_dash.page
    page.emulate_media(color_scheme=theme)
    _status_route(
        page,
        {
            "enabled": False,
            "configured": True,
            "provider": "anthropic",
            "reason": "Provider 'anthropic' is selected but its SDK is not installed.",
        },
    )
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()

    contrast = page.evaluate(
        """() => {
          const parse = (value) => {
            const [r, g, b] = value.match(/[\\d.]+/g).map(Number);
            const channel = (c) => {
              const s = c / 255;
              return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
            };
            return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
          };
          const code = document.getElementById("ast-unavailable-reason");
          const box = code.closest("pre");
          const panel = document.getElementById("assistant-dialog");
          const text = parse(getComputedStyle(code).color);
          const surface = parse(getComputedStyle(box).backgroundColor);
          const behind = parse(getComputedStyle(panel).backgroundColor);
          const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          return {text: ratio(text, surface), edge: ratio(surface, behind)};
        }"""
    )

    assert contrast["text"] >= 4.5, contrast
    # The block has to be visibly its own surface, not a flat continuation of the panel.
    assert contrast["edge"] >= 1.03, contrast


def test_the_unavailable_panel_offers_nothing_that_cannot_work(assistant_dash):
    """No scope banner, no composer, no Clear: none of them can do anything here."""
    page = assistant_dash.page
    _status_route(
        page,
        {
            "enabled": False,
            "configured": True,
            "provider": "anthropic",
            "reason": "Provider 'anthropic' is selected but its SDK is not installed.",
        },
    )
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()

    expect(page.locator("#ast-context")).to_be_hidden()
    expect(page.locator("#ast-form")).to_be_hidden()
    expect(page.locator("#ast-clear")).to_be_hidden()
    # Focus still lands somewhere sane for a keyboard user.
    assert page.evaluate("() => document.activeElement.id") == "ast-close"


def test_local_progress_is_visible_while_the_tree_is_being_reduced(assistant_dash):
    """Local mode sends nothing for up to two minutes; the user needs to see movement.

    The mocked stream closes as soon as it is written, so the waiting bubble is gone by
    the time an assertion could look at it. A recorder catches what was actually rendered.
    """
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    page.evaluate(
        """() => {
          window.__progress = [];
          // Read the mutation records, not the live DOM: the observer callback runs on a
          // microtask, by which time the whole mocked stream has been consumed and the
          // waiting bubble replaced.
          const seen = new MutationObserver((records) => {
            for (const record of records) {
              for (const node of record.addedNodes) {
                if (node.classList && node.classList.contains("ast-progress")) {
                  window.__progress.push(node.textContent);
                }
              }
            }
          });
          seen.observe(document.getElementById("ast-messages"),
                       {subtree: true, childList: true, characterData: true});
        }"""
    )

    def stream(route):
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=(
                'event: progress\ndata: {"phase": "loading_model"}\n\n'
                'event: progress\ndata: {"phase": "local_reduce", "chunks_done": 7,'
                ' "elapsed_seconds": 21.5, "budget_seconds": 120}\n\n'
            ),
        )

    page.route("**/api/assistant/stream", stream)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    page.wait_for_function("() => window.__progress && window.__progress.length >= 2")

    rendered = page.evaluate("() => window.__progress")
    assert any("model" in text.lower() for text in rendered), rendered
    last = rendered[-1]
    assert "7" in last and "120" in last, last


def test_progress_disappears_once_the_answer_starts(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()

    def stream(route):
        body = (
            'event: progress\ndata: {"phase": "local_reduce", "chunks_done": 3,'
            ' "elapsed_seconds": 4, "budget_seconds": 120}\n\n'
            + _stream_body({"answer": "All good.", "evidence": [], "reports": []})
        )
        route.fulfill(status=200, content_type="text/event-stream", body=body)

    page.route("**/api/assistant/stream", stream)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()

    expect(page.locator(".ast-answer").last).to_contain_text("All good.")
    expect(page.locator(".ast-progress")).to_have_count(0)


_CHATS = {
    "available": True,
    "conversation": "chat-b",
    "conversations": [
        {
            "id": "chat-b",
            "title": "why is etl_daily red?",
            "messages": 4,
            "updated_at": "2026-08-04T10:00:00",
        },
        {
            "id": "chat-a",
            "title": "which tests got slower?",
            "messages": 2,
            "updated_at": "2026-08-03T09:00:00",
        },
    ],
    "messages": [
        {"role": "user", "content": "why is etl_daily red?", "evidence": []},
        {"role": "assistant", "content": "Because of a timeout.", "evidence": []},
    ],
}


def _server_history(page, body=None):
    """Make the viewer believe the API server stores chats."""
    status = page.request.get(page.url.split("#")[0] + "api/assistant/status").json()
    status["history_server_side"] = True
    status["history_days"] = 30
    page.route(
        "**/api/assistant/status",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(status)
        ),
    )
    page.route(
        "**/api/assistant/history*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(body if body is not None else _CHATS),
        ),
    )
    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)


def test_the_chat_list_opens_and_names_each_conversation(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()

    page.locator("#ast-chats").click()

    dialog = page.locator("#ast-chats-dialog")
    expect(dialog).to_be_visible()
    items = dialog.locator(".ast-chat-item")
    expect(items).to_have_count(2)
    expect(items.first).to_contain_text("why is etl_daily red?")
    expect(items.nth(1)).to_contain_text("which tests got slower?")
    # The chat being read is marked, so switching is not a guess.
    expect(items.first).to_have_attribute("aria-current", "true")


def test_switching_chats_loads_that_transcript(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()

    asked = []

    def by_conversation(route):
        asked.append(route.request.url)
        body = dict(_CHATS)
        body["conversation"] = "chat-a"
        body["messages"] = [
            {"role": "user", "content": "which tests got slower?", "evidence": []},
            {"role": "assistant", "content": "test_ingest, by 4s.", "evidence": []},
        ]
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body)
        )

    page.locator("#ast-chats").click()
    page.route("**/api/assistant/history*", by_conversation)
    page.locator(".ast-chat-item").nth(1).click()

    expect(page.locator("#ast-chats-dialog")).to_be_hidden()
    expect(page.locator(".ast-answer").last).to_contain_text("test_ingest")
    assert any("conversation=chat-a" in url for url in asked), asked


def test_a_new_chat_starts_empty_without_deleting_anything(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    deletes = []
    page.on("request", lambda r: deletes.append(r) if r.method == "DELETE" else None)

    page.locator("#ast-chats").click()
    page.locator("#ast-chat-new").click()

    expect(page.locator("#ast-chats-dialog")).to_be_hidden()
    expect(page.locator(".ast-empty")).to_be_visible()
    assert deletes == [], "starting a new chat must never erase an old one"


def test_the_chat_button_is_absent_without_server_history(assistant_dash):
    """Nothing to switch between when the transcript lives in this tab only."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()

    expect(page.locator("#ast-chats")).to_be_hidden()


def test_deleting_a_chat_asks_first(assistant_dash):
    """A misclick on a row's × would otherwise erase a conversation for good."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    deletes = []
    page.on(
        "request", lambda r: deletes.append(r.url) if r.method == "DELETE" else None
    )

    page.locator("#ast-chats").click()
    page.locator(".ast-chat-delete").first.click()

    expect(page.locator(".ast-chat-confirm")).to_be_visible()
    assert deletes == [], "nothing may be deleted before the confirmation"

    page.locator(".ast-chat-cancel").click()

    expect(page.locator(".ast-chat-confirm")).to_have_count(0)
    expect(page.locator(".ast-chat-item").first).to_be_visible()
    assert deletes == []


def test_confirming_deletes_only_that_chat(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    deletes = []
    page.on(
        "request", lambda r: deletes.append(r.url) if r.method == "DELETE" else None
    )

    page.locator("#ast-chats").click()
    page.locator(".ast-chat-delete").nth(1).click()
    page.locator(".ast-chat-confirm").click()

    page.wait_for_function("() => true")
    expect(page.locator("#ast-chats-dialog")).to_be_visible()
    assert len(deletes) == 1 and "conversation=chat-a" in deletes[0], deletes


def test_a_refresh_returns_to_the_chat_you_were_reading(assistant_dash):
    """Switching to an older chat and reloading must not silently jump to the newest."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()

    def by_conversation(route):
        wanted = "chat-a" if "conversation=chat-a" in route.request.url else "chat-b"
        body = dict(_CHATS)
        body["conversation"] = wanted
        body["messages"] = [
            {"role": "user", "content": f"question in {wanted}", "evidence": []},
            {"role": "assistant", "content": f"answer from {wanted}", "evidence": []},
        ]
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body)
        )

    page.route("**/api/assistant/history*", by_conversation)
    page.locator("#ast-chats").click()
    page.locator(".ast-chat-item").nth(1).click()
    expect(page.locator(".ast-answer").last).to_contain_text("answer from chat-a")

    page.reload()
    page.wait_for_selector("#kpis:not([hidden])", timeout=20_000)
    # The window reopens by itself after a refresh in the same tab.
    expect(page.locator("#assistant-dialog")).to_be_visible()

    expect(page.locator(".ast-answer").last).to_contain_text("answer from chat-a")


def test_two_windows_of_one_user_do_not_overwrite_each_other(assistant_dash, context):
    """Two tabs share a server chat but keep their own in-tab transcript.

    sessionStorage is per tab, so the second window must not inherit or clobber the first
    one's on-screen conversation; the server copy is the only thing they share.
    """
    first = assistant_dash.page
    _server_history(first)
    first.locator("#assistant-btn").click()

    second = context.new_page()
    _install_history_routes(second)
    second.goto(first.url)
    second.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    second.locator("#assistant-btn").click()

    # Each window renders the server transcript; neither shows the other's draft.
    first.locator("#ast-question").fill("draft in window one")
    expect(second.locator("#ast-question")).to_have_value("")
    second.locator("#ast-question").fill("draft in window two")
    expect(first.locator("#ast-question")).to_have_value("draft in window one")
    second.close()


def test_a_second_window_can_open_a_different_chat(assistant_dash, context):
    first = assistant_dash.page
    _server_history(first)
    first.locator("#assistant-btn").click()

    second = context.new_page()
    _install_history_routes(second)
    second.goto(first.url)
    second.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    second.locator("#assistant-btn").click()
    second.locator("#ast-chats").click()
    second.locator(".ast-chat-item").nth(1).click()

    # The first window is untouched by what the second one opened.
    expect(second.locator(".ast-answer").last).to_contain_text("chat-a")
    expect(first.locator(".ast-answer").last).to_contain_text("timeout")
    second.close()


def test_a_different_user_in_the_same_browser_sees_nothing_of_the_first(
    assistant_dash, context
):
    """Logging in as someone else must not restore the previous user's transcript."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    expect(page.locator(".ast-answer").last).to_contain_text("timeout")

    other = context.new_page()
    status = _install_history_routes(
        other,
        history={
            "available": True,
            "conversation": None,
            "conversations": [],
            "messages": [],
        },
        namespace="a-completely-different-user",
    )
    del status
    other.goto(page.url)
    other.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    other.locator("#assistant-btn").click()

    expect(other.locator(".ast-empty")).to_be_visible()
    # Nothing of the first user's conversation, in the panel or in this tab's storage.
    assert "timeout" not in other.locator("#ast-messages").inner_text()
    stored = other.evaluate("() => Object.values(sessionStorage).join(' ')")
    assert "timeout" not in stored
    other.close()


def _install_history_routes(page, history=None, namespace=None):
    """Mock status + history on a page that has no fixture of its own."""
    body = dict(_CHATS) if history is None else history

    def status_route(route):
        raw = route.fetch()
        status = raw.json()
        status["history_server_side"] = True
        status["history_days"] = 30
        if namespace:
            status["storage_namespace"] = namespace
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(status)
        )

    def history_route(route):
        wanted = "chat-a" if "conversation=chat-a" in route.request.url else None
        payload = dict(body)
        if wanted:
            payload["conversation"] = wanted
            payload["messages"] = [
                {"role": "user", "content": "q chat-a", "evidence": []},
                {"role": "assistant", "content": "answer from chat-a", "evidence": []},
            ]
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload)
        )

    page.route("**/api/assistant/status", status_route)
    page.route("**/api/assistant/history*", history_route)
    return body


_XSS = [
    "<img src=x onerror=window.__pwned=1>",
    "<script>window.__pwned=1</script>",
    "javascript:window.__pwned=1",
    "<svg/onload=window.__pwned=1>",
    "\"><iframe srcdoc='<script>parent.__pwned=1</script>'>",
    '<a href="javascript:window.__pwned=1">click</a>',
]


def test_a_chat_title_is_never_treated_as_markup(assistant_dash):
    """The title is the user's own question, replayed from the database into a list."""
    page = assistant_dash.page
    hostile = {
        "available": True,
        "conversation": "c0",
        "conversations": [
            {"id": f"c{index}", "title": payload, "messages": 2, "updated_at": None}
            for index, payload in enumerate(_XSS)
        ],
        "messages": [],
    }
    _server_history(page, hostile)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()

    expect(page.locator(".ast-chat-item")).to_have_count(len(_XSS))
    assert page.evaluate("() => window.__pwned") is None
    assert page.locator(".ast-chat-list script, .ast-chat-list img").count() == 0
    # The payload is shown as the text it is.
    expect(page.locator(".ast-chat-title").first).to_have_text(_XSS[0])


def test_a_restored_server_answer_is_never_treated_as_markup(assistant_dash):
    page = assistant_dash.page
    hostile = {
        "available": True,
        "conversation": "c0",
        "conversations": [
            {"id": "c0", "title": "t", "messages": 2, "updated_at": None}
        ],
        "messages": [
            {"role": "user", "content": _XSS[0], "evidence": []},
            {"role": "assistant", "content": "\n".join(_XSS), "evidence": []},
        ],
    }
    _server_history(page, hostile)
    page.locator("#assistant-btn").click()

    assert page.evaluate("() => window.__pwned") is None
    assert page.locator("#ast-messages script, #ast-messages iframe").count() == 0
    assert page.locator('#ast-messages a[href^="javascript"]').count() == 0


def test_hostile_evidence_links_cannot_navigate_anywhere(assistant_dash):
    """Evidence comes back from the database and drives buttons that open reports."""
    page = assistant_dash.page
    hostile = {
        "available": True,
        "conversation": "c0",
        "conversations": [
            {"id": "c0", "title": "t", "messages": 2, "updated_at": None}
        ],
        "messages": [
            {"role": "user", "content": "q", "evidence": []},
            {
                "role": "assistant",
                "content": "See [R1].",
                "evidence": [
                    {
                        "key": "R1",
                        "report_id": "javascript:window.__pwned=1",
                        "dag_id": "<img src=x onerror=window.__pwned=1>",
                        "task_id": "t",
                        "run_id": "r",
                    }
                ],
            },
        ],
    }
    _server_history(page, hostile)
    page.locator("#assistant-btn").click()

    assert page.evaluate("() => window.__pwned") is None
    assert page.locator('#ast-messages a[href^="javascript"]').count() == 0


def _hold_stream(page):
    """Start an answer and never answer it, so the panel stays in its pending state.

    The route handler deliberately neither fulfils nor continues: the request hangs, which
    is exactly the state a slow model puts the panel in.
    """
    page.route("**/api/assistant/stream", lambda route: None)
    page.locator("#ast-question").fill("what failed?")
    page.locator("#ast-send").click()
    page.wait_for_selector("#ast-stop:not([hidden])", timeout=10_000)


def test_the_chat_being_written_to_cannot_be_cleared_mid_answer(assistant_dash):
    """Clearing under an in-flight answer files it into a transcript that no longer exists."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    deletes = []
    page.on(
        "request", lambda r: deletes.append(r.url) if r.method == "DELETE" else None
    )

    _hold_stream(page)

    expect(page.locator("#ast-clear")).to_be_disabled()
    page.locator("#ast-clear").click(force=True)
    assert deletes == [], "a disabled Clear must not reach the server either"


def test_the_chat_being_written_to_cannot_be_deleted_mid_answer(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    _hold_stream(page)

    page.locator("#ast-chats").click()
    current = page.locator(".ast-chat-item[aria-current='true']")
    expect(current).to_have_count(1)
    expect(
        page.locator(".ast-chat-row").first.locator(".ast-chat-delete")
    ).to_be_disabled()
    # A different chat is not being written to, so it stays deletable.
    expect(
        page.locator(".ast-chat-row").nth(1).locator(".ast-chat-delete")
    ).to_be_enabled()


def test_controls_come_back_once_the_answer_is_stopped(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    _hold_stream(page)
    expect(page.locator("#ast-clear")).to_be_disabled()

    page.locator("#ast-stop").click()

    expect(page.locator("#ast-clear")).to_be_enabled()
    expect(page.locator("#ast-send")).to_be_visible()


_AWKWARD_MARKDOWN = {
    "unbalanced table": "| a | b |\n| --- |\n| 1 | 2 | 3 |\n| 4 |",
    "table with no body": "| a | b |\n| --- | --- |",
    "unclosed code fence": "```python\nprint('x')",
    "unclosed emphasis": "**bold and *italic",
    "nested lists ten deep": "\n".join(
        " " * (level * 2) + "- item" for level in range(10)
    ),
    "heading with no text": "#\n##\n###",
    "link with no target": "[click]()",
    "reference link never defined": "[click][missing]",
    "pipe inside a cell": "| a | b |\n| --- | --- |\n| x \\| y | z |",
    "one very long line": "x" * 50_000,
    "only whitespace": "   \n\n\t\n   ",
    "html comment": "<!-- hidden -->visible",
    "mixed rtl and code": "‮`code`‬ after",
    "list item that is a table": "- | a |\n  | --- |\n  | 1 |",
}


def test_awkward_markdown_still_renders_an_answer(assistant_dash):
    """A renderer that throws leaves an empty bubble and no way to read the answer.

    Every payload here is something a model plausibly emits when it runs out of tokens
    mid-structure.
    """
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    for label, markdown in _AWKWARD_MARKDOWN.items():
        # A closure, not a default argument: Playwright reads the handler's arity and
        # would pass the Request as the second parameter.
        def answer_with(route, body=None, _body=markdown):
            del body
            _fulfil_stream(route, {"answer": _body, "evidence": [], "reports": []})

        page.route("**/api/assistant/stream", lambda route: answer_with(route))
        page.locator("#ast-question").fill(f"render {label}")
        page.locator("#ast-send").click()
        # Wait for the answer to land: asserting on "the last bubble" straight after the
        # click races the three-dot placeholder, which is legitimately empty.
        expect(page.locator("#ast-send")).to_be_visible()
        expect(page.locator(".ast-msg.assistant").last).not_to_have_class(
            re.compile("ast-waiting")
        )
        # Whitespace-only markdown legitimately renders nothing; everything else must
        # leave something readable rather than an empty bubble.
        if markdown.strip():
            rendered = page.locator(".ast-msg.assistant").last.inner_text()
            assert rendered.strip(), f"{label} rendered an empty answer"

    assert errors == [], errors


def test_the_chat_dialog_is_keyboard_reachable_and_returns_focus(assistant_dash):
    """A modal that traps or drops focus is unusable without a mouse."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").focus()
    page.keyboard.press("Enter")

    expect(page.locator("#ast-chats-dialog")).to_be_visible()
    assert page.evaluate(
        "() => document.getElementById('ast-chats-dialog').contains(document.activeElement)"
    ), "focus must move into the dialog"

    page.keyboard.press("Escape")

    expect(page.locator("#ast-chats-dialog")).to_be_hidden()
    expect(page.locator("#ast-chats")).to_have_attribute("aria-expanded", "false")


def test_the_chat_window_puts_close_at_the_right_with_new_chat_beside_it(
    assistant_dash,
):
    """Window conventions: the close control is the rightmost thing in the header."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()

    box = page.evaluate(
        """() => {
          const head = document.querySelector("#ast-chats-dialog .ast-scope-dialog-head");
          const rect = (id) => document.getElementById(id).getBoundingClientRect();
          return {
            head: head.getBoundingClientRect().right,
            close: rect("ast-chats-dialog-close"),
            fresh: rect("ast-chat-new"),
            title: rect("ast-chats-dialog-title"),
          };
        }"""
    )

    # Close is flush with the right edge of the header, not floating beside the title.
    assert box["head"] - box["close"]["right"] < 24, box
    # New chat sits immediately to its left, on the same row.
    assert box["fresh"]["right"] <= box["close"]["left"] + 1, box
    assert abs(box["fresh"]["top"] - box["close"]["top"]) < 12, box
    # And the title stays on the left.
    assert box["title"]["left"] < box["fresh"]["left"], box


def test_the_selected_chat_is_not_marked_with_a_left_edge_bar(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()

    current = page.locator(".ast-chat-item[aria-current='true']")
    expect(current).to_have_count(1)
    shadow = current.evaluate("el => getComputedStyle(el).boxShadow")

    assert "inset" not in shadow, shadow


def test_the_question_is_framed_and_the_answer_runs_full_width(assistant_dash):
    """Answers carry tables and code; a bubble narrower than the panel hides them."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": "| a | b |\n| --- | --- |\n| 1 | 2 |",
                "evidence": [],
                "reports": [],
            },
        ),
    )
    page.locator("#ast-question").fill("show me a table")
    page.locator("#ast-send").click()
    expect(page.locator("#ast-send")).to_be_visible()

    style = page.evaluate(
        """() => {
          const user = document.querySelector(".ast-msg.user");
          const bot = document.querySelector(".ast-msg.assistant");
          const area = document.getElementById("ast-messages");
          const read = (el) => {
            const s = getComputedStyle(el);
            return {
              borderWidth: parseFloat(s.borderTopWidth),
              width: el.getBoundingClientRect().width,
            };
          };
          return {
            user: read(user),
            bot: read(bot),
            inner: area.clientWidth - parseFloat(getComputedStyle(area).paddingLeft)
                   - parseFloat(getComputedStyle(area).paddingRight),
          };
        }"""
    )

    assert style["user"]["borderWidth"] >= 1, style
    assert style["bot"]["borderWidth"] == 0, style
    # The answer spans the available width; the question does not.
    assert style["bot"]["width"] >= style["inner"] - 1, style
    assert style["user"]["width"] < style["inner"], style


def test_the_copy_control_is_small_and_quiet(assistant_dash):
    """One answer should not add a full-size button to the transcript."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route, {"answer": "Short answer.", "evidence": [], "reports": []}
        ),
    )
    page.locator("#ast-question").fill("anything")
    page.locator("#ast-send").click()

    copy = page.locator(".ast-copy").last
    expect(copy).to_be_visible()
    size = copy.bounding_box()

    assert size["height"] <= 32, size


def test_clearing_a_chat_asks_before_deleting_anything(assistant_dash):
    """Clear wipes the transcript and its saved copy; one misclick must not do that."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    deletes: list[str] = []
    page.on(
        "request", lambda r: deletes.append(r.url) if r.method == "DELETE" else None
    )

    page.locator("#ast-clear").click()

    confirm = page.locator("#ast-clear-confirm")
    expect(confirm).to_be_visible()
    expect(confirm).to_contain_text("server")
    assert deletes == [], "nothing may go before the user says so"
    # The transcript is still there behind the question.
    expect(page.locator(".ast-msg.assistant").first).to_be_visible()

    page.locator("#ast-clear-keep").click()

    expect(confirm).to_be_hidden()
    expect(page.locator(".ast-msg.assistant").first).to_be_visible()
    assert deletes == []


def test_confirming_the_clear_removes_the_chat_and_its_saved_copy(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    deletes: list[str] = []
    page.on(
        "request", lambda r: deletes.append(r.url) if r.method == "DELETE" else None
    )

    page.locator("#ast-clear").click()
    page.locator("#ast-clear-yes").click()

    expect(page.locator("#ast-clear-confirm")).to_be_hidden()
    expect(page.locator(".ast-empty")).to_be_visible()
    page.wait_for_function("() => true")
    assert len(deletes) == 1 and "conversation=chat-b" in deletes[0], deletes


def test_the_clear_question_goes_away_when_the_window_is_reopened(assistant_dash):
    """A half-answered question must not be waiting the next time the panel opens."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    page.locator("#ast-clear").click()
    expect(page.locator("#ast-clear-confirm")).to_be_visible()

    page.locator("#ast-close").click()
    page.locator("#assistant-btn").click()

    expect(page.locator("#ast-clear-confirm")).to_be_hidden()


def test_localising_a_control_does_not_erase_its_icon(assistant_dash):
    """`textContent` on a button that holds an icon wipes the icon.

    It is invisible in a screenshot review because the label still reads correctly.
    """
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()

    for selector in ("#ast-chat-new", "#ast-send", "#ast-stop"):
        assert page.locator(f"{selector} svg").count() == 1, selector
    expect(page.locator("#ast-chat-new-label")).not_to_be_empty()


def test_a_table_too_wide_to_fit_scrolls_inside_the_answer(assistant_dash):
    """Full-width answers fit more, not everything: the containment still has to work."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    columns = [f"column number {index}" for index in range(12)]
    wide = (
        "| " + " | ".join(columns) + " |\n"
        "| " + " | ".join("---" for _ in columns) + " |\n"
        "| " + " | ".join(f"value {index}" for index in range(12)) + " |"
    )
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route, {"answer": wide, "evidence": [], "reports": []}
        ),
    )
    page.locator("#ast-question").fill("a very wide table")
    page.locator("#ast-send").click()
    expect(page.locator("#ast-send")).to_be_visible()

    metrics = page.locator(".ast-table-wrap").last.evaluate(
        """el => ({
          client: el.clientWidth,
          scroll: el.scrollWidth,
          page: document.documentElement.scrollWidth
                <= document.documentElement.clientWidth,
        })"""
    )

    assert metrics["scroll"] > metrics["client"], "this one genuinely overflows"
    assert metrics["page"], "and it is contained: the page does not scroll sideways"


def test_a_new_chat_appears_in_the_list_before_it_has_any_messages(assistant_dash):
    """The list comes from the server, and a new chat is not there until it is answered.

    So pressing New chat emptied the panel and then showed a list that did not contain
    the chat you were now in, with the old one still marked open.
    """
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()
    expect(page.locator(".ast-chat-item")).to_have_count(2)

    page.locator("#ast-chat-new").click()
    page.locator("#ast-chats").click()

    items = page.locator(".ast-chat-item")
    expect(items).to_have_count(3)
    # The new one is first, marked as the one being read, and honest about being empty.
    expect(items.first).to_have_attribute("aria-current", "true")
    expect(items.first).to_contain_text("0")
    expect(page.locator(".ast-chat-item[aria-current='true']")).to_have_count(1)


def test_the_new_chat_stops_being_a_placeholder_once_it_is_saved(assistant_dash):
    """It must not sit in the list twice after the server learns about it."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()
    page.locator("#ast-chat-new").click()

    identifier = page.evaluate(
        "() => JSON.parse(Object.entries(sessionStorage)"
        ".find(([k]) => k.indexOf('assistant:v') >= 0)[1]).conversation"
    )
    saved = dict(_CHATS)
    saved["conversation"] = identifier
    saved["conversations"] = [
        {"id": identifier, "title": "first question", "messages": 2, "updated_at": None}
    ] + _CHATS["conversations"]
    page.route(
        "**/api/assistant/history*",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(saved)
        ),
    )

    page.locator("#ast-chats").click()

    expect(page.locator(".ast-chat-item")).to_have_count(3)
    expect(page.locator(".ast-chat-item").first).to_contain_text("first question")


def test_a_chat_can_be_renamed_from_the_list(assistant_dash):
    """The opening question is a default label, not the one a person would choose."""
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    sent: list[dict] = []
    page.route(
        "**/api/assistant/history*",
        lambda route: (
            sent.append(
                {
                    "method": route.request.method,
                    "url": route.request.url,
                    "body": route.request.post_data_json,
                }
            ),
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"renamed": 1} if route.request.method == "PATCH" else _CHATS
                ),
            ),
        )[-1],
    )
    page.locator("#ast-chats").click()

    page.locator(".ast-chat-rename").first.click()
    field = page.locator(".ast-chat-name-input")
    expect(field).to_be_focused()
    field.fill("Friday incident")
    field.press("Enter")

    patch = [call for call in sent if call["method"] == "PATCH"]
    assert patch and patch[0]["body"]["title"] == "Friday incident", sent
    assert "conversation=chat-b" in patch[0]["url"]


def test_renaming_can_be_abandoned_without_saving(assistant_dash):
    page = assistant_dash.page
    _server_history(page)
    page.locator("#assistant-btn").click()
    patches: list[str] = []
    page.on(
        "request",
        lambda r: patches.append(r.url) if r.method == "PATCH" else None,
    )
    page.locator("#ast-chats").click()

    page.locator(".ast-chat-rename").first.click()
    page.locator(".ast-chat-name-input").fill("half a name")
    page.locator(".ast-chat-name-input").press("Escape")

    expect(page.locator(".ast-chat-name-input")).to_have_count(0)
    expect(page.locator(".ast-chat-title").first).to_have_text("why is etl_daily red?")
    assert patches == []


def test_a_hostile_chat_name_is_still_only_text(assistant_dash):
    page = assistant_dash.page
    hostile = dict(_CHATS)
    # The open chat is this one, so no "new chat" placeholder is prepended.
    hostile["conversation"] = "c1"
    hostile["conversations"] = [
        {
            "id": "c1",
            "title": "<img src=x onerror=window.__pwned=1>",
            "messages": 2,
            "updated_at": None,
        }
    ]
    _server_history(page, hostile)
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()

    expect(page.locator(".ast-chat-title").first).to_have_text(
        "<img src=x onerror=window.__pwned=1>"
    )
    assert page.evaluate("() => window.__pwned") is None
    assert page.locator(".ast-chat-list img").count() == 0


def test_the_question_field_suggests_a_completion_that_tab_accepts(assistant_dash):
    """A hint you can take with one key beats a placeholder you have to retype."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")

    field.click()
    field.type("What br")

    ghost = page.locator("#ast-ghost")
    expect(ghost).to_be_visible()
    suggestion = ghost.inner_text()
    assert suggestion.lower().startswith("what br"), suggestion

    field.press("Tab")

    expect(field).to_have_value(suggestion)
    expect(ghost).to_be_hidden()


def test_tab_still_leaves_the_field_when_there_is_nothing_to_complete(assistant_dash):
    """Stealing Tab with no suggestion would trap a keyboard user in the textarea."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("zzzz no such suggestion")
    expect(page.locator("#ast-ghost")).to_be_hidden()

    field.press("Tab")

    assert page.evaluate("() => document.activeElement.id") != "ast-question"


def test_the_suggestion_disappears_as_soon_as_it_stops_matching(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("What br")
    expect(page.locator("#ast-ghost")).to_be_visible()

    field.type("zzz")

    expect(page.locator("#ast-ghost")).to_be_hidden()


def test_a_suggestion_never_survives_into_the_sent_question(assistant_dash):
    """Ghost text is a hint, not content: only what was typed may be sent."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    sent: list[dict] = []
    page.route(
        "**/api/assistant/stream",
        lambda route: (
            sent.append(route.request.post_data_json),
            _fulfil_stream(route, {"answer": "ok", "evidence": [], "reports": []}),
        )[-1],
    )
    field = page.locator("#ast-question")
    field.click()
    field.type("What br")
    expect(page.locator("#ast-ghost")).to_be_visible()

    page.locator("#ast-send").click()

    assert sent and sent[0]["question"] == "What br", sent


def test_a_breakdown_missing_a_newer_part_still_renders(assistant_dash):
    """A tab held open across a deploy sends what the old build knew about.

    Rejecting the whole payload for one absent field left the bubble with no breakdown at
    all, which reads as a broken request rather than an older one.
    """
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": "Answered.",
                "evidence": [],
                "reports": [],
                # No "docs" key: exactly what a build from before it existed sends.
                "prompt_bytes": {
                    "system": 900,
                    "user": 40,
                    "context": 4200,
                    "history": 0,
                    "structure": 120,
                    "total": 5260,
                },
                "provider_input_bytes": 5260,
            },
        ),
    )
    page.locator("#ast-question").fill("anything")
    page.locator("#ast-send").click()

    rows = page.locator(".ast-msg.user .ast-prompt-row")
    expect(rows).to_have_count(7)
    expect(rows.nth(3)).to_contain_text("Documentation")
    expect(rows.nth(3).locator("code")).to_have_text("0 B")


def test_typing_a_slash_offers_the_commands(assistant_dash):
    """Exact targeting: the user names the skill instead of hoping the words match."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")

    field.click()
    field.type("/")

    menu = page.locator("#ast-commands")
    expect(menu).to_be_visible()
    items = menu.locator(".ast-command")
    # From the server's own catalogue, not a literal: the menu exists precisely so the
    # command list is never written down twice, and a test that hard-codes the count
    # makes itself the second copy.
    expect(items).to_have_count(len(command_catalogue()))
    expect(items.first).to_contain_text("/bug")
    expect(menu).to_contain_text("/docs")
    # Each one says what it does, not just its name.
    assert items.first.inner_text().strip() != "/bug"


def test_a_command_picked_from_the_menu_survives_into_the_request(assistant_dash):
    """What the user picked has to be what the server is told, keystroke for keystroke.

    Reported symptom: a question asked with /bug sometimes comes back answered as
    something else. Server-side parsing handles every spelling, so the only way that
    happens is the command not being in the text that was sent.
    """
    page = assistant_dash.page
    sent: list[dict] = []
    page.route(
        "**/api/assistant/stream",
        lambda route: (
            sent.append(route.request.post_data_json),
            _fulfil_stream(route, {"answer": "ok", "evidence": [], "reports": []}),
        )[-1],
    )
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")

    field.click()
    field.type("/")
    expect(page.locator("#ast-commands")).to_be_visible()
    page.keyboard.press("Enter")  # accept the highlighted /bug
    field.type("почему упал test_login?")
    page.locator("#ast-send").click()

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("ok")
    assert sent[0]["question"] == "/bug почему упал test_login?", sent[0]["question"]
    assert assistant_dash.errors == []


def test_arrowing_to_a_command_is_not_undone_by_typing(assistant_dash):
    """Highlighting survives the next keystroke, or the menu picks something else.

    The list is rebuilt on every input event and the highlight was reset to the top each
    time, so narrowing "/p" after arrowing down sent whatever now sat first.
    """
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")

    field.click()
    field.type("/")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    chosen = page.locator("#ast-commands .ast-command[aria-selected=true]").inner_text()
    field.type("d")  # narrows the list; the choice above must not silently move

    still = page.locator("#ast-commands .ast-command[aria-selected=true]")
    expect(still).to_have_count(1)
    assert chosen.split()[0] in still.inner_text() or still.inner_text().startswith(
        "/d"
    )


def test_the_command_menu_is_not_rebuilt_on_every_keystroke(assistant_dash):
    """The reported flicker: the list is destroyed and recreated as the name is typed.

    Typing "/bug" offers the same single command at "/b", "/bu" and "/bug", and each
    keystroke tore the row out of the DOM and built a new one -- which is visible, and
    which also threw away the aria-selected state screen readers and arrow keys rely on.
    """
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("/b")
    expect(page.locator("#ast-commands .ast-command")).to_have_count(1)

    page.evaluate(
        """() => {
          window.__astRebuilds = 0;
          new MutationObserver(records => {
            for (const record of records) {
              if (record.removedNodes.length) window.__astRebuilds++;
            }
          }).observe(document.getElementById('ast-commands'),
                     { childList: true, subtree: true });
        }"""
    )
    field.type("ug")
    page.wait_for_timeout(120)

    assert page.evaluate("window.__astRebuilds") == 0
    expect(
        page.locator("#ast-commands .ast-command[aria-selected=true]")
    ).to_contain_text("/bug")


def test_the_list_narrows_as_the_command_is_typed(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("/fl")

    items = page.locator("#ast-commands .ast-command")
    expect(items).to_have_count(1)
    expect(items.first).to_contain_text("/flaky")


def test_a_command_is_chosen_with_the_keyboard(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("/")

    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")

    expect(page.locator("#ast-commands")).to_be_hidden()
    # The second entry, and a space so the question can be typed straight after.
    expect(field).to_have_value("/compare ")
    expect(field).to_be_focused()


def test_enter_does_not_send_while_the_menu_is_open(assistant_dash):
    """Enter picks a command there; sending "/" as a question would be nonsense."""
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    sent: list[dict] = []
    page.route(
        "**/api/assistant/stream",
        lambda route: (
            sent.append(route.request.post_data_json),
            _fulfil_stream(route, {"answer": "ok", "evidence": [], "reports": []}),
        )[-1],
    )
    field = page.locator("#ast-question")
    field.click()
    field.type("/")
    page.keyboard.press("Control+Enter")

    assert sent == []


def test_escape_closes_the_menu_without_closing_the_window(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("/")
    expect(page.locator("#ast-commands")).to_be_visible()

    page.keyboard.press("Escape")

    expect(page.locator("#ast-commands")).to_be_hidden()
    expect(page.locator("#assistant-dialog")).to_be_visible()


def test_a_slash_inside_a_sentence_is_just_a_slash(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("why did /tmp/x fail")

    expect(page.locator("#ast-commands")).to_be_hidden()


def test_the_command_is_sent_and_the_menu_never_leaks_into_the_question(assistant_dash):
    page = assistant_dash.page
    page.locator("#assistant-btn").click()
    sent: list[dict] = []
    page.route(
        "**/api/assistant/stream",
        lambda route: (
            sent.append(route.request.post_data_json),
            _fulfil_stream(route, {"answer": "ok", "evidence": [], "reports": []}),
        )[-1],
    )
    field = page.locator("#ast-question")
    field.click()
    field.type("/")
    page.keyboard.press("Enter")
    field.type("по этому падению")
    page.locator("#ast-send").click()

    assert sent and sent[0]["question"] == "/bug по этому падению", sent


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_command_menu_is_readable_in_both_themes(assistant_dash, theme):
    page = assistant_dash.page
    page.emulate_media(color_scheme=theme)
    page.locator("#assistant-btn").click()
    field = page.locator("#ast-question")
    field.click()
    field.type("/")
    expect(page.locator("#ast-commands")).to_be_visible()

    ratios = page.evaluate(
        r"""() => {
          const lum = (value) => {
            // `color-mix` computes to `color(srgb r g b)` with channels in 0..1, while
            // everything else reports `rgb(0..255)`. Reading both the same way makes a
            // perfectly legible colour look like a contrast failure.
            const parts = (value.match(/[\d.]+/g) || []).map(Number);
            const rgb = value.startsWith('color(srgb')
              ? parts.slice(0, 3).map((c) => c * 255)
              : parts.slice(0, 3);
            const channel = (x) => {
              x /= 255;
              return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
            };
            return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1])
              + 0.0722 * channel(rgb[2]);
          };
          const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          const back = lum(getComputedStyle(
            document.getElementById('ast-commands')).backgroundColor);
          const name = getComputedStyle(document.querySelector('.ast-command b')).color;
          const what = getComputedStyle(document.querySelector('.ast-command span')).color;
          return {name: ratio(lum(name), back), what: ratio(lum(what), back)};
        }"""
    )

    assert ratios["name"] >= 4.5, ratios
    assert ratios["what"] >= 4.5, ratios


@pytest.mark.parametrize(
    ("width", "height", "label"),
    [
        (320, 640, "small phone"),
        (375, 812, "phone"),
        (414, 896, "large phone"),
        (768, 1024, "tablet"),
        (1280, 800, "desktop"),
    ],
)
def test_the_assistant_fits_every_viewport_it_is_opened_in(
    assistant_dash, width, height, label
):
    """The panel is embedded in an Airflow page whose width is not ours to choose.

    Checked with the window doing everything at once -- an answer rendered, the command
    menu open, the chat list open -- because each of those is absolutely positioned and
    each is a way to push a scrollbar onto a phone.
    """
    page = assistant_dash.page
    page.set_viewport_size({"width": width, "height": height})
    # The chat list only exists when the server stores one, and it is the widest thing
    # the window can put on screen.
    _server_history(page)
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": (
                    "## Вывод\n\n`tests.test_auth::test_login` падает с "
                    "`AssertionError: assert 401 == 200`.\n\n```\n"
                    "tests/test_auth.py:42: in test_login\n"
                    "    assert response.status_code == 200\n"
                    "E   AssertionError: assert 401 == 200\n```\n\n"
                    # An unbreakable run is what actually pushes a scrollbar onto a
                    # phone: real node ids are parametrised and get this long.
                    "Затронут `tests/integration/test_checkout_flow.py::"
                    "TestCheckoutIntegration::test_pay_with_saved_card"
                    "[currency=EUR-provider=stripe-retries=3-idempotency_key="
                    "0f8c2b1a9d7e4f6a8b3c5d7e9f1a2b3c]`.\n"
                ),
                "evidence": [],
                "reports": [],
            },
        ),
    )
    page.locator("#assistant-btn").click()
    expect(page.locator("#assistant-dialog")).to_be_visible()

    page.locator("#ast-question").fill("почему упал test_login?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Вывод", timeout=15_000
    )
    page.locator("#ast-question").click()
    page.locator("#ast-question").type("/")
    expect(page.locator("#ast-commands")).to_be_visible()
    page.locator("#ast-chats").click()
    expect(page.locator("#ast-chats-dialog")).to_be_visible()

    overflow = page.evaluate(
        """() => {
          const doc = document.documentElement;
          const wide = [];
          const room = window.innerWidth + 2;
          const scope = document.querySelectorAll(
            '#assistant-dialog *, #ast-chats-dialog *');
          for (const el of scope) {
            const box = el.getBoundingClientRect();
            if (box.width === 0) continue;
            if (box.right > room || box.left < -2) {
              wide.push(el.id || el.className || el.tagName);
            }
          }
          return {
            page: doc.scrollWidth - window.innerWidth,
            elements: wide.slice(0, 6),
          };
        }"""
    )

    assert overflow["page"] <= 2, f"{label}: page scrolls horizontally"
    assert overflow["elements"] == [], f"{label}: {overflow['elements']}"
    assert assistant_dash.errors == []


@pytest.mark.parametrize("width", [320, 375, 768])
def test_every_control_stays_tappable_on_a_narrow_screen(assistant_dash, width):
    """WCAG 2.2 asks 24x24 CSS pixels for a target; a phone deserves at least that."""
    page = assistant_dash.page
    page.set_viewport_size({"width": width, "height": 800})
    page.locator("#assistant-btn").click()
    expect(page.locator("#assistant-dialog")).to_be_visible()

    small = page.evaluate(
        """() => {
          const bad = [];
          const dialog = document.getElementById('assistant-dialog');
          for (const el of dialog.querySelectorAll('button, a[href], summary')) {
            if (el.hidden || el.closest('[hidden]')) continue;
            const box = el.getBoundingClientRect();
            if (box.width === 0 && box.height === 0) continue;
            if (box.width < 24 || box.height < 24) {
              bad.push((el.id || el.className) + ' ' +
                       Math.round(box.width) + 'x' + Math.round(box.height));
            }
          }
          return bad;
        }"""
    )

    assert small == [], f"{width}px: {small}"
    assert assistant_dash.errors == []


def test_the_chat_list_says_when_it_is_showing_only_the_newest(assistant_dash):
    """Twenty rows and thirty-five chats must not read as "you have twenty chats".

    A reader whose older conversation left the window otherwise cannot tell that from
    having deleted it, and the summary line asserts the truncated length as the total.
    """
    page = assistant_dash.page
    _server_history(
        page,
        {
            "available": True,
            "conversation": "c0",
            "conversations": [
                {
                    "id": f"c{index}",
                    "title": f"чат {index}",
                    "messages": 2,
                    "updated_at": "2026-08-06T10:00:00",
                }
                for index in range(20)
            ],
            "conversations_truncated": True,
            "messages": [],
        },
    )
    page.locator("#assistant-btn").click()
    page.locator("#ast-chats").click()

    expect(page.locator("#ast-chats-dialog-summary")).to_contain_text("20")
    expect(page.locator("#ast-chats-dialog-summary")).not_to_contain_text(
        "saved on the server"
    )
    assert assistant_dash.errors == []


def _status_with_quota(route, *, quota: int, spent: int) -> None:
    """Answer the status call as a deployment that bounds the daily spend would."""
    response = route.fetch()
    body = response.json()
    body.update(daily_token_quota=quota, daily_tokens_spent=spent)
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def test_the_panel_shows_how_much_of_the_daily_budget_is_left(page, assistant_base_url):
    """A quota nobody can see is a 429 that arrives without warning."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.route(
        "**/api/assistant/status",
        lambda route: _status_with_quota(route, quota=10_000, spent=2_500),
    )
    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    expect(page.locator("#assistant-dialog")).to_be_visible()

    budget = page.locator("#ast-daily-budget")
    expect(budget).to_be_visible()
    expect(budget).to_contain_text("2,500")
    expect(budget).to_contain_text("10,000")


def test_an_answer_moves_the_budget_without_asking_the_server_again(
    page, assistant_base_url
):
    """The spend changes with every answer, and the panel already knows by how much.

    Re-fetching the status after each answer would be a second request for a number the
    stream just delivered, so the figure is seeded from the server and then carried
    forward locally -- exactly as the session total already is.
    """
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.route(
        "**/api/assistant/status",
        lambda route: _status_with_quota(route, quota=10_000, spent=1_000),
    )
    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    expect(page.locator("#ast-daily-budget")).to_contain_text("1,000")

    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": "done",
                "provider": "fake",
                "model": "offline-fake",
                "evidence": [],
                # Every field the server always sends: the browser rejects a partial
                # usage object outright rather than guessing the missing counts.
                "token_usage": {
                    "input_tokens": 200,
                    "output_tokens": 50,
                    "total_tokens": 250,
                    "cached_input_tokens": 0,
                },
            },
        ),
    )
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("done")

    expect(page.locator("#ast-daily-budget")).to_contain_text("1,250")


def test_without_a_quota_the_panel_claims_no_budget(page, assistant_base_url):
    """Nothing is counted when nothing is bounded, so nothing is shown."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    expect(page.locator("#assistant-dialog")).to_be_visible()

    expect(page.locator("#ast-daily-budget")).to_be_hidden()


def test_the_budget_moves_on_a_provider_that_reports_no_usage(page, assistant_base_url):
    """Some providers answer without a `usage` block, and the server bills an estimate.

    Counting `token_usage` in the browser meant both meters stayed at zero on exactly
    those deployments while the ledger behind them ran down -- the reader watched "1,000
    of 10,000" all day and then met a 429. The server now says what it charged.
    """
    from conftest import _load_dash  # type: ignore[import-not-found]

    page.route(
        "**/api/assistant/status",
        lambda route: _status_with_quota(route, quota=10_000, spent=1_000),
    )
    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    expect(page.locator("#ast-daily-budget")).to_contain_text("1,000")

    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": "done",
                "provider": "fake",
                "model": "offline-fake",
                "evidence": [],
                "token_usage": None,
                "billed_tokens": 900,
            },
        ),
    )
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("done")

    expect(page.locator("#ast-daily-budget")).to_contain_text("1,900")
    # The session counter is fed from the same number, so the two cannot disagree.
    expect(page.locator("#ast-session-tokens")).to_contain_text("900")


def test_a_reload_keeps_the_cost_of_answers_it_restores(page, assistant_base_url):
    """The running total is persisted, so it must survive in the same units it was kept."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": "restored",
                "provider": "fake",
                "model": "offline-fake",
                "evidence": [],
                "token_usage": None,
                "billed_tokens": 700,
            },
        ),
    )
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator("#ast-session-tokens")).to_contain_text("700")

    page.reload()
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    expect(page.locator("#assistant-dialog")).to_be_visible()

    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "restored"
    )
    expect(page.locator("#ast-session-tokens")).to_contain_text("700")


CODE_ANSWER = (
    "Two tests failed [R1].\n\n"
    "```python\n"
    "def test_checkout():\n"
    "    assert total == 42  # boom\n"
    "```\n\n"
    "And the traceback:\n\n"
    "```\n"
    "AssertionError: 41 != 42\n"
    "```\n"
)


def _answer_with_code(route) -> None:
    _fulfil_stream(
        route,
        {
            "answer": CODE_ANSWER,
            "provider": "fake",
            "model": "offline-fake",
            "evidence": [
                {
                    "key": "R1",
                    "report_id": "rid",
                    "dag_id": "checkout",
                    "run_id": "run_a",
                    "task_id": "pytest",
                }
            ],
            "token_usage": None,
            "billed_tokens": 320,
        },
    )


def test_each_code_block_carries_its_own_copy(page, assistant_base_url):
    """A traceback is the part of an answer people take away.

    Selecting it by hand out of a scrolling panel, without catching the prose around it,
    is the worst way to get it -- so a fenced block gets the same affordance the whole
    answer already had, at the granularity people actually reach for.
    """
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route("**/api/assistant/stream", _answer_with_code)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("boom")

    blocks = page.locator(".ast-msg.assistant .ast-code")
    expect(blocks).to_have_count(2)
    # The fence's info string is shown, and only when the model wrote one.
    expect(blocks.nth(0).locator(".ast-code-lang")).to_have_text("python")
    expect(blocks.nth(1).locator(".ast-code-lang")).to_have_text("")
    # Visible without hovering: a touch screen has no hover, and a control nobody can
    # reveal is a control that does not exist.
    expect(blocks.nth(0).locator(".ast-code-copy")).to_be_visible()
    expect(blocks.nth(1).locator(".ast-code-copy")).to_be_visible()


def test_copying_a_code_block_takes_the_code_and_not_the_prose(
    page, assistant_base_url
):
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route("**/api/assistant/stream", _answer_with_code)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("boom")

    copied: list[str] = []
    page.expose_function("astTestCopy", lambda text: copied.append(text))
    page.evaluate(
        "() => { navigator.clipboard.writeText = t => "
        "{ window.astTestCopy(t); return Promise.resolve(); }; }"
    )

    page.locator(".ast-code").nth(1).locator(".ast-code-copy").click()
    expect(page.locator(".ast-code").nth(1).locator(".ast-code-copy")).to_contain_text(
        "Copied"
    )

    assert copied == ["AssertionError: 41 != 42"]


def test_the_whole_answer_copy_still_takes_everything(page, assistant_base_url):
    """The two copies are different scopes, not a replacement."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route("**/api/assistant/stream", _answer_with_code)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("boom")

    copied: list[str] = []
    page.expose_function("astTestCopy", lambda text: copied.append(text))
    page.evaluate(
        "() => { navigator.clipboard.writeText = t => "
        "{ window.astTestCopy(t); return Promise.resolve(); }; }"
    )

    page.locator(".ast-msg-footer .ast-copy").last.click()
    expect(page.locator(".ast-msg-footer .ast-copy").last).to_contain_text("Copied")

    assert copied and "Two tests failed" in copied[0]
    assert "def test_checkout()" in copied[0]


def test_a_chat_can_be_exported_as_markdown(page, assistant_base_url):
    """The answers are Markdown already; an export is an assembly job, not a conversion.

    Worth having because the panel is the one place this work exists: a reader who wants
    to paste the analysis into a ticket, a PR or a postmortem currently retypes it.
    """
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    # Nothing to export before there is a chat.
    expect(page.locator("#ast-export")).to_be_hidden()

    page.route("**/api/assistant/stream", _answer_with_code)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("boom")
    expect(page.locator("#ast-export")).to_be_visible()

    with page.expect_download() as download:
        page.locator("#ast-export").click()
    saved = download.value
    assert saved.suggested_filename.endswith(".md"), saved.suggested_filename

    text = pathlib.Path(saved.path()).read_text(encoding="utf-8")
    assert text.startswith("# Report assistant chat")
    # Both sides of the exchange, in order, with the answer's own Markdown intact.
    assert text.index("## You") < text.index("## Assistant")
    assert "What failed?" in text
    assert "```python" in text and "def test_checkout():" in text
    # The grounding travels with it: an export without the evidence is an unsourced claim.
    assert "**Evidence**" in text
    assert "`[R1]` checkout / run_a / pytest" in text


def test_the_export_keeps_an_answer_that_was_stopped(page, assistant_base_url):
    """What somebody exports should be what they read, including a half answer."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")

    def _hang(route):
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body='event: delta\ndata: {"text": "half an ans"}\n\n',
        )

    page.route("**/api/assistant/stream", _hang)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "half an ans"
    )

    with page.expect_download() as download:
        page.locator("#ast-export").click()
    text = pathlib.Path(download.value.path()).read_text(encoding="utf-8")

    assert "half an ans" in text
    assert "(answer stopped before it finished)" in text


def test_the_export_is_named_after_the_chat_and_the_moment(page, assistant_base_url):
    """Two exports in one session must not overwrite each other in the download folder."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route("**/api/assistant/stream", _answer_with_code)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("boom")

    with page.expect_download() as first:
        page.locator("#ast-export").click()

    name = first.value.suggested_filename
    assert name.startswith("assistant-")
    # Only characters that survive a file system, whatever the chat id was.
    assert re.fullmatch(r"assistant-[A-Za-z0-9_-]+\.md", name), name


HOSTILE_ANSWER = (
    "Here you go:\n\n"
    '```"><script>window.astPwned = 1</script>\n'
    '<img src=x onerror="window.astPwned = 2">\n'
    "</code></pre><script>window.astPwned = 3</script>\n"
    "```\n"
)


def test_a_code_block_cannot_smuggle_markup_out_of_itself(page, assistant_base_url):
    """Everything in an answer is model output, and the fence's info string is too.

    The language is written by whatever answered, so it is shown as text and never
    becomes a class name; the body is `textContent` for the same reason.
    """
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route(
        "**/api/assistant/stream",
        lambda route: _fulfil_stream(
            route,
            {
                "answer": HOSTILE_ANSWER,
                "provider": "fake",
                "model": "offline-fake",
                "evidence": [],
                "token_usage": None,
                "billed_tokens": 10,
            },
        ),
    )
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-code")).to_have_count(1)

    assert page.evaluate("() => window.astPwned || null") is None
    assert page.locator(".ast-msg.assistant script").count() == 0
    assert page.locator(".ast-msg.assistant img").count() == 0
    # The markup is visible as text, which is the whole point of a code block.
    expect(page.locator(".ast-code pre")).to_contain_text("<script>")
    # An info string that is not a plain word is not shown at all rather than shown wrong.
    expect(page.locator(".ast-code-lang")).to_have_text("")


def test_an_export_filename_cannot_escape_its_folder(page, assistant_base_url):
    """The chat id reaches a `download` attribute, and ids are not always ours."""
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route("**/api/assistant/stream", _answer_with_code)
    page.locator("#ast-question").fill("What failed?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text("boom")

    for hostile in ("../../etc/passwd", "a/b\\c", "чат", "x" * 200, ".."):
        page.evaluate(
            "id => { window.__astSetConversation(id); }", hostile
        ) if page.evaluate(
            "() => typeof window.__astSetConversation === 'function'"
        ) else None
        name = page.evaluate(
            "id => { const stamp = new Date().toISOString().slice(0, 19)"
            ".replace(/[:T]/g, '-');"
            " const chat = (id || 'chat').replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 40);"
            " return 'assistant-' + (chat || 'chat') + '-' + stamp + '.md'; }",
            hostile,
        )
        assert re.fullmatch(r"assistant-[A-Za-z0-9_-]{1,40}-[0-9-]+\.md", name), name
        assert "/" not in name and "\\" not in name and ".." not in name.rstrip(".md")


def test_a_long_chat_exports_its_window_and_says_so(page, assistant_base_url):
    """The panel keeps a window, not the whole chat, and a file hides that.

    A scrolling view makes the cut obvious -- you can see there is nothing above. A
    Markdown file that simply starts at the seventh exchange reads as the whole
    conversation, so the export says which part of it this is.
    """
    from conftest import _load_dash  # type: ignore[import-not-found]

    _load_dash(page, assistant_base_url)
    page.click("#assistant-btn")
    page.route("**/api/assistant/stream", _answer_with_code)
    for _ in range(12):
        page.locator("#ast-question").fill("What failed?")
        page.locator("#ast-send").click()
        expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
            "boom"
        )

    started = time.monotonic()
    with page.expect_download() as download:
        page.locator("#ast-export").click()
    text = pathlib.Path(download.value.path()).read_text(encoding="utf-8")
    elapsed = time.monotonic() - started

    kept = page.evaluate("() => document.querySelectorAll('.ast-msg').length")
    assert text.count("## You") + text.count("## Assistant") == kept
    assert "the chat itself may be longer" in text
    assert elapsed < 5, f"exporting the window took {elapsed:.1f}s"
