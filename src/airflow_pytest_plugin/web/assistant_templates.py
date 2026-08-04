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

"""Isolated HTML/CSS/JS fragments for the dependency-free assistant dialog."""

from __future__ import annotations

_CSS = r"""
  /* -- Report assistant: a focused, resizable workspace over the dashboard. -------- */
  #assistant-dialog.ast-dialog {
    width: min(960px, 94vw); height: min(760px, 88dvh);
    min-width: min(680px, 94vw); min-height: min(520px, 88dvh);
    max-width: 94vw; max-height: 90dvh; margin: auto; padding: 0;
    overflow: hidden; resize: both; background: var(--surface); color: var(--fg);
    border: 1px solid var(--border); border-radius: 14px;
    box-shadow: 0 24px 72px #0008;
  }
  .ast-head { min-height: 68px; padding: 12px 12px 12px 16px;
    border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
  .ast-title-wrap { min-width: 0; flex: 1 1 auto; }
  .ast-title { margin: 0; display: flex; align-items: center; gap: 8px;
    font-size: 17px; line-height: 1.3; font-weight: 650; }
  .ast-beta { padding: 2px 5px; border: 1px solid var(--border); border-radius: 5px;
    background: var(--surface-2); color: var(--primary);
    font: 700 10px/1.3 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    letter-spacing: .04em; }
  .ast-title-meta { min-width: 0; margin-top: 2px; display: flex; align-items: center;
    gap: 7px; color: var(--muted); font-size: 11px; }
  .ast-provider { min-width: 0; flex: 1 1 auto; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; }
  /* The session total sits beside "View list" so cost and scope read as one row. When no
     runs are selected the button is hidden and the total simply takes its place, which is
     why the aside is right-aligned rather than the total being positioned against the
     button. */
  .ast-scope-aside { display: flex; align-items: center; justify-content: flex-end;
    gap: 8px; flex: 0 0 auto; min-width: 0; margin-left: auto; }
  .ast-session-tokens { flex: 0 1 auto; min-width: 0; color: var(--muted); font-size: 11px;
    font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; }
  .ast-session-tokens b { color: var(--fg); font-weight: 650; }
  .ast-head-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
  .ast-close { width: 44px; height: 44px; padding: 0; justify-content: center;
    flex: 0 0 auto; }
  .ast-context { padding: 6px 16px; border-bottom: 1px solid var(--border);
    background: var(--surface-2); }
  .ast-clear { position: relative; min-height: 44px; border: 0; padding: 2px 6px;
    background: transparent;
    color: var(--muted); cursor: pointer; font: inherit; font-size: 11px; }
  .ast-clear:hover { color: var(--fg); text-decoration: underline; }
  .ast-scope-row { display: flex; align-items: center; gap: 10px; min-height: 32px;
    flex-wrap: wrap; }
  .ast-scope { display: block; min-width: 0; flex: 1 1 auto; font-size: 12px;
    line-height: 1.45; overflow-wrap: anywhere; }
  .ast-processing { display: flex; min-width: 0; color: var(--muted); font-size: 11px;
    line-height: 1.45; overflow-wrap: anywhere; }
  .ast-processing-copy { margin: 0 0 10px; color: var(--muted); }
  .ast-processing-copy code, .ast-msg-meta code { padding: 1px 4px;
    border: 1px solid var(--border); border-radius: 4px; background: var(--surface-2);
    color: var(--primary); font: 600 10.5px/1.35 ui-monospace, SFMono-Regular, Menlo,
      Consolas, monospace; }
  .ast-limit-disclosure { position: relative; display: inline-flex; align-items: center;
    color: var(--fg); }
  .ast-limit-button { min-height: 44px; padding: 0 12px; display: inline-flex;
    align-items: center; border: 1px solid var(--border); border-radius: 8px;
    background: var(--surface); color: var(--fg); cursor: pointer; font: inherit;
    font-size: 12px; font-weight: 600; }
  .ast-limit-button:hover { background: var(--surface-2); }
  .ast-limit-button[aria-expanded="true"] { background: var(--surface-2);
    border-color: var(--primary); }
  .ast-limit-button:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
  .ast-limit-tooltip { position: absolute; z-index: 20; right: 0;
    bottom: calc(100% + 8px);
    width: min(390px, calc(94vw - 32px)); padding: 12px 14px;
    visibility: hidden; opacity: 0; transform: translateY(3px); pointer-events: none;
    border: 1px solid var(--border); border-radius: 10px; background: var(--surface);
    box-shadow: 0 12px 32px #0005; transition: opacity .15s ease, transform .15s ease,
      visibility 0s linear .15s; }
  .ast-limit-disclosure[data-open="true"] .ast-limit-tooltip {
    visibility: visible; opacity: 1; transform: translateY(0); pointer-events: auto;
    transition-delay: 0s; }
  .ast-limits { display: block; margin: 0; padding-left: 18px; }
  .ast-limit + .ast-limit { margin-top: 7px; }
  .ast-limit::marker { color: var(--primary); }
  .ast-limit code { display: inline; max-width: 100%; padding: 2px 5px;
    border: 1px solid var(--border); border-radius: 5px; background: var(--surface-2);
    color: var(--primary); font: 600 10.5px/1.35 ui-monospace, SFMono-Regular, Menlo,
      Consolas, monospace; overflow-wrap: anywhere; }
  .ast-scope-list { min-height: 32px; padding: 0 9px; flex: 0 0 auto; border-radius: 7px;
    border: 1px solid var(--border); background: var(--surface); color: var(--fg);
    cursor: pointer; font: inherit; font-size: 12px; }
  .ast-scope-list:hover { background: var(--border); }
  .ast-scope-list:focus-visible, .ast-scope-dialog-close:focus-visible {
    outline: 2px solid var(--ring); outline-offset: 2px; }
  #ast-scope-dialog { max-width: min(560px, 92vw); max-height: 82vh; }
  #ast-report-context-dialog { width: min(860px, 94vw); max-width: min(860px, 94vw);
    height: min(720px, 86dvh); max-height: 86dvh; }
  .ast-scope-dialog-head { padding: 14px 16px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }
  .ast-scope-dialog-title-wrap { min-width: 0; flex: 1 1 auto; }
  .ast-scope-dialog-head h2 { margin: 0; font-size: 16px; line-height: 1.35; }
  .ast-scope-dialog-summary { margin-top: 2px; color: var(--muted); font-size: 12px; }
  .ast-scope-dialog-close { width: 44px; height: 44px; padding: 0; flex: 0 0 auto;
    justify-content: center; }
  .ast-scope-dialog-body { min-height: 0; overflow-y: auto; padding: 8px 16px 18px; }
  .ast-report-context-body { min-height: 0; flex: 1 1 auto; padding: 14px 16px 18px;
    display: flex; flex-direction: column; gap: 10px; overflow: hidden; }
  .ast-report-context-note { margin: 0; color: var(--muted); font-size: 12px;
    line-height: 1.5; }
  .ast-report-context-toolbar { display: flex; align-items: center; gap: 10px; }
  .ast-report-context-format { min-width: 0; flex: 1 1 auto; color: var(--muted);
    font-size: 12px; overflow-wrap: anywhere; }
  .ast-report-context-copy, .ast-report-context-wrap { min-height: 44px; padding: 0 12px;
    border: 1px solid var(--border); border-radius: 8px; background: var(--surface-2);
    color: var(--fg); cursor: pointer; font: inherit; font-size: 12px; font-weight: 600; }
  .ast-report-context-copy:hover, .ast-report-context-wrap:hover { border-color: var(--primary); }
  .ast-report-context-wrap[aria-pressed="true"] { border-color: var(--primary);
    background: var(--primary); color: var(--on-primary); }
  .ast-report-context-copy:focus-visible, .ast-report-context-wrap:focus-visible,
  .ast-context-review:focus-visible,
  .ast-report-context-content:focus-visible { outline: 2px solid var(--ring);
    outline-offset: 2px; }
  .ast-report-context-copy:disabled { cursor: wait; opacity: .7; }
  .ast-report-context-content { min-width: 0; min-height: 0; flex: 1 1 auto; margin: 0;
    padding: 12px 14px; overflow: auto; border: 1px solid var(--border);
    border-radius: 9px; background: var(--surface-2); color: var(--fg);
    font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre; tab-size: 2; }
  .ast-report-context-content.ast-wrap { white-space: pre-wrap; overflow-wrap: anywhere; }
  .ast-report-context-content code { font: inherit; }
  .ast-scope-runs { margin: 0; padding: 0; list-style: none; }
  .ast-scope-run { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 8px;
    padding: 10px 0; border-bottom: 1px solid var(--border); }
  .ast-scope-run:last-child { border-bottom: 0; }
  .ast-scope-run-num { color: var(--muted); font-size: 11px; padding-top: 2px;
    font-variant-numeric: tabular-nums; }
  .ast-scope-run-main { min-width: 0; }
  .ast-scope-run-main strong, .ast-scope-run-main code { display: block;
    overflow-wrap: anywhere; }
  .ast-scope-run-main strong { font-size: 13px; font-weight: 600; }
  .ast-scope-run-main code { margin-top: 2px; color: var(--muted); font-size: 11px; }
  .ast-scope-limit { padding: 10px 0; color: var(--muted); font-size: 12px;
    border-bottom: 1px solid var(--border); }
  .ast-messages { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 22px 24px;
    display: flex; flex-direction: column; gap: 12px; scroll-behavior: smooth;
    scrollbar-width: thin; scrollbar-color: transparent transparent; }
  .ast-messages:hover, .ast-messages:focus-within {
    scrollbar-color: color-mix(in srgb, var(--muted) 52%, transparent) transparent; }
  html[data-theme] .ast-messages::-webkit-scrollbar { width: 8px; height: 8px; }
  html[data-theme] .ast-messages::-webkit-scrollbar-track { background: transparent; }
  html[data-theme] .ast-messages::-webkit-scrollbar-thumb {
    min-height: 32px; border: 2px solid transparent; border-radius: 999px;
    background: transparent; background-clip: padding-box; }
  html[data-theme] .ast-messages:hover::-webkit-scrollbar-thumb,
  html[data-theme] .ast-messages:focus-within::-webkit-scrollbar-thumb {
    background: color-mix(in srgb, var(--muted) 52%, transparent);
    background-clip: padding-box; }
  html[data-theme] .ast-messages::-webkit-scrollbar-corner { background: transparent; }
  .ast-empty { width: min(100%, 720px); margin: auto; color: var(--muted); text-align: center; }
  .ast-empty strong { display: block; color: var(--fg); font-size: 15px; margin-bottom: 5px; }
  .ast-starters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px; margin-top: 18px; text-align: left; }
  .ast-starter { min-height: 44px; width: 100%; padding: 9px 11px; border-radius: 9px;
    border: 1px solid var(--border); background: var(--surface); color: var(--fg);
    cursor: pointer; text-align: left; line-height: 1.35; transition: background .15s; }
  .ast-starter:hover { background: var(--surface-2); }
  .ast-starter:focus-visible, .ast-close:focus-visible, .ast-send:focus-visible,
  .ast-source:focus-visible, .ast-clear:focus-visible, .ast-copy:focus-visible {
    outline: 2px solid var(--ring); outline-offset: 2px; }
  /* The question is the card and the answer is the page. An answer carries tables, code
     and lists; boxing it inside a bubble narrower than the panel is what made those hard
     to read, while a question is short and benefits from being visibly one object. */
  .ast-msg { max-width: 92%; border-radius: 12px; padding: 12px 14px;
    overflow-wrap: anywhere; }
  .ast-msg.user { max-width: min(88%, 620px); align-self: flex-end;
    background: var(--surface-2); color: var(--fg);
    border: 1px solid color-mix(in srgb, var(--muted) 45%, transparent);
    border-bottom-right-radius: 4px; }
  .ast-msg.user.ast-has-meta { width: min(420px, 100%); }
  .ast-msg.assistant { width: 100%; max-width: 100%; align-self: stretch;
    background: transparent; border: 0; border-radius: 0; padding: 2px 0 6px; }
  .ast-answer { line-height: 1.55; }
  .ast-msg.user .ast-answer, .ast-answer.ast-error { white-space: pre-wrap; }
  .ast-answer > :first-child { margin-top: 0; }
  .ast-answer > :last-child { margin-bottom: 0; }
  .ast-answer p { margin: 0 0 9px; }
  .ast-answer h3 { margin: 14px 0 7px; font-size: 14px; line-height: 1.35; }
  .ast-answer ul, .ast-answer ol { margin: 7px 0 10px; padding-left: 22px; }
  .ast-answer li + li { margin-top: 5px; }
  .ast-answer code { padding: 1px 4px; border-radius: 4px; background: var(--surface);
    border: 1px solid var(--border); font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo,
      Consolas, monospace; }
  .ast-answer pre { max-width: 100%; margin: 8px 0 10px; padding: 10px;
    overflow-x: auto; border-radius: 7px; background: var(--surface);
    border: 1px solid var(--border); }
  .ast-answer pre code { padding: 0; border: 0; background: transparent; white-space: pre; }
  .ast-answer blockquote { margin: 8px 0; padding-left: 10px; color: var(--muted);
    border-left: 3px solid var(--border); }
  .ast-answer a { color: var(--primary); text-underline-offset: 2px; }
  .ast-table-wrap { max-width: 100%; margin: 10px 0 12px; overflow-x: auto;
    border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
  .ast-table-wrap:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
  .ast-answer table { width: max-content; min-width: 100%; border-collapse: collapse;
    font-size: 12px; line-height: 1.45; }
  .ast-answer th, .ast-answer td { min-width: 108px; max-width: 260px; padding: 8px 10px;
    border-right: 1px solid var(--border); border-bottom: 1px solid var(--border);
    text-align: left; vertical-align: top; white-space: normal; overflow-wrap: anywhere; }
  .ast-answer th { background: var(--surface-2); font-weight: 650; }
  .ast-answer tr:last-child td { border-bottom: 0; }
  .ast-answer th:last-child, .ast-answer td:last-child { border-right: 0; }
  .ast-error { color: var(--fail); }
  .ast-msg-meta { color: var(--muted); font-size: 11px; margin-top: 8px; }
  /* The breakdown sits under the question, separated by a rule and with each number in an
     outlined pill: it is reference data, so it must be legible without competing with the
     question itself. */
  /* A mid-tone, not the app's hairline: on the neutral question card the hairline is
     invisible, and the rule and the value pills are what separate reference data from the
     question above it. Non-text boundaries carry their own contrast requirement. */
  .ast-msg.user .ast-msg-meta { margin-top: 11px; padding-top: 10px;
    border-top: 1px solid color-mix(in srgb, var(--muted) 72%, transparent); }
  .ast-msg.user .ast-msg-meta code {
    border: 1px solid color-mix(in srgb, var(--muted) 72%, transparent);
    background: var(--surface); color: var(--fg); }
  .ast-prompt-title { display: block; margin-bottom: 7px; font-weight: 650;
    letter-spacing: .01em; }
  .ast-prompt-parts { display: grid; gap: 4px; margin: 0; }
  .ast-prompt-row { display: grid; grid-template-columns: minmax(94px, 1fr) auto;
    align-items: baseline; gap: 10px; }
  .ast-prompt-row dt, .ast-prompt-row dd { margin: 0; }
  .ast-prompt-row dt { min-width: 0; overflow-wrap: anywhere; }
  .ast-prompt-row dd { font-variant-numeric: tabular-nums; }
  .ast-prompt-total { margin-top: 7px; padding-top: 7px; font-weight: 650;
    border-top: 1px solid color-mix(in srgb, var(--muted) 72%, transparent); }
  /* Quiet by default: one small outlined control under the breakdown, not a second
     primary action competing with Send. */
  .ast-context-review { display: inline-flex; align-items: center; gap: 6px;
    min-height: 28px; margin-top: 10px; padding: 0 9px; border-radius: 7px;
    border: 1px solid color-mix(in srgb, var(--muted) 72%, transparent);
    background: var(--surface);
    /* Brand blue on white lands just under 4.5 at this size; mixing in the foreground
       keeps it recognisably a link-coloured control and clears the threshold. */
    color: color-mix(in srgb, var(--primary) 78%, var(--fg));
    cursor: pointer; font: inherit; font-size: 11.5px; font-weight: 600; text-align: left;
    transition: background .15s, border-color .15s; }
  .ast-context-review svg { width: 13px; height: 13px; flex: 0 0 auto; }
  .ast-context-review:hover { background: var(--surface-2); border-color: var(--primary); }
  .ast-context-review:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
  .ast-output-warning { margin: 10px 0 2px; padding: 9px 11px; border-radius: 8px;
    background: var(--warn-bg); color: var(--warn); font-size: 12px; line-height: 1.5; }
  .ast-msg-footer { display: flex; align-items: center; justify-content: space-between;
    gap: 10px; margin-top: 8px; }
  .ast-msg-footer .ast-msg-meta { margin-top: 0; }
  .ast-msg-footer > .ast-copy:first-child { margin-left: auto; }
  /* Small and quiet: the answer is the content, and a full-size button under every reply
     turned the transcript into a column of controls. Full touch size returns on mobile. */
  .ast-copy { min-height: 26px; padding: 0 8px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center; gap: 5px;
    border: 1px solid transparent; border-radius: 7px; background: transparent;
    color: var(--muted); cursor: pointer; font: inherit; font-size: 11px; }
  .ast-copy svg { width: 13px; height: 13px; }
  .ast-copy:hover { color: var(--fg); background: var(--surface-2);
    border-color: var(--border); }
  .ast-copy:disabled { cursor: wait; opacity: .75; }
  .ast-copy svg { width: 14px; height: 14px; }
  .ast-sources { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }
  .ast-source { min-height: 32px; max-width: 100%; padding: 5px 8px; border-radius: 7px;
    border: 1px solid var(--border); background: var(--surface); color: var(--primary);
    cursor: pointer; font-size: 11px; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }
  .ast-retry { margin-top: 9px; min-height: 36px; }
  .ast-thinking { display: inline-flex; align-items: center; gap: 4px; min-height: 20px; }
  .ast-thinking i { width: 6px; height: 6px; border-radius: 50%; background: var(--muted);
    animation: ast-pulse 1.1s ease-in-out infinite; }
  .ast-thinking i:nth-child(2) { animation-delay: .14s; }
  .ast-thinking i:nth-child(3) { animation-delay: .28s; }
  .ast-progress { display: block; margin-top: 7px; color: var(--muted); font-size: 12px;
    line-height: 1.4; }
  .ast-progress-bar { display: block; width: 168px; max-width: 100%; height: 3px;
    margin-top: 6px; border-radius: 2px; background: var(--border); overflow: hidden; }
  .ast-progress-bar > i { display: block; height: 100%; border-radius: 2px;
    background: var(--primary); transition: width .3s linear; }
  @media (prefers-reduced-motion: reduce) { .ast-progress-bar > i { transition: none; } }
  .ast-msg.assistant.ast-waiting { width: auto; max-width: none; align-self: flex-start;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px;
    padding: 9px 11px;
    flex: 0 0 auto; }
  /* A blinking block after the last streamed character, so a slow model still looks alive. */
  .ast-caret { display: inline-block; width: 7px; height: 14px; margin-left: 1px;
    vertical-align: -2px; border-radius: 1px; background: var(--primary);
    animation: ast-blink 1s steps(2, start) infinite; }
  .ast-stopped-note { margin: 10px 0 2px; padding: 8px 11px; border-radius: 8px;
    border: 1px solid var(--border); background: var(--surface); color: var(--muted);
    font-size: 12px; line-height: 1.5; }
  .ast-stop { min-height: 44px; padding: 0 15px; }
  .ast-stop svg { width: 15px; height: 15px; }
  .ast-stop[disabled] { opacity: .5; cursor: not-allowed; }
  @keyframes ast-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) {
    .ast-caret { animation: none; }
  }
  @keyframes ast-pulse { 0%, 70%, 100% { opacity: .25; } 35% { opacity: 1; } }
  #ast-chats-dialog { width: min(520px, calc(100vw - 32px)); max-height: min(70vh, 560px);
    padding: 0; border: 1px solid var(--border); border-radius: 14px;
    background: var(--surface); color: var(--fg); overflow: hidden; }
  #ast-chats-dialog::backdrop { background: rgba(0, 0, 0, .38); }
  /* In the header row, left of the close control: the two window-level actions belong
     together, and a full-width primary button above the list shouted over the chats. */
  .ast-chat-new { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto;
    min-height: 32px; padding: 0 11px; border: 1px solid var(--border);
    border-radius: 8px; background: var(--surface); color: var(--primary);
    cursor: pointer; font: inherit; font-size: 12px; font-weight: 650; }
  .ast-chat-new:hover { background: var(--surface-2); border-color: var(--primary); }
  .ast-chat-new:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
  .ast-chat-list { list-style: none; margin: 0; padding: 12px 12px 14px; overflow-y: auto;
    max-height: min(48vh, 380px); }
  .ast-chat-row { display: flex; align-items: stretch; gap: 6px; margin: 0 0 6px; }
  .ast-chat-item { flex: 1 1 auto; display: block; text-align: left; padding: 9px 11px;
    border: 1px solid var(--border); border-radius: 9px; background: var(--surface-2);
    color: var(--fg); font: inherit; cursor: pointer; }
  .ast-chat-item:hover { border-color: var(--primary); }
  .ast-chat-item:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  /* Marked by its own outline and a word, not a bar down the left edge: the edge marker
     read as a scrollbar or a nesting cue rather than "this is the one you are reading". */
  .ast-chat-item[aria-current="true"] { border-color: var(--primary);
    background: color-mix(in srgb, var(--primary) 8%, var(--surface-2)); }
  .ast-chat-current { margin-left: 6px; padding: 1px 6px; border-radius: 999px;
    background: color-mix(in srgb, var(--primary) 16%, transparent);
    color: var(--primary); font-size: 10px; font-weight: 700; letter-spacing: .02em;
    text-transform: uppercase; white-space: nowrap; }
  .ast-chat-title { display: block; font-weight: 600; font-size: 13px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ast-chat-meta { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; }
  .ast-chat-row-confirming { align-items: center; gap: 8px; padding: 8px 11px;
    border: 1px solid var(--danger, #dc2626); border-radius: 9px;
    background: var(--surface-2); }
  .ast-chat-confirm-label { flex: 1 1 auto; font-size: 12px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; }
  .ast-chat-confirm, .ast-chat-cancel { flex: 0 0 auto; min-height: 30px; padding: 0 11px;
    border-radius: 8px; border: 1px solid var(--border); background: var(--surface);
    color: var(--fg); font: inherit; font-size: 12px; cursor: pointer; }
  .ast-chat-confirm { border-color: var(--danger, #dc2626);
    color: var(--danger, #dc2626); font-weight: 600; }
  .ast-chat-confirm:focus-visible, .ast-chat-cancel:focus-visible {
    outline: 2px solid var(--ring); outline-offset: 1px; }
  .ast-chat-name-input { flex: 1 1 auto; min-width: 0; min-height: 30px; padding: 0 9px;
    border: 1px solid var(--primary); border-radius: 8px; background: var(--surface);
    color: var(--fg); font: inherit; font-size: 12px; }
  .ast-chat-name-input:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .ast-chat-rename, .ast-chat-delete { flex: 0 0 auto; width: 34px; display: inline-flex;
    align-items: center; justify-content: center; border: 1px solid transparent;
    border-radius: 9px; background: transparent; color: var(--muted); cursor: pointer;
    transition: color .15s, background .15s, border-color .15s; }
  .ast-chat-rename svg, .ast-chat-delete svg { width: 15px; height: 15px; }
  .ast-chat-rename:hover { border-color: var(--primary); color: var(--primary);
    background: color-mix(in srgb, var(--primary) 10%, transparent); }
  .ast-chat-delete:hover { border-color: var(--danger, #dc2626);
    color: var(--danger, #dc2626);
    background: color-mix(in srgb, var(--danger, #dc2626) 10%, transparent); }
  .ast-chat-delete:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .ast-chat-delete:disabled { opacity: .4; cursor: not-allowed; }
  .ast-clear:disabled { opacity: .5; cursor: not-allowed; }
  @media (max-width: 700px) {
    #ast-chats-dialog { width: 100vw; max-width: none; height: 100dvh; max-height: none;
      margin: 0; border: 0; border-radius: 0; }
    .ast-chat-list { max-height: none; }
  }
  .ast-clear-confirm { flex: 0 0 auto; display: flex; align-items: center; gap: 10px;
    padding: 10px 24px; border-bottom: 1px solid var(--border);
    background: var(--surface-2); }
  .ast-clear-confirm-text { flex: 1 1 auto; font-size: 12px; line-height: 1.45; }
  .ast-clear-keep, .ast-clear-yes { flex: 0 0 auto; min-height: 30px; padding: 0 12px;
    border-radius: 8px; border: 1px solid var(--border); background: var(--surface);
    color: var(--fg); font: inherit; font-size: 12px; cursor: pointer; }
  .ast-clear-yes { border-color: var(--danger, #dc2626); color: var(--danger, #dc2626);
    font-weight: 650; }
  .ast-clear-keep:focus-visible, .ast-clear-yes:focus-visible {
    outline: 2px solid var(--ring); outline-offset: 1px; }
  @media (max-width: 700px) { .ast-clear-confirm { padding: 10px 12px; } }
  .ast-unavailable { flex: 1 1 auto; overflow: auto; padding: 22px 24px 24px; }
  .ast-unavailable-title { margin: 0 0 8px; font-size: 15px; font-weight: 650; }
  .ast-unavailable-lead { margin: 0 0 12px; color: var(--muted); font-size: 13px;
    line-height: 1.5; }
  .ast-unavailable-reason { margin: 0 0 12px; padding: 11px 12px; border-radius: 9px;
    border: 1px solid var(--border); background: var(--surface-2); overflow-x: auto;
    font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
  .ast-unavailable-hint { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.5; }
  @media (max-width: 700px) { .ast-unavailable { padding: 16px 12px 20px; } }
  .ast-form { flex: 0 0 auto; border-top: 1px solid var(--border); padding: 14px 24px 20px;
    background: var(--surface); }
  .ast-label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 6px; }
  /* The ghost is a second copy of the field's own text plus the completion, sitting
     exactly under the real one: same box, same metrics, so the grey tail lines up with
     what has been typed however it wraps. */
  .ast-question-wrap { position: relative; }
  /* Above the field, not below it: the composer is already at the bottom of the panel. */
  .ast-commands { position: absolute; left: 0; right: 0; bottom: calc(100% + 6px);
    z-index: 3; margin: 0; padding: 4px; list-style: none; max-height: 240px;
    overflow-y: auto; border: 1px solid var(--border); border-radius: 10px;
    background: var(--surface); box-shadow: 0 10px 30px rgba(0, 0, 0, .18); }
  .ast-command { display: block; width: 100%; padding: 7px 9px; border: 0;
    border-radius: 7px; background: transparent; color: var(--fg); cursor: pointer;
    font: inherit; font-size: 12px; text-align: left; }
  .ast-command:hover, .ast-command[aria-selected="true"] { background: var(--surface-2); }
  .ast-command[aria-selected="true"] { outline: 1px solid var(--primary); }
  /* Brand blue on this surface lands just under 4.5 at 12px; mixing in the foreground
     keeps it recognisably the command colour and clears the threshold for text. */
  .ast-command b { display: inline-block; min-width: 74px; font-weight: 650;
    color: color-mix(in srgb, var(--primary) 78%, var(--fg)); }
  .ast-command span { color: var(--muted); }
  .ast-ghost { position: absolute; inset: 0; z-index: 0; overflow: hidden;
    padding: 10px 11px; border: 1px solid transparent; border-radius: 9px;
    color: var(--muted); font: inherit; line-height: 1.45; white-space: pre-wrap;
    overflow-wrap: anywhere; pointer-events: none; }
  .ast-ghost b { font-weight: inherit; color: transparent; }
  .ast-question { position: relative; z-index: 1; background: transparent; }
  .ast-question:not(:placeholder-shown) + #ast-ghost { }
  .ast-visually-hidden { position: absolute; width: 1px; height: 1px; margin: -1px;
    padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
  .ast-question { display: block; width: 100%; min-height: 88px; max-height: 220px;
    resize: vertical; padding: 10px 11px; border: 1px solid var(--border); border-radius: 9px;
    background: var(--surface-2); color: var(--fg); font: inherit; line-height: 1.45; }
  .ast-question:focus { outline: 2px solid var(--ring); outline-offset: 1px;
    border-color: var(--primary); }
  .ast-form-row { display: flex; align-items: center; gap: 10px; margin-top: 9px; }
  .ast-hint { color: var(--muted); font-size: 11px; flex: 1 1 auto; }
  .ast-form-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
  .ast-send { min-height: 44px; padding: 0 15px; }
  .ast-send[disabled] { opacity: .5; cursor: not-allowed; }
  .ast-send svg { width: 16px; height: 16px; }
  @media (max-width: 700px) {
    #assistant-dialog.ast-dialog {
      width: 100vw !important; height: 100dvh !important;
      min-width: 0; min-height: 0; max-width: none; max-height: none;
      margin: 0; border: 0; border-radius: 0; resize: none;
    }
    .ast-starters { grid-template-columns: 1fr; }
    .ast-limit-tooltip { position: fixed; left: 12px; right: 12px;
      bottom: max(64px, calc(52px + env(safe-area-inset-bottom))); width: auto; }
    .ast-messages { padding: 14px 12px; }
    .ast-form { padding: 10px 12px max(12px, env(safe-area-inset-bottom)); }
    .ast-question { font-size: 16px; }
    .ast-msg.user { max-width: 88%; }
    .ast-prompt-row { grid-template-columns: minmax(84px, 1fr) auto; }
    #ast-report-context-dialog { width: 100vw; max-width: none; height: 100dvh;
      max-height: none; margin: 0; border: 0; border-radius: 0; }
    .ast-report-context-toolbar { align-items: stretch; flex-wrap: wrap; }
    .ast-report-context-format { flex-basis: 100%; }
    .ast-report-context-copy, .ast-report-context-wrap { flex: 1 1 140px; }
  }
  @media (max-height: 620px) {
    #assistant-dialog.ast-dialog { height: 96dvh; min-height: 0; }
    .ast-question { min-height: 58px; max-height: 100px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .ast-messages { scroll-behavior: auto; }
    .ast-thinking i { animation: none; opacity: .65; }
    .ast-limit-tooltip { transition: none; }
  }
"""

_BUTTON = r"""
    <button id="assistant-btn" class="btn" type="button" aria-controls="assistant-dialog"
            aria-expanded="false" hidden>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>
        <path d="M8 9h8M8 13h5"/>
      </svg>
      <span id="assistant-btn-label">AI assistant</span>
    </button>
"""

_PANEL = r"""
<dialog id="assistant-dialog" class="ast-dialog" aria-labelledby="ast-title">
  <div class="ast-head">
    <div class="ast-title-wrap">
      <h2 id="ast-title" class="ast-title">
        <span id="ast-title-text">Report assistant</span><code class="ast-beta">BETA</code>
      </h2>
      <div class="ast-title-meta">
        <div id="ast-provider" class="ast-provider"></div>
      </div>
    </div>
    <div class="ast-head-actions">
      <button id="ast-chats" class="ast-clear" type="button" hidden
              aria-haspopup="dialog" aria-controls="ast-chats-dialog"
              aria-expanded="false">Chats</button>
      <button id="ast-clear" class="ast-clear" type="button" hidden>Clear chat</button>
      <button id="ast-close" class="btn ast-close" type="button" aria-label="Close assistant">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M18 6 6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>
  </div>
  <div id="ast-context" class="ast-context" hidden>
    <div class="ast-scope-row">
      <span id="ast-scope" class="ast-scope" aria-live="polite"></span>
      <div class="ast-scope-aside">
        <span id="ast-session-tokens" class="ast-session-tokens" aria-live="polite" hidden></span>
        <button id="ast-scope-list" class="ast-scope-list" type="button"
                aria-haspopup="dialog" aria-controls="ast-scope-dialog"
                aria-expanded="false" hidden>View list</button>
      </div>
    </div>
  </div>
  <div id="ast-unavailable" class="ast-unavailable" hidden>
    <h3 id="ast-unavailable-title" class="ast-unavailable-title"></h3>
    <p id="ast-unavailable-lead" class="ast-unavailable-lead"></p>
    <pre class="ast-unavailable-reason"><code id="ast-unavailable-reason"></code></pre>
    <p id="ast-unavailable-hint" class="ast-unavailable-hint"></p>
  </div>
  <div id="ast-clear-confirm" class="ast-clear-confirm" role="alertdialog"
       aria-labelledby="ast-clear-confirm-text" hidden>
    <span id="ast-clear-confirm-text" class="ast-clear-confirm-text"></span>
    <button id="ast-clear-keep" class="ast-clear-keep" type="button"></button>
    <button id="ast-clear-yes" class="ast-clear-yes" type="button"></button>
  </div>
  <div id="ast-messages" class="ast-messages" aria-live="polite" aria-busy="false"></div>
  <form id="ast-form" class="ast-form">
    <label id="ast-question-label" class="ast-label" for="ast-question">Ask about reports</label>
    <div class="ast-question-wrap">
      <ul id="ast-commands" class="ast-commands" role="listbox"
          aria-label="Assistant commands" hidden></ul>
      <div id="ast-ghost" class="ast-ghost" aria-hidden="true" hidden></div>
      <textarea id="ast-question" class="ast-question" maxlength="4000" required
                autocomplete="off" spellcheck="true"
                aria-describedby="ast-ghost-hint"></textarea>
      <span id="ast-ghost-hint" class="ast-visually-hidden"></span>
    </div>
    <div class="ast-form-row">
      <span id="ast-hint" class="ast-hint">Ctrl/⌘ + Enter to send</span>
      <div class="ast-form-actions">
        <div id="ast-processing" class="ast-processing" aria-live="polite"></div>
        <button id="ast-stop" class="btn ast-stop" type="button" hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="2"/>
          </svg>
          <span id="ast-stop-label">Stop</span>
        </button>
        <button id="ast-send" class="btn primary ast-send" type="submit">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>
          </svg>
          <span id="ast-send-label">Send</span>
        </button>
      </div>
    </div>
  </form>
</dialog>
<dialog id="ast-chats-dialog" aria-labelledby="ast-chats-dialog-title">
  <div class="ast-scope-dialog-head">
    <div class="ast-scope-dialog-title-wrap">
      <h2 id="ast-chats-dialog-title">Your chats</h2>
      <div id="ast-chats-dialog-summary" class="ast-scope-dialog-summary"></div>
    </div>
    <button id="ast-chat-new" class="ast-chat-new" type="button">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 5v14M5 12h14"/>
      </svg>
      <span id="ast-chat-new-label">New chat</span>
    </button>
    <button id="ast-chats-dialog-close" class="btn ast-scope-dialog-close" type="button"
            aria-label="Close chat list">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <ol id="ast-chat-list" class="ast-chat-list"></ol>
</dialog>

<dialog id="ast-scope-dialog" aria-labelledby="ast-scope-dialog-title">
  <div class="ast-scope-dialog-head">
    <div class="ast-scope-dialog-title-wrap">
      <h2 id="ast-scope-dialog-title">Selected runs</h2>
      <div id="ast-scope-dialog-summary" class="ast-scope-dialog-summary"></div>
    </div>
    <button id="ast-scope-dialog-close" class="btn ast-scope-dialog-close" type="button"
            aria-label="Close selected runs">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="ast-scope-dialog-body">
    <ol id="ast-scope-runs" class="ast-scope-runs"></ol>
  </div>
</dialog>
<dialog id="ast-report-context-dialog" aria-labelledby="ast-report-context-dialog-title">
  <div class="ast-scope-dialog-head">
    <div class="ast-scope-dialog-title-wrap">
      <h2 id="ast-report-context-dialog-title">Report context sent to LLM</h2>
      <div id="ast-report-context-summary" class="ast-scope-dialog-summary"></div>
    </div>
    <button id="ast-report-context-close" class="btn ast-scope-dialog-close" type="button"
            aria-label="Close report context">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="ast-report-context-body">
    <p id="ast-report-context-note" class="ast-report-context-note"></p>
    <div class="ast-report-context-toolbar">
      <div id="ast-report-context-format" class="ast-report-context-format"></div>
      <button id="ast-report-context-wrap" class="ast-report-context-wrap" type="button"
              aria-pressed="true">Wrap lines</button>
      <button id="ast-report-context-copy" class="ast-report-context-copy" type="button">
        Copy context
      </button>
    </div>
    <pre id="ast-report-context-content" class="ast-report-context-content"
         tabindex="0"><code id="ast-report-context-code"></code></pre>
  </div>
</dialog>
"""

_JS = r"""
  // -- Report assistant ---------------------------------------------------------------
  // Kept in a separate Python module but injected inside this IIFE so it can reuse the
  // dashboard's current filters, selected report ids and safe openDetail() navigation.
  var AST_I18N = {
    en: {
      button: "AI assistant", title: "Report assistant", close: "Close assistant",
      tableLabel: "Answer table",
      allScope: "All readable reports", selectedScope: "{n} reports selected",
      selectedScopeLimited: "{total} reports selected · the first {used} will be used",
      scopeList: "View list", scopeListTitle: "Selected runs",
      scopeListClose: "Close selected runs", scopeListSummary: "{n} runs selected",
      scopeListLimit: "The reports below are selected too, but are outside the {n}-report assistant limit.",
      filtersScope: "Current filters: {value}", ask: "Ask about reports", limits: "Limits",
      localProcessing: "Readable in this scope: {visible}. The local model will process the complete test tree for {processed}; only compacted evidence leaves the server.",
      directProcessing: "Readable in this scope: {visible}. The external API receives a newest-first snapshot. If it exceeds the limit, older summaries or non-fitting failure records are omitted and the answer is marked as context-limited.",
      directLimitSummaries: "summaries ≤ {value} newest",
      contextLimit: "all report evidence in this request ≤ {value}",
      tracebackLimit: "traceback ≤ {value} / test",
      captureLimit: "stdout/stderr/log ≤ {value} / test",
      outputTokenLimit: "answer output ≤ {value} tokens",
      localLimitReports: "reports processed: {value}",
      localLimitCases: "test cases: all in scope",
      localOutboundLimit: "external evidence ≤ {value}",
      localBudgetLimit: "local processing ≤ {value} s",
      placeholder: "What changed in the latest runs?", hint: "Ctrl/⌘ + Enter to send",
      send: "Send", stop: "Stop", stopHint: "Stop generating this answer",
      stoppedNote: "Stopped. This answer is incomplete.",
      stoppedEmpty: "Stopped before the model produced anything.",
      clear: "Clear chat", introTitle: "Ask the report history",
      promptSize: "Sent to LLM", promptSystem: "System", promptUser: "User",
      promptContext: "Context data", promptDocs: "Documentation", promptHistory: "History",
      promptStructure: "Prompt structure", promptTotal: "Total",
      promptNothingSent: "Nothing was sent to the LLM: no readable reports in this scope.",
      noReportsInScope: "No readable reports match the current scope. Clear or widen the dashboard filters and try again.",
      contextReview: "Context overview", contextDialogTitle: "Report context sent to LLM",
      contextDialogClose: "Close report context", copyContext: "Copy context",
      contextWrap: "Wrap lines", contextWrapTitle: "Toggle wrapping of long context lines",
      contextDirectFormat: "Direct snapshot · header + JSON Lines",
      contextLocalFormat: "Local reduction · plain text",
      contextNote: "Exact report-evidence block after RBAC filtering. System instructions, your question and chat history are not shown here.",
      copyAnswer: "Copy", copied: "Copied", copyFailed: "Copy failed",
      tokens: "LLM tokens: input {input} · output {output} · total {total}",
      sessionTokens: "Session total: {total} tokens",
      intro: "Answers use only reports you may read. This tab keeps the chat after refresh.",
      thinking: "Reviewing reports…", retry: "Try again", noDetail: "The request failed.",
      chats: "Chats", chatsTitle: "Your chats", chatsClose: "Close chat list",
      chatsSummary: "{n} saved on the server", newChat: "New chat",
      chatMeta: "{n} messages · {when}", chatUntitled: "New chat",
      deleteChat: "Delete this chat", chatsEmpty: "No saved chats yet.",
      renameChat: "Rename this chat", renameSave: "Save",
      renamePlaceholder: "Name this chat",
      deleteChatConfirm: "Delete “{title}”?", deleteChatYes: "Delete",
      deleteChatNo: "Cancel", chatOpen: "open",
      clearConfirm: "Clear this chat? The copy saved on the server goes too.",
      clearConfirmLocal: "Clear this chat? It is only in this tab, so it cannot come back.",
      clearConfirmYes: "Clear", clearConfirmNo: "Keep",
      command_bug: "Draft a bug report from a failure",
      command_flaky: "Judge a flaky test, and whether to quarantine it",
      command_priority: "What to fix first, and why",
      command_compare: "What changed between runs",
      command_test: "Write pytest for code you paste",
      progressLoadingModel: "Loading the local model…",
      progressReduce: "Reading the report tree locally · {done} chunks · {elapsed} s of {budget} s",
      progressReduceNoBudget: "Reading the report tree locally · {done} chunks · {elapsed} s",
      progressMerge: "Merging what was read · pass {pass} · {elapsed} s",
      invalidRequest: "The request was rejected: {reason}",
      outputLimited: "The model reached its output-token limit, so this answer may be incomplete. Ask a narrower question or increase AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS.",
      unavailableTitle: "The assistant is not available",
      unavailableLead: "This deployment asked for a report assistant, but the API server could not start it.",
      unavailableHint: "The same line is in the API-server log. Fix the configuration and restart the server; nothing else in the viewer is affected.",
      truncated: "Context was limited", reports: "{n} reports", direct: "direct context",
      suggestionHint: "Press Tab to complete: {text}",
      starters: ["What broke in the latest runs?", "Which failures look flaky?", "What became slower?"]
    },
    ru: {
      button: "AI-ассистент", title: "Помощник по отчётам", close: "Закрыть помощника",
      tableLabel: "Таблица ответа",
      allScope: "Все доступные отчёты", selectedScope: "Выбрано отчётов: {n}",
      selectedScopeLimited: "Выбрано отчётов: {total} · будут использованы первые {used}",
      scopeList: "Список", scopeListTitle: "Выбранные прогоны",
      scopeListClose: "Закрыть список выбранных прогонов", scopeListSummary: "Выбрано прогонов: {n}",
      scopeListLimit: "Следующие отчёты тоже выбраны, но не входят в лимит помощника из {n} отчётов.",
      filtersScope: "Текущие фильтры: {value}", ask: "Спросить об отчётах", limits: "Ограничения",
      localProcessing: "Доступно в этой области: {visible}. Локальная модель обработает полное дерево тестов для {processed}; наружу уйдут только сжатые факты.",
      directProcessing: "Доступно в этой области: {visible}. Во внешний API уйдёт срез от новых прогонов. Если данные превысят лимит, старые сводки или не поместившиеся целиком записи падений не войдут в запрос, а ответ будет отмечен как ограниченный.",
      directLimitSummaries: "сводки ≤ {value} последних",
      contextLimit: "данные всех отчётов в запросе ≤ {value}",
      tracebackLimit: "traceback ≤ {value} / тест",
      captureLimit: "stdout/stderr/log ≤ {value} / тест",
      outputTokenLimit: "ответ ≤ {value} токенов",
      localLimitReports: "обработано отчётов: {value}",
      localLimitCases: "test cases: все в области",
      localOutboundLimit: "факты наружу ≤ {value}",
      localBudgetLimit: "локальная обработка ≤ {value} с",
      placeholder: "Что изменилось в последних прогонах?", hint: "Ctrl/⌘ + Enter — отправить",
      send: "Отправить", stop: "Остановить", stopHint: "Прервать генерацию ответа",
      stoppedNote: "Остановлено. Ответ неполный.",
      stoppedEmpty: "Остановлено до того, как модель что-то ответила.",
      clear: "Очистить чат", introTitle: "Спросите историю прогонов",
      promptSize: "Отправлено в LLM", promptSystem: "System", promptUser: "User",
      promptContext: "Данные отчётов", promptDocs: "Документация", promptHistory: "История",
      promptStructure: "Структура промпта", promptTotal: "Всего",
      promptNothingSent: "В LLM ничего не отправлялось: в этой области нет доступных отчётов.",
      noReportsInScope: "В текущей области нет доступных отчётов. Сбросьте или расширьте фильтры и попробуйте снова.",
      contextReview: "Обзор контекста", contextDialogTitle: "Контекст отчётов, отправленный в LLM",
      contextDialogClose: "Закрыть контекст отчётов", copyContext: "Копировать контекст",
      contextWrap: "Перенос строк", contextWrapTitle: "Включить или выключить перенос длинных строк контекста",
      contextDirectFormat: "Прямой срез · заголовок + JSON Lines",
      contextLocalFormat: "Локальное сжатие · обычный текст",
      contextNote: "Точный блок данных отчётов после проверки RBAC. Системная инструкция, ваш вопрос и история чата здесь не показаны.",
      copyAnswer: "Копировать", copied: "Скопировано", copyFailed: "Ошибка копирования",
      tokens: "Токены LLM: вход {input} · ответ {output} · всего {total}",
      sessionTokens: "За сессию: {total} токенов",
      intro: "Ответ строится только по доступным вам отчётам. Эта вкладка сохранит чат после обновления.",
      thinking: "Изучаю отчёты…", retry: "Повторить", noDetail: "Запрос не выполнен.",
      chats: "Чаты", chatsTitle: "Ваши чаты", chatsClose: "Закрыть список чатов",
      chatsSummary: "Сохранено на сервере: {n}", newChat: "Новый чат",
      chatMeta: "Сообщений: {n} · {when}", chatUntitled: "Новый чат",
      deleteChat: "Удалить этот чат", chatsEmpty: "Сохранённых чатов пока нет.",
      renameChat: "Переименовать чат", renameSave: "Сохранить",
      renamePlaceholder: "Название чата",
      deleteChatConfirm: "Удалить «{title}»?", deleteChatYes: "Удалить",
      deleteChatNo: "Отмена", chatOpen: "открыт",
      clearConfirm: "Очистить этот чат? Копия на сервере тоже будет удалена.",
      clearConfirmLocal: "Очистить этот чат? Он есть только в этой вкладке — вернуть будет нельзя.",
      clearConfirmYes: "Очистить", clearConfirmNo: "Оставить",
      command_bug: "Оформить багрепорт по падению",
      command_flaky: "Разобрать flaky-тест и нужен ли карантин",
      command_priority: "Что чинить в первую очередь и почему",
      command_compare: "Что изменилось между прогонами",
      command_test: "Написать pytest по присланному коду",
      progressLoadingModel: "Загружаю локальную модель…",
      progressReduce: "Читаю дерево отчётов локально · порций: {done} · {elapsed} с из {budget} с",
      progressReduceNoBudget: "Читаю дерево отчётов локально · порций: {done} · {elapsed} с",
      progressMerge: "Свожу прочитанное · проход {pass} · {elapsed} с",
      invalidRequest: "Запрос отклонён: {reason}",
      outputLimited: "Модель достигла лимита токенов ответа, поэтому текст может быть неполным. Сузьте вопрос или увеличьте AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS.",
      unavailableTitle: "Ассистент недоступен",
      unavailableLead: "На этом стенде помощник по отчётам включён, но API-сервер не смог его запустить.",
      unavailableHint: "Та же строка есть в логе API-сервера. Поправьте конфигурацию и перезапустите сервер — на остальную часть интерфейса это не влияет.",
      truncated: "Контекст был ограничен", reports: "Отчётов: {n}", direct: "контекст без сжатия",
      suggestionHint: "Нажмите Tab, чтобы дописать: {text}",
      starters: ["Что сломалось в последних прогонах?", "Какие падения похожи на flaky?", "Какие тесты замедлились?"]
    }
  };
  function astT(key) {
    var dict = AST_I18N[LOCALE] || AST_I18N.en;
    return dict[key] == null ? AST_I18N.en[key] : dict[key];
  }
  function astFmt(text, key, value) { return String(text).replace("{" + key + "}", value); }

  //: Set once the server says the feature was configured but could not start.
  var astUnavailable = false;
  //: Latest local-phase progress for the one in-flight request, or null. Only one
  //: request can be pending at a time, so a single value is always the right one.
  var astProgress = null;
  var astButton = document.getElementById("assistant-btn");
  var astDialog = document.getElementById("assistant-dialog");
  var astMessages = document.getElementById("ast-messages");
  var astSessionTokens = document.getElementById("ast-session-tokens");
  var astQuestion = document.getElementById("ast-question");
  var astSend = document.getElementById("ast-send");
  var astStop = document.getElementById("ast-stop");
  var astClear = document.getElementById("ast-clear");
  var astChats = document.getElementById("ast-chats");
  var astChatsDialog = document.getElementById("ast-chats-dialog");
  var astChatList = document.getElementById("ast-chat-list");
  var astClearConfirm = document.getElementById("ast-clear-confirm");
  var astCommands = document.getElementById("ast-commands");
  //: Commands the server published, and the state of the menu built from them.
  var AST_COMMANDS = [];
  var astCommandList = [];
  var astCommandIndex = 0;
  var astGhost = document.getElementById("ast-ghost");
  var astGhostHint = document.getElementById("ast-ghost-hint");
  //: The completion currently offered, or "" when there is none.
  var astSuggestion = "";
  var astContext = document.getElementById("ast-context");
  var astScopeList = document.getElementById("ast-scope-list");
  var astScopeDialog = document.getElementById("ast-scope-dialog");
  var astReportContextDialog = document.getElementById("ast-report-context-dialog");
  var astReportContextCopy = document.getElementById("ast-report-context-copy");
  var astReportContextWrap = document.getElementById("ast-report-context-wrap");
  var AST_STORAGE_PREFIX = "airflow-pytest-plugin:assistant:v2:" + location.pathname + ":";
  var AST_WINDOW_PREFIX = "airflow-pytest-plugin:assistant-window:v1:" + location.pathname + ":";
  var AST_STORAGE_KEY = null;
  var AST_WINDOW_PREFS_KEY = null, AST_WINDOW_OPEN_KEY = null, AST_CONTEXT_WRAP_KEY = null;
  var AST_MAX_MESSAGES = 12;
  var AST_MAX_HISTORY_CHARS = 4000;
  var AST_SERVER_HISTORY = false;
  var AST_MAX_SESSION_TOKENS = 1_000_000_000_000_000;
  var astLastFocus = null, astPending = false, astLastQuestion = "", astStatus = null;
  var astController = null;
  var astResizeTimer = null, astWindowWidth = null, astWindowHeight = null;
  var astWindowDirty = false, astActiveReportContext = null, astReportContextTrigger = null;
  var astReportContextIndex = null;
  var astContextWrapped = true, astSessionTotalTokens = 0;
  var astTranscript = [];
  //: The stored chat being read. Empty means "whichever the server calls newest", which
  //: is what a freshly opened panel wants. Only meaningful with server-side history.
  var astConversation = "";
  var astConversations = [];

  function astApplyText() {
    document.getElementById("assistant-btn-label").textContent = astT("button");
    document.getElementById("ast-title-text").textContent = astT("title");
    document.getElementById("ast-close").setAttribute("aria-label", astT("close"));
    document.getElementById("ast-question-label").textContent = astT("ask");
    astClear.textContent = astT("clear");
    astQuestion.placeholder = astT("placeholder");
    document.getElementById("ast-hint").textContent = astT("hint");
    document.getElementById("ast-send-label").textContent = astT("send");
    document.getElementById("ast-stop-label").textContent = astT("stop");
    astStop.setAttribute("aria-label", astT("stopHint"));
    astChats.textContent = astT("chats");
    document.getElementById("ast-chats-dialog-title").textContent = astT("chatsTitle");
    document.getElementById("ast-chats-dialog-close")
      .setAttribute("aria-label", astT("chatsClose"));
    // The label only: the button also holds an icon, and textContent would erase it.
    document.getElementById("ast-chat-new-label").textContent = astT("newChat");
    if (astChatsDialog.open) astRenderChatList();
    astScopeList.textContent = astT("scopeList");
    document.getElementById("ast-scope-dialog-title").textContent = astT("scopeListTitle");
    document.getElementById("ast-scope-dialog-close").setAttribute("aria-label", astT("scopeListClose"));
    document.getElementById("ast-report-context-dialog-title").textContent = astT("contextDialogTitle");
    document.getElementById("ast-report-context-close").setAttribute("aria-label", astT("contextDialogClose"));
    document.getElementById("ast-report-context-note").textContent = astT("contextNote");
    astReportContextCopy.textContent = astT("copyContext");
    astReportContextWrap.textContent = astT("contextWrap");
    astReportContextWrap.title = astT("contextWrapTitle");
    astApplyContextWrap();
    astRenderSessionTokens();
    if (astActiveReportContext) astRenderReportContext(astActiveReportContext);
    astApplyProviderText(); astUpdateScope();
    if (astTranscript.length && astMessages.children.length) astRenderTranscript();
    else if (astMessages.querySelector(".ast-empty")) astEmpty();
  }

  function astShowUnavailable(status) {
    astUnavailable = true;
    document.getElementById("ast-unavailable-title").textContent = astT("unavailableTitle");
    document.getElementById("ast-unavailable-lead").textContent = astT("unavailableLead");
    // The reason is written by the server for an operator and is not translated; it is
    // rendered as text so a provider name can never become markup.
    document.getElementById("ast-unavailable-reason").textContent =
      status.reason || astT("noDetail");
    document.getElementById("ast-unavailable-hint").textContent = astT("unavailableHint");
    document.getElementById("ast-unavailable").hidden = false;
    astMessages.hidden = true;
    document.getElementById("ast-form").hidden = true;
    astClear.hidden = true;
    astChats.hidden = true;
    astContext.hidden = true;
    astApplyProviderText();
    astButton.hidden = false;
  }

  function astApplyProviderText() {
    if (!astStatus) return;
    var parts = [astStatus.provider, astStatus.model].filter(Boolean);
    parts.push(astStatus.context_model || astT("direct"));
    document.getElementById("ast-provider").textContent = parts.join(" · ");
  }

  //: What the field offers to finish. The starters the panel already shows, plus the
  //: questions this user has asked before -- no model call: a request per keystroke would
  //: cost real money, add latency to typing and burn the rate limit.
  function astSuggestionPool() {
    var pool = astT("starters").slice();
    for (var i = astTranscript.length - 1; i >= 0; i--) {
      var item = astTranscript[i];
      if (item.role === "user" && item.text && pool.indexOf(item.text) === -1) {
        pool.push(item.text);
      }
    }
    return pool;
  }

  function astSuggestionFor(typed) {
    var text = String(typed || "");
    if (text.length < 2 || text.indexOf("\n") !== -1) return "";
    var lowered = text.toLowerCase();
    var pool = astSuggestionPool();
    for (var i = 0; i < pool.length; i++) {
      var candidate = pool[i];
      if (candidate.length > text.length
          && candidate.toLowerCase().indexOf(lowered) === 0) {
        return candidate;
      }
    }
    return "";
  }

  function astRenderGhost() {
    var typed = astQuestion.value;
    astSuggestion = astPending ? "" : astSuggestionFor(typed);
    if (!astSuggestion) {
      astGhost.hidden = true;
      astGhost.textContent = "";
      astGhostHint.textContent = "";
      return;
    }
    // The typed part is rendered transparent so only the tail shows, and it keeps the
    // completion aligned with the real text under every wrap.
    astGhost.textContent = "";
    var typedPart = document.createElement("b");
    typedPart.textContent = typed;
    astGhost.appendChild(typedPart);
    astGhost.appendChild(
      document.createTextNode(astSuggestion.slice(typed.length))
    );
    astGhost.hidden = false;
    astGhostHint.textContent = astFmt(astT("suggestionHint"), "text", astSuggestion);
  }

  function astAcceptSuggestion() {
    if (!astSuggestion) return false;
    astQuestion.value = astSuggestion;
    astRenderGhost();
    return true;
  }

  function astSelectedReports() {
    var available = (typeof allReports !== "undefined" && allReports.length) ? allReports : reports;
    return available.filter(function (report) { return selectedIds.has(report.id); });
  }

  function astScopeLimit() {
    return astStatus && Number.isFinite(astStatus.max_scope_reports)
      ? astStatus.max_scope_reports : 100;
  }

  function astReadableReports(scope) {
    var available = (typeof allReports !== "undefined" && allReports.length) ? allReports : reports;
    if (scope.selected.length) return scope.selected;
    var filters = scope.payload || {};
    return available.filter(function (report) {
      return (!filters.dag_id || String(report.dag_id).toLowerCase().indexOf(filters.dag_id.toLowerCase()) !== -1)
        && (!filters.task_id || String(report.task_id).toLowerCase().indexOf(filters.task_id.toLowerCase()) !== -1)
        && (!filters.run_id || String(report.run_id).toLowerCase().indexOf(filters.run_id.toLowerCase()) !== -1);
    });
  }

  function astByteLabel(value) {
    var bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return "?";
    if (bytes === 0) return "0 B";
    if (bytes >= 1024) {
      var kib = bytes / 1024;
      return (Math.round(kib * 100) / 100) + " KiB";
    }
    return bytes + " B";
  }

  function astLimitText(key, value) {
    return astFmt(astT(key), "value", value);
  }

  function astAppendCodeValue(root, text, key, value) {
    var marker = "{" + key + "}", index = String(text).indexOf(marker);
    if (index < 0) { root.textContent = text; return; }
    root.appendChild(document.createTextNode(String(text).slice(0, index)));
    var code = document.createElement("code"); code.textContent = String(value);
    root.appendChild(code);
    root.appendChild(document.createTextNode(String(text).slice(index + marker.length)));
  }

  function astProcessingModel(scope) {
    var visible = astReadableReports(scope).length;
    var selectedCap = scope.selected.length ? astScopeLimit() : visible;
    var contextBytes = astStatus && Number.isFinite(astStatus.max_context_bytes)
      ? astStatus.max_context_bytes : 49152;
    var failureBytes = astStatus && Number.isFinite(astStatus.max_failure_bytes)
      ? astStatus.max_failure_bytes : 3072;
    var captureBytes = astStatus && Number.isFinite(astStatus.max_capture_bytes)
      ? astStatus.max_capture_bytes : 2048;
    var outputTokens = astStatus && Number.isFinite(astStatus.max_output_tokens)
      ? astStatus.max_output_tokens : 3072;
    if (astStatus && astStatus.context_mode === "local-full-tree") {
      var processed = Math.min(visible, selectedCap);
      var localLimits = [
        astLimitText("localLimitReports", processed),
        astT("localLimitCases"),
        astLimitText("tracebackLimit", astByteLabel(failureBytes)),
        astLimitText("captureLimit", astByteLabel(captureBytes)),
        astLimitText("localOutboundLimit", astByteLabel(contextBytes))
      ];
      if (Number.isFinite(astStatus.local_budget_seconds)
          && astStatus.local_budget_seconds > 0) {
        localLimits.push(astLimitText("localBudgetLimit",
          Math.round(astStatus.local_budget_seconds)));
      }
      localLimits.push(astLimitText("outputTokenLimit", outputTokens));
      return {
        copy: astFmt(astT("localProcessing"), "processed", processed),
        visible: visible,
        limits: localLimits
      };
    }
    var summaryLimit = astStatus && Number.isFinite(astStatus.direct_max_summaries)
      ? astStatus.direct_max_summaries : 100;
    return {
      copy: astT("directProcessing"),
      visible: visible,
      limits: [
        astLimitText("directLimitSummaries", summaryLimit),
        astLimitText("contextLimit", astByteLabel(contextBytes)),
        astLimitText("tracebackLimit", astByteLabel(failureBytes)),
        astLimitText("captureLimit", astByteLabel(captureBytes)),
        astLimitText("outputTokenLimit", outputTokens)
      ]
    };
  }

  function astRenderProcessing(scope) {
    var root = document.getElementById("ast-processing");
    var model = astProcessingModel(scope); root.textContent = "";
    var disclosure = document.createElement("div");
    disclosure.className = "ast-limit-disclosure";
    disclosure.id = "ast-limit-disclosure"; disclosure.dataset.open = "false";
    var button = document.createElement("button"); button.type = "button";
    button.className = "ast-limit-button"; button.textContent = astT("limits");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", "ast-limit-tooltip");
    disclosure.appendChild(button);
    var tooltip = document.createElement("div"); tooltip.id = "ast-limit-tooltip";
    tooltip.className = "ast-limit-tooltip"; tooltip.setAttribute("role", "region");
    tooltip.setAttribute("aria-label", astT("limits"));
    var copy = document.createElement("p"); copy.className = "ast-processing-copy";
    astAppendCodeValue(copy, model.copy, "visible", model.visible); tooltip.appendChild(copy);
    var limits = document.createElement("ul"); limits.className = "ast-limits";
    model.limits.forEach(function (value) {
      var item = document.createElement("li"); item.className = "ast-limit";
      var code = document.createElement("code"); code.textContent = value;
      item.appendChild(code); limits.appendChild(item);
    });
    tooltip.appendChild(limits); disclosure.appendChild(tooltip); root.appendChild(disclosure);
    button.addEventListener("click", function () {
      var open = disclosure.dataset.open !== "true";
      disclosure.dataset.open = String(open);
      button.setAttribute("aria-expanded", String(open));
    });
  }

  function astCloseLimits(returnFocus) {
    var disclosure = document.getElementById("ast-limit-disclosure");
    if (!disclosure || disclosure.dataset.open !== "true") return false;
    disclosure.dataset.open = "false";
    var button = disclosure.querySelector(".ast-limit-button");
    if (button) {
      button.setAttribute("aria-expanded", "false");
      if (returnFocus) button.focus();
    }
    return true;
  }

  function astScope() {
    var allSelected = astSelectedReports(), limit = astScopeLimit();
    var selected = allSelected.slice(0, limit);
    var total = allSelected.length;
    if (selected.length) {
      var label = total > selected.length
        ? astFmt(astFmt(astT("selectedScopeLimited"), "used", selected.length), "total", total)
        : astFmt(astT("selectedScope"), "n", total);
      return { payload: { report_ids: selected.map(function (r) { return r.id; }) },
        label: label, selected: allSelected };
    }
    var scope = {}, labels = [];
    [["dag_id", "f-dag"], ["task_id", "f-task"], ["run_id", "f-run"]].forEach(function (pair) {
      var value = document.getElementById(pair[1]).value.trim();
      if (value) { scope[pair[0]] = value; labels.push(pair[0] + "~" + value); }
    });
    return { payload: scope, label: labels.length
      ? astFmt(astT("filtersScope"), "value", labels.join(" · ")) : astT("allScope"),
      selected: [] };
  }

  function astRenderScopeList(scope) {
    var runs = document.getElementById("ast-scope-runs"); runs.textContent = "";
    document.getElementById("ast-scope-dialog-summary").textContent =
      astFmt(astT("scopeListSummary"), "n", scope.selected.length);
    var limitAt = astScopeLimit();
    scope.selected.forEach(function (report, index) {
      if (index === limitAt) {
        var limit = document.createElement("li"); limit.className = "ast-scope-limit";
        limit.textContent = astFmt(astT("scopeListLimit"), "n", limitAt); runs.appendChild(limit);
      }
      var item = document.createElement("li"); item.className = "ast-scope-run";
      var number = document.createElement("span"); number.className = "ast-scope-run-num";
      number.textContent = String(index + 1);
      var main = document.createElement("div"); main.className = "ast-scope-run-main";
      var name = document.createElement("strong");
      name.textContent = report.dag_id + " · " + report.task_id;
      var run = document.createElement("code"); run.textContent = report.run_id;
      main.appendChild(name); main.appendChild(run); item.appendChild(number); item.appendChild(main);
      runs.appendChild(item);
    });
  }

  function astUpdateScope() {
    // Nothing can be asked, so the scope banner would only describe a question that
    // cannot be sent.
    if (astUnavailable) { astContext.hidden = true; return; }
    var scope = astScope();
    document.getElementById("ast-scope").textContent = scope.label;
    astRenderProcessing(scope);
    astScopeList.hidden = !scope.selected.length;
    // Always state the scope, including the unfiltered default. Hiding the banner until a
    // filter exists left the most common case -- "everything you may read" -- as the only
    // one the user had to go looking for.
    astContext.hidden = false;
    if (astScopeDialog.open) astRenderScopeList(scope);
  }

  function astUseStorageNamespace(namespace) {
    var token = String(namespace || "standalone").slice(0, 64);
    AST_STORAGE_KEY = AST_STORAGE_PREFIX + token;
    AST_WINDOW_PREFS_KEY = AST_WINDOW_PREFIX + token;
    AST_WINDOW_OPEN_KEY = AST_WINDOW_PREFS_KEY + ":open";
    AST_CONTEXT_WRAP_KEY = AST_WINDOW_PREFS_KEY + ":context-wrap";
    try {
      var savedWrap = localStorage.getItem(AST_CONTEXT_WRAP_KEY);
      astContextWrapped = savedWrap == null ? true : savedWrap === "1";
    } catch (error) { astContextWrapped = true; }
    astApplyContextWrap();
    astTranscript = astLoadTranscript();
    if (AST_SERVER_HISTORY) astLoadServerHistory(astConversation, false);
    astRenderSessionTokens();
    var lastUsers = astTranscript.filter(function (item) { return item.role === "user"; });
    astLastQuestion = lastUsers.length ? lastUsers[lastUsers.length - 1].text : "";
    astClear.hidden = !astTranscript.length;
    if (astDialog.open) {
      if (astTranscript.length) astRenderTranscript(); else astEmpty();
    }
  }

  function astLoadServerHistory(conversation, replace) {
    // The server is the source of truth once it stores the transcript: it survives the tab
    // closing and follows the user to another browser, which sessionStorage cannot do.
    var url = API + "assistant/history";
    if (conversation) url += "?conversation=" + encodeURIComponent(conversation);
    return fetch(url).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(function (body) {
      if (!body || body.available !== true || !Array.isArray(body.messages)) return;
      if (astPending) return;
      astConversations = Array.isArray(body.conversations) ? body.conversations : [];
      astConversation = typeof body.conversation === "string" ? body.conversation : "";
      astChats.hidden = !AST_SERVER_HISTORY;
      if (astChatsDialog.open) astRenderChatList();
      var restored = body.messages.filter(function (item) {
        return item && (item.role === "user" || item.role === "assistant")
          && typeof item.content === "string" && item.content;
      }).slice(-AST_MAX_MESSAGES).map(function (item) {
        return {
          role: item.role,
          text: item.content.slice(0, 64 * 1024),
          evidence: Array.isArray(item.evidence) ? item.evidence : [],
          reports: null, promptParts: null, promptBytes: null, reportContext: null,
          tokenUsage: null, contextLimited: false, outputLimited: false,
          pending: false, stopped: false, truncated: false
        };
      });
      if (!restored.length && !replace) return;
      astTranscript = restored;
      astSessionTotalTokens = 0;
      astPersistTranscript(); astRenderSessionTokens();
      astClear.hidden = !astTranscript.length;
      if (astDialog.open) {
        if (astTranscript.length) astRenderTranscript(); else astEmpty();
      }
    }).catch(function () { /* Stored history is a convenience; the chat works without it. */ });
  }

  function astIcon(path) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    var shape = document.createElementNS("http://www.w3.org/2000/svg", "path");
    shape.setAttribute("d", path);
    svg.appendChild(shape);
    return svg;
  }

  function astChatWhen(value) {
    if (!value) return "";
    var when = new Date(value);
    if (isNaN(when.getTime())) return "";
    return when.toLocaleString();
  }

  function astChatsForDisplay() {
    // A chat that has never been answered exists only here: the list comes from the
    // server, and the server learns about it with the first stored exchange. Without
    // this, New chat emptied the panel and then showed a list you were not in.
    var listed = astConversations.slice();
    if (astConversation && !listed.some(function (chat) {
      return chat.id === astConversation;
    })) {
      listed.unshift({ id: astConversation, title: "", messages: 0, updated_at: null });
    }
    return listed;
  }

  function astRenderChatList() {
    astChatList.textContent = "";
    var chats = astChatsForDisplay();
    document.getElementById("ast-chats-dialog-summary").textContent =
      astFmt(astT("chatsSummary"), "n", astConversations.length);
    if (!chats.length) {
      var empty = document.createElement("li");
      empty.className = "ast-chat-meta";
      empty.textContent = astT("chatsEmpty");
      astChatList.appendChild(empty);
      return;
    }
    chats.forEach(function (chat) {
      var row = document.createElement("li"); row.className = "ast-chat-row";
      var open = document.createElement("button");
      open.type = "button"; open.className = "ast-chat-item";
      var current = chat.id === astConversation;
      if (current) open.setAttribute("aria-current", "true");
      var title = document.createElement("span"); title.className = "ast-chat-title";
      // textContent, never innerHTML: the title is a question a user typed.
      title.textContent = chat.title || astT("chatUntitled");
      var meta = document.createElement("span"); meta.className = "ast-chat-meta";
      meta.textContent = astFmt(astFmt(astT("chatMeta"), "n", chat.messages || 0),
        "when", astChatWhen(chat.updated_at));
      if (current) {
        var badge = document.createElement("span");
        badge.className = "ast-chat-current";
        badge.textContent = astT("chatOpen");
        meta.appendChild(badge);
      }
      open.appendChild(title); open.appendChild(meta);
      open.addEventListener("click", function () { astSwitchChat(chat.id); });
      var remove = document.createElement("button");
      remove.type = "button"; remove.className = "ast-chat-delete";
      remove.setAttribute("aria-label", astT("deleteChat"));
      remove.title = astT("deleteChat");
      remove.appendChild(astIcon(
        "M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6"));
      var rename = document.createElement("button");
      rename.type = "button"; rename.className = "ast-chat-rename";
      rename.setAttribute("aria-label", astT("renameChat"));
      rename.title = astT("renameChat");
      rename.appendChild(astIcon("M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"));
      rename.addEventListener("click", function (event) {
        event.stopPropagation(); astStartRename(row, chat);
      });
      // Deleting a chat that is not being written to stays available.
      remove.disabled = astPending && chat.id === astConversation;
      remove.addEventListener("click", function (event) {
        event.stopPropagation(); astAskToDelete(row, chat);
      });
      row.appendChild(open); row.appendChild(rename); row.appendChild(remove);
      astChatList.appendChild(row);
    });
  }

  function astStartRename(row, chat) {
    // In place of the row, like the delete confirmation: no second modal stacked on this
    // one, and the chat being renamed stays where the user was looking at it.
    row.textContent = "";
    row.classList.add("ast-chat-row-confirming");
    var field = document.createElement("input");
    field.type = "text"; field.className = "ast-chat-name-input";
    field.maxLength = 200;
    field.value = chat.title || "";
    field.placeholder = astT("renamePlaceholder");
    field.setAttribute("aria-label", astT("renameChat"));
    var save = document.createElement("button");
    save.type = "button"; save.className = "ast-chat-confirm";
    save.textContent = astT("renameSave");
    var cancel = document.createElement("button");
    cancel.type = "button"; cancel.className = "ast-chat-cancel";
    cancel.textContent = astT("deleteChatNo");
    function commit() { astRenameChat(chat.id, field.value); }
    save.addEventListener("click", commit);
    cancel.addEventListener("click", astRenderChatList);
    field.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { event.preventDefault(); commit(); }
      else if (event.key === "Escape") { event.preventDefault(); astRenderChatList(); }
    });
    row.appendChild(field); row.appendChild(cancel); row.appendChild(save);
    field.focus(); field.select();
  }

  function astRenameChat(id, title) {
    fetch(API + "assistant/history?conversation=" + encodeURIComponent(id), {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title })
    }).catch(function () { /* The refresh below reports the real state either way. */ })
      .then(function () { astLoadChatList(); });
  }

  function astAskToDelete(row, chat) {
    // Deleting a whole conversation cannot be undone, and the row's small x is easy to hit
    // by accident. The confirmation replaces the row in place: no second modal to stack on
    // top of this one, and the chat being deleted stays named on screen.
    row.textContent = "";
    row.classList.add("ast-chat-row-confirming");
    var label = document.createElement("span");
    label.className = "ast-chat-confirm-label";
    label.textContent = astFmt(astT("deleteChatConfirm"), "title",
      chat.title || astT("chatUntitled"));
    var yes = document.createElement("button");
    yes.type = "button"; yes.className = "ast-chat-confirm";
    yes.textContent = astT("deleteChatYes");
    yes.addEventListener("click", function () { astDeleteChat(chat.id); });
    var no = document.createElement("button");
    no.type = "button"; no.className = "ast-chat-cancel";
    no.textContent = astT("deleteChatNo");
    no.addEventListener("click", function () { astRenderChatList(); });
    row.appendChild(label); row.appendChild(no); row.appendChild(yes);
    yes.focus();
  }

  function astOpenChats() {
    astRenderChatList();
    if (typeof astChatsDialog.showModal === "function") {
      if (!astChatsDialog.open) astChatsDialog.showModal();
    } else astChatsDialog.setAttribute("open", "");
    astChats.setAttribute("aria-expanded", "true");
    if (typeof updateParentDim === "function") updateParentDim();
    // Refresh in the background: another tab may have added a chat since this one loaded.
    astLoadChatList();
  }

  function astCloseChats() {
    if (astChatsDialog.open && typeof astChatsDialog.close === "function") {
      astChatsDialog.close();
    } else astChatsDialog.removeAttribute("open");
    astChats.setAttribute("aria-expanded", "false");
  }

  function astLoadChatList() {
    fetch(API + "assistant/history" +
      (astConversation ? "?conversation=" + encodeURIComponent(astConversation) : ""))
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (body) {
        if (!body || body.available !== true) return;
        astConversations = Array.isArray(body.conversations) ? body.conversations : [];
        if (astChatsDialog.open) astRenderChatList();
      }).catch(function () { /* The list is a convenience. */ });
  }

  function astSwitchChat(id) {
    if (astPending) return;
    astCloseChats();
    if (id === astConversation) return;
    astConversation = id;
    astLoadServerHistory(id, true);
    astQuestion.focus();
  }

  function astNewChat() {
    if (astPending) return;
    astCloseChats();
    // A fresh id is minted here and only reaches the server with the first answer, so an
    // abandoned new chat leaves nothing behind.
    astConversation = astNewConversationId();
    astTranscript = []; astLastQuestion = ""; astSessionTotalTokens = 0;
    astPersistTranscript(); astRenderSessionTokens();
    astClear.hidden = true; astEmpty(); astQuestion.focus();
  }

  function astDeleteChat(id) {
    if (astPending && id === astConversation) return;
    fetch(API + "assistant/history?conversation=" + encodeURIComponent(id),
      { method: "DELETE" })
      .catch(function () { /* Reported by the refresh below either way. */ })
      .then(function () {
        astLoadChatList();
        if (id === astConversation) {
          astConversation = "";
          astTranscript = []; astLastQuestion = ""; astSessionTotalTokens = 0;
          astPersistTranscript(); astRenderSessionTokens();
          astClear.hidden = true; astEmpty();
          astLoadServerHistory("", true);
        }
      });
  }

  function astNewConversationId() {
    var random = "";
    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      var bytes = new Uint8Array(8);
      window.crypto.getRandomValues(bytes);
      for (var i = 0; i < bytes.length; i++) {
        random += ("0" + bytes[i].toString(16)).slice(-2);
      }
    } else random = String(Math.random()).slice(2, 18);
    return "c" + Date.now().toString(36) + random;
  }

  function astCleanPromptParts(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    var names = ["system", "user", "context", "history", "docs", "structure"], clean = {};
    for (var i = 0; i < names.length; i++) {
      var value = raw[names[i]];
      // A part this build knows about and the payload does not is zero, not a reason to
      // throw the whole breakdown away: a transcript stored before a part existed, or a
      // browser held open across a deploy, would otherwise show no breakdown at all.
      if (value === undefined || value === null) { clean[names[i]] = 0; continue; }
      if (!Number.isFinite(value) || value < 0) return null;
      clean[names[i]] = Math.min(Math.floor(value), 100 * 1024 * 1024);
    }
    clean.total = names.reduce(function (sum, name) { return sum + clean[name]; }, 0);
    return clean;
  }

  function astCleanReportContext(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)
        || typeof raw.content !== "string"
        || (raw.format !== "direct-snapshot-jsonl"
          && raw.format !== "locally-reduced-text")) return null;
    var content = raw.content.slice(0, 256 * 1024);
    var bytes;
    try { bytes = new TextEncoder().encode(content).length; }
    catch (error) { bytes = new Blob([content]).size; }
    return { content: content, format: raw.format, bytes: bytes };
  }

  function astCleanTokenUsage(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    var names = ["input_tokens", "output_tokens", "total_tokens", "cached_input_tokens"];
    var clean = {};
    for (var i = 0; i < names.length; i++) {
      var value = raw[names[i]];
      if (!Number.isFinite(value) || value < 0) return null;
      clean[names[i]] = Math.min(Math.floor(value), 1_000_000_000_000);
    }
    return clean;
  }

  function astTokenText(usage) {
    var locale = LOCALE === "ru" ? "ru-RU" : "en-US";
    var text = astFmt(astT("tokens"), "input", usage.input_tokens.toLocaleString(locale));
    text = astFmt(text, "output", usage.output_tokens.toLocaleString(locale));
    return astFmt(text, "total", usage.total_tokens.toLocaleString(locale));
  }

  function astBoundSessionTokens(value) {
    if (!Number.isFinite(value) || value < 0) return 0;
    return Math.min(Math.floor(value), AST_MAX_SESSION_TOKENS);
  }

  function astRenderSessionTokens() {
    astSessionTokens.textContent = "";
    if (astSessionTotalTokens <= 0) { astSessionTokens.hidden = true; return; }
    var locale = LOCALE === "ru" ? "ru-RU" : "en-US";
    var total = astSessionTotalTokens.toLocaleString(locale);
    // Built as nodes so the number can carry its own weight without innerHTML.
    var text = astFmt(astT("sessionTokens"), "total", "\u0000").split("\u0000");
    astSessionTokens.appendChild(document.createTextNode(text[0]));
    var value = document.createElement("b"); value.textContent = total;
    astSessionTokens.appendChild(value);
    if (text.length > 1) astSessionTokens.appendChild(document.createTextNode(text[1]));
    astSessionTokens.title = astSessionTokens.textContent;
    astSessionTokens.hidden = false;
  }

  function astAddSessionTokens(usage) {
    if (!usage) return;
    astSessionTotalTokens = astBoundSessionTokens(
      astSessionTotalTokens + usage.total_tokens
    );
    astRenderSessionTokens();
  }

  function astLoadTranscript() {
    astSessionTotalTokens = 0;
    if (!AST_STORAGE_KEY) return [];
    try {
      var saved = JSON.parse(sessionStorage.getItem(AST_STORAGE_KEY) || "null");
      if (!saved || saved.version !== 1 || !Array.isArray(saved.messages)) return [];
      // Reopen the chat this tab was reading. Without it a refresh silently jumps to
      // whichever chat the server calls newest, which may be one written in another tab.
      astConversation = typeof saved.conversation === "string"
        ? saved.conversation.slice(0, 64) : "";
      var messages = saved.messages.filter(function (item) {
        return item && (item.role === "user" || item.role === "assistant")
          && typeof item.text === "string";
      }).slice(-AST_MAX_MESSAGES).map(function (item) {
        var evidence = Array.isArray(item.evidence) ? item.evidence.filter(function (ref) {
          return ref && typeof ref.key === "string" && typeof ref.report_id === "string"
            && typeof ref.dag_id === "string" && typeof ref.task_id === "string"
            && typeof ref.run_id === "string";
        }).slice(0, astScopeLimit()).map(function (ref) {
          return { key: ref.key.slice(0, 8), report_id: ref.report_id.slice(0, 4096),
            dag_id: ref.dag_id.slice(0, 512), task_id: ref.task_id.slice(0, 512),
            run_id: ref.run_id.slice(0, 512) };
        }) : [];
        var promptParts = astCleanPromptParts(item.promptParts);
        var reportContext = astCleanReportContext(item.reportContext);
        if (promptParts && reportContext && promptParts.context !== reportContext.bytes) {
          reportContext = null;
        }
        return {
          role: item.role,
          text: item.text.slice(0, 64 * 1024),
          evidence: evidence,
          reports: Number.isFinite(item.reports) ? item.reports : null,
          promptParts: promptParts,
          reportContext: reportContext,
          tokenUsage: astCleanTokenUsage(item.tokenUsage),
          promptBytes: Number.isFinite(item.promptBytes) && item.promptBytes >= 0
            ? Math.min(Math.floor(item.promptBytes), 100 * 1024 * 1024) : null,
          contextLimited: item.contextLimited === true,
          outputLimited: item.outputLimited === true,
          // A reload kills the connection, so a restored answer can never still be
          // streaming: it is exactly as finished as the text that reached storage.
          pending: false,
          stopped: item.pending === true || item.stopped === true,
          stoppedNote: typeof item.stoppedNote === "string"
            ? item.stoppedNote.slice(0, 400) : null,
          truncated: item.truncated === true
        };
      }).filter(function (item) {
        return item.text || item.role === "user";
      });
      var visibleTotal = messages.reduce(function (total, item) {
        return total + (item.tokenUsage ? item.tokenUsage.total_tokens : 0);
      }, 0);
      var storedTotal = astBoundSessionTokens(saved.sessionTotalTokens);
      astSessionTotalTokens = Math.max(storedTotal, astBoundSessionTokens(visibleTotal));
      return messages;
    } catch (error) { astSessionTotalTokens = 0; return []; }
  }

  function astPersistTranscript() {
    astTranscript = astTranscript.slice(-AST_MAX_MESSAGES);
    try { if (AST_STORAGE_KEY) {
      sessionStorage.setItem(AST_STORAGE_KEY,
        JSON.stringify({ version: 1, messages: astTranscript,
          conversation: astConversation,
          sessionTotalTokens: astSessionTotalTokens }));
    } } catch (error) { /* Storage may be blocked or full; chat still works in memory. */ }
    astClear.hidden = !astTranscript.length;
  }

  function astHistoryPayload() {
    // A stored answer may be far longer than one prompt turn, and the server clips each
    // turn to the same limit anyway. Sending the whole transcript verbatim would only
    // push the request towards the 64 KiB body cap.
    return astTranscript.filter(function (item) {
      return (item.role === "user" || item.role === "assistant") && item.text;
    }).slice(-AST_MAX_MESSAGES).map(function (item) {
      return { role: item.role, content: item.text.slice(0, AST_MAX_HISTORY_CHARS) };
    });
  }

  function astMessageMeta(item) {
    // An empty scope never reaches a model, so the API reports a zero-byte prompt. Six
    // rows of "0 B" read as a broken request; say what actually happened instead.
    if (item.role === "user" && item.promptParts && !item.promptParts.total) {
      return astT("promptNothingSent");
    }
    if (item.role === "user" && Number.isFinite(item.promptBytes)
        && item.promptBytes === 0 && !item.promptParts) {
      return astT("promptNothingSent");
    }
    if (item.role === "user" && item.promptParts) {
      return { title: astT("promptSize"), items: [
        { label: astT("promptSystem"), value: astByteLabel(item.promptParts.system) },
        { label: astT("promptUser"), value: astByteLabel(item.promptParts.user) },
        { label: astT("promptContext"), value: astByteLabel(item.promptParts.context) },
        { label: astT("promptDocs"), value: astByteLabel(item.promptParts.docs) },
        { label: astT("promptHistory"), value: astByteLabel(item.promptParts.history) },
        { label: astT("promptStructure"), value: astByteLabel(item.promptParts.structure) },
        { label: astT("promptTotal"), value: astByteLabel(item.promptParts.total), total: true }
      ], reportContext: item.reportContext };
    }
    if (item.role === "user" && Number.isFinite(item.promptBytes)) {
      return { title: astT("promptSize"), items: [
        { label: astT("promptTotal"), value: astByteLabel(item.promptBytes), total: true }
      ], reportContext: item.reportContext };
    }
    if (item.role !== "assistant" || item.reports == null) return "";
    var meta = astFmt(astT("reports"), "n", item.reports);
    if (item.contextLimited) meta += " · " + astT("truncated");
    if (item.tokenUsage) meta += " · " + astTokenText(item.tokenUsage);
    return meta;
  }

  function astReportContextFormat(context) {
    return astT(context.format === "locally-reduced-text"
      ? "contextLocalFormat" : "contextDirectFormat");
  }

  function astApplyContextWrap() {
    document.getElementById("ast-report-context-content").classList.toggle(
      "ast-wrap", astContextWrapped
    );
    astReportContextWrap.setAttribute("aria-pressed", String(astContextWrapped));
  }

  function astRenderReportContext(context) {
    document.getElementById("ast-report-context-summary").textContent = astByteLabel(context.bytes);
    document.getElementById("ast-report-context-format").textContent =
      astReportContextFormat(context);
    document.getElementById("ast-report-context-code").textContent = context.content;
  }

  function astContextTrigger(index) {
    if (index == null) return null;
    var box = astMessages.querySelector('[data-ast-index="' + index + '"]');
    return box ? box.querySelector(".ast-context-review") : null;
  }

  function astOpenReportContext(context, trigger) {
    if (!context) return;
    astActiveReportContext = context; astReportContextTrigger = trigger;
    var owner = trigger && trigger.closest ? trigger.closest("[data-ast-index]") : null;
    astReportContextIndex = owner ? owner.getAttribute("data-ast-index") : null;
    astRenderReportContext(context);
    if (typeof astReportContextDialog.showModal === "function") {
      if (!astReportContextDialog.open) astReportContextDialog.showModal();
    } else astReportContextDialog.setAttribute("open", "");
    if (typeof updateParentDim === "function") updateParentDim();
    document.getElementById("ast-report-context-close").focus();
  }

  function astCloseReportContext() {
    if (astReportContextDialog.open && typeof astReportContextDialog.close === "function") {
      astReportContextDialog.close();
    } else astReportContextDialog.removeAttribute("open");
  }

  function astRenderTranscript() {
    astMessages.textContent = "";
    astTranscript.forEach(function (item, index) {
      var box = astAddMessage(item.role, item.text, item.evidence || [], astMessageMeta(item),
        false, item.outputLimited === true, astMessageState(item), item.stoppedNote);
      // A stable position, so anything holding on to a bubble (focus return, in particular)
      // can find the replacement after a re-render instead of pointing at a detached node.
      box.setAttribute("data-ast-index", String(index));
    });
    astClear.hidden = !astTranscript.length;
  }

  function astMessageState(item) {
    if (item.role !== "assistant") return "";
    if (item.pending) return "pending";
    return item.stopped ? "stopped" : "";
  }

  function astStreamingBox() {
    return astMessages.querySelector('.ast-msg.assistant[data-ast-state="pending"]');
  }

  function astUpdateStreamingAnswer(item) {
    // Patch the live bubble in place so a delta never rebuilds the whole transcript. Any
    // full re-render in between recreates the same node from the same transcript item.
    var box = astStreamingBox();
    var body = box ? box.querySelector(".ast-answer") : null;
    if (!body) {
      // The very first delta upgrades the three-dot bubble into a text bubble; after that
      // the answer element exists and every later delta is a cheap in-place patch.
      astRenderTranscript();
      box = astStreamingBox();
      body = box ? box.querySelector(".ast-answer") : null;
      if (!body) return;
    }
    body.textContent = "";
    astRenderMarkdown(body, item.text);
    var atBottom = astMessages.scrollHeight - astMessages.scrollTop
      - astMessages.clientHeight < 80;
    if (atBottom) astMessages.scrollTop = astMessages.scrollHeight;
  }

  function astAskToClear() {
    // Clear throws away the transcript *and* its stored copy, and it sits in the header
    // next to Close. Asking first is the difference between a mistake and a loss.
    if (astPending) return;
    document.getElementById("ast-clear-confirm-text").textContent =
      AST_SERVER_HISTORY ? astT("clearConfirm") : astT("clearConfirmLocal");
    document.getElementById("ast-clear-keep").textContent = astT("clearConfirmNo");
    document.getElementById("ast-clear-yes").textContent = astT("clearConfirmYes");
    astClearConfirm.hidden = false;
    document.getElementById("ast-clear-keep").focus();
  }

  function astHideClearConfirm() {
    astClearConfirm.hidden = true;
  }

  function astClearTranscript() {
    astHideClearConfirm();
    if (astPending) return;
    if (AST_SERVER_HISTORY) {
      // Scoped to the chat on screen: with a list of chats, a button that silently wiped
      // all of them would be a trap. The list has a delete of its own per chat.
      var url = API + "assistant/history";
      if (astConversation) url += "?conversation=" + encodeURIComponent(astConversation);
      fetch(url, { method: "DELETE" })
        .catch(function () { /* Local clear still happens below. */ })
        .then(function () { astLoadChatList(); });
    }
    astTranscript = []; astLastQuestion = ""; astSessionTotalTokens = 0;
    try { if (AST_STORAGE_KEY) sessionStorage.removeItem(AST_STORAGE_KEY); } catch (error) {}
    astRenderSessionTokens(); astClear.hidden = true; astEmpty();
    astRenderGhost(); astQuestion.focus();
  }

  function astEmpty() {
    astMessages.textContent = "";
    var empty = document.createElement("div"); empty.className = "ast-empty";
    var title = document.createElement("strong"); title.textContent = astT("introTitle");
    var copy = document.createElement("span"); copy.textContent = astT("intro");
    var starters = document.createElement("div"); starters.className = "ast-starters";
    astT("starters").forEach(function (question) {
      var button = document.createElement("button"); button.type = "button";
      button.className = "ast-starter"; button.textContent = question;
      button.addEventListener("click", function () { astQuestion.value = question; astQuestion.focus(); });
      starters.appendChild(button);
    });
    empty.appendChild(title); empty.appendChild(copy); empty.appendChild(starters);
    astMessages.appendChild(empty);
  }

  function astAppendInline(root, raw) {
    var text = String(raw || "");
    var tokens = /(`[^`\n]+`|´[^´\n]+´|｀[^｀\n]+｀|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g;
    var last = 0, match;
    while ((match = tokens.exec(text)) !== null) {
      var rawToken = match[0];
      if (rawToken.charAt(0) === "_" &&
          (/[A-Za-z0-9]/.test(text.charAt(match.index - 1)) ||
           /[A-Za-z0-9]/.test(text.charAt(match.index + rawToken.length)))) {
        root.appendChild(document.createTextNode(text.slice(last, match.index + 1)));
        last = match.index + 1; tokens.lastIndex = last; continue;
      }
      if (match.index > last) root.appendChild(document.createTextNode(text.slice(last, match.index)));
      var token = match[0], node;
      if (token.charAt(0) === "`" || token.charAt(0) === "´" || token.charAt(0) === "｀") {
        node = document.createElement("code"); node.textContent = token.slice(1, -1);
      } else if (token.slice(0, 2) === "**" || token.slice(0, 2) === "__") {
        node = document.createElement("strong"); astAppendInline(node, token.slice(2, -2));
      } else if (token.charAt(0) === "*" || token.charAt(0) === "_") {
        node = document.createElement("em"); astAppendInline(node, token.slice(1, -1));
      } else {
        var link = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(token);
        node = document.createElement("a"); node.textContent = link ? link[1] : token;
        if (link) { node.href = link[2]; node.target = "_blank"; node.rel = "noopener noreferrer"; }
      }
      root.appendChild(node); last = match.index + token.length;
    }
    if (last < text.length) root.appendChild(document.createTextNode(text.slice(last)));
  }

  function astTableCells(raw) {
    var line = String(raw || "").trim();
    if (line.charAt(0) === "|") line = line.slice(1);
    if (line.charAt(line.length - 1) === "|" && !/\\\|$/.test(line)) line = line.slice(0, -1);
    var cells = [], cell = "", code = false;
    for (var i = 0; i < line.length; i++) {
      var char = line.charAt(i);
      if (char === "\\" && line.charAt(i + 1) === "|") { cell += "|"; i++; continue; }
      if (char === "`") { code = !code; cell += char; continue; }
      if (char === "|" && !code) { cells.push(cell.trim()); cell = ""; continue; }
      cell += char;
    }
    cells.push(cell.trim()); return cells;
  }

  function astTableDivider(raw, columns) {
    var cells = astTableCells(raw);
    return cells.length === columns && cells.every(function (cell) {
      return /^:?-{3,}:?$/.test(cell.replace(/\s/g, ""));
    });
  }

  function astAppendTable(root, headers, rows) {
    var wrap = document.createElement("div"); wrap.className = "ast-table-wrap";
    wrap.tabIndex = 0; wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", astT("tableLabel"));
    var table = document.createElement("table"), head = document.createElement("thead");
    var headRow = document.createElement("tr");
    headers.forEach(function (text) {
      var cell = document.createElement("th"); cell.scope = "col"; astAppendInline(cell, text);
      headRow.appendChild(cell);
    });
    head.appendChild(headRow); table.appendChild(head);
    var body = document.createElement("tbody");
    rows.forEach(function (values) {
      var row = document.createElement("tr");
      values.forEach(function (text) {
        var cell = document.createElement("td"); astAppendInline(cell, text); row.appendChild(cell);
      });
      body.appendChild(row);
    });
    table.appendChild(body); wrap.appendChild(table); root.appendChild(wrap);
  }

  function astRenderMarkdown(root, raw) {
    root.textContent = "";
    var lines = String(raw || "").replace(/\r\n?/g, "\n").split("\n");
    var paragraph = [], list = null, listKind = "";
    function flushParagraph() {
      if (!paragraph.length) return;
      var p = document.createElement("p"); astAppendInline(p, paragraph.join(" ").trim());
      root.appendChild(p); paragraph = [];
    }
    function closeList() { list = null; listKind = ""; }
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i], heading = /^(#{1,6})\s+(.+)$/.exec(line);
      var ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
      var bullet = /^\s*[-+*]\s+(.+)$/.exec(line);
      var headers = astTableCells(line);
      if (headers.length >= 2 && i + 1 < lines.length
          && astTableDivider(lines[i + 1], headers.length)) {
        flushParagraph(); closeList(); var rows = []; i += 2;
        while (i < lines.length && lines[i].trim()) {
          var values = astTableCells(lines[i]);
          if (values.length !== headers.length) break;
          rows.push(values); i++;
        }
        astAppendTable(root, headers, rows); i--; continue;
      }
      if (/^\s*```/.test(line)) {
        flushParagraph(); closeList(); var codeLines = [];
        while (++i < lines.length && !/^\s*```/.test(lines[i])) codeLines.push(lines[i]);
        var pre = document.createElement("pre"), code = document.createElement("code");
        code.textContent = codeLines.join("\n"); pre.appendChild(code); root.appendChild(pre); continue;
      }
      if (!line.trim()) { flushParagraph(); closeList(); continue; }
      if (heading) {
        flushParagraph(); closeList(); var title = document.createElement("h3");
        astAppendInline(title, heading[2]); root.appendChild(title); continue;
      }
      if (ordered || bullet) {
        flushParagraph(); var kind = ordered ? "ol" : "ul";
        if (!list || listKind !== kind) {
          list = document.createElement(kind); listKind = kind; root.appendChild(list);
        }
        var item = document.createElement("li"); astAppendInline(item, (ordered || bullet)[1]);
        list.appendChild(item); continue;
      }
      if (/^\s*>\s?/.test(line)) {
        flushParagraph(); closeList(); var quote = document.createElement("blockquote");
        astAppendInline(quote, line.replace(/^\s*>\s?/, "")); root.appendChild(quote); continue;
      }
      closeList(); paragraph.push(line.trim());
    }
    flushParagraph();
  }

  function astContextIcon() {
    var icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 24 24"); icon.setAttribute("fill", "none");
    icon.setAttribute("stroke", "currentColor"); icon.setAttribute("stroke-width", "2");
    icon.setAttribute("stroke-linecap", "round");
    icon.setAttribute("stroke-linejoin", "round");
    icon.setAttribute("aria-hidden", "true");
    var page = document.createElementNS("http://www.w3.org/2000/svg", "path");
    page.setAttribute("d", "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z");
    var fold = document.createElementNS("http://www.w3.org/2000/svg", "path");
    fold.setAttribute("d", "M14 2v6h6");
    icon.appendChild(page); icon.appendChild(fold);
    ["M9 13h6", "M9 17h4"].forEach(function (d) {
      var line = document.createElementNS("http://www.w3.org/2000/svg", "path");
      line.setAttribute("d", d); icon.appendChild(line);
    });
    return icon;
  }

  function astAppendMessageMeta(box, meta) {
    if (!meta) return;
    if (typeof meta !== "string" && box.classList && box.classList.contains("ast-msg")) {
      box.classList.add("ast-has-meta");
    }
    var note = document.createElement("div"); note.className = "ast-msg-meta";
    if (typeof meta === "string") note.textContent = meta;
    else {
      var title = document.createElement("strong"); title.className = "ast-prompt-title";
      title.textContent = meta.title; note.appendChild(title);
      var parts = document.createElement("dl"); parts.className = "ast-prompt-parts";
      meta.items.forEach(function (item) {
        var row = document.createElement("div"); row.className = "ast-prompt-row";
        if (item.total) row.classList.add("ast-prompt-total");
        var label = document.createElement("dt"); label.textContent = item.label;
        var value = document.createElement("dd"), code = document.createElement("code");
        code.textContent = item.value; value.appendChild(code);
        row.appendChild(label); row.appendChild(value); parts.appendChild(row);
      });
      note.appendChild(parts);
      if (meta.reportContext) {
        var review = document.createElement("button"); review.type = "button";
        review.className = "ast-context-review";
        review.appendChild(astContextIcon());
        var reviewLabel = document.createElement("span");
        reviewLabel.textContent = astT("contextReview");
        review.appendChild(reviewLabel);
        review.setAttribute("aria-haspopup", "dialog");
        review.setAttribute("aria-controls", "ast-report-context-dialog");
        review.addEventListener("click", function () {
          astOpenReportContext(meta.reportContext, review);
        });
        note.appendChild(review);
      }
    }
    box.appendChild(note);
  }

  function astLegacyCopy(text) {
    var input = document.createElement("textarea"); input.value = text;
    input.setAttribute("readonly", ""); input.style.position = "fixed";
    input.style.left = "-9999px"; document.body.appendChild(input);
    input.select(); input.setSelectionRange(0, input.value.length);
    var copied = false;
    try { copied = document.execCommand("copy"); } catch (error) { copied = false; }
    input.remove(); return copied;
  }

  function astCopyText(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function"
        && window.isSecureContext) {
      try {
        return navigator.clipboard.writeText(text).catch(function () {
          if (astLegacyCopy(text)) return;
          throw new Error("clipboard unavailable");
        });
      } catch (error) { /* Fall through to the compatibility path. */ }
    }
    return astLegacyCopy(text) ? Promise.resolve() : Promise.reject(new Error("clipboard unavailable"));
  }

  function astCopyButton(text) {
    var button = document.createElement("button"); button.type = "button";
    button.className = "ast-copy"; button.setAttribute("aria-live", "polite");
    var icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 24 24"); icon.setAttribute("fill", "none");
    icon.setAttribute("stroke", "currentColor"); icon.setAttribute("stroke-width", "2");
    icon.setAttribute("stroke-linecap", "round"); icon.setAttribute("stroke-linejoin", "round");
    icon.setAttribute("aria-hidden", "true");
    var front = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    front.setAttribute("width", "14"); front.setAttribute("height", "14");
    front.setAttribute("x", "8"); front.setAttribute("y", "8"); front.setAttribute("rx", "2");
    var back = document.createElementNS("http://www.w3.org/2000/svg", "path");
    back.setAttribute("d", "M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2");
    icon.appendChild(front); icon.appendChild(back);
    var label = document.createElement("span"); label.textContent = astT("copyAnswer");
    button.appendChild(icon); button.appendChild(label);
    button.addEventListener("click", function () {
      button.disabled = true;
      astCopyText(text).then(function () { label.textContent = astT("copied"); })
        .catch(function () { label.textContent = astT("copyFailed"); })
        .then(function () {
          setTimeout(function () {
            if (!button.isConnected) return;
            label.textContent = astT("copyAnswer"); button.disabled = false;
          }, 1500);
        });
    });
    return button;
  }

  function astCommandMatch() {
    // Only a slash that opens the whole question: "/bug", not "why did /tmp/x fail".
    var value = astQuestion.value;
    var match = /^\/([A-Za-z]*)$/.exec(value);
    return match ? match[1].toLowerCase() : null;
  }

  function astRenderCommands() {
    var typed = astCommandMatch();
    var offered = typed === null ? [] : AST_COMMANDS.filter(function (command) {
      return command.name.indexOf(typed) === 0;
    });
    astCommandList = offered;
    astCommandIndex = 0;
    astCommands.textContent = "";
    if (!offered.length) { astCommands.hidden = true; return; }
    offered.forEach(function (command, index) {
      var row = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button"; button.className = "ast-command";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      var name = document.createElement("b");
      name.textContent = "/" + command.name;
      var what = document.createElement("span");
      // Described in the reader's language; the server owns the names, not the wording.
      what.textContent = astT("command_" + command.name) || command.title;
      button.appendChild(name); button.appendChild(what);
      button.addEventListener("mousedown", function (event) {
        // mousedown, not click: the field must not lose focus first.
        event.preventDefault(); astUseCommand(index);
      });
      row.appendChild(button); astCommands.appendChild(row);
    });
    astCommands.hidden = false;
  }

  function astHighlightCommand(step) {
    if (!astCommandList.length) return;
    astCommandIndex =
      (astCommandIndex + step + astCommandList.length) % astCommandList.length;
    var buttons = astCommands.querySelectorAll(".ast-command");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute("aria-selected", i === astCommandIndex ? "true" : "false");
      if (i === astCommandIndex && buttons[i].scrollIntoView) {
        buttons[i].scrollIntoView({ block: "nearest" });
      }
    }
  }

  function astUseCommand(index) {
    var command = astCommandList[index];
    if (!command) return;
    astQuestion.value = "/" + command.name + " ";
    astCloseCommands();
    astRenderGhost();
    astQuestion.focus();
  }

  function astCloseCommands() {
    astCommandList = [];
    astCommands.hidden = true;
    astCommands.textContent = "";
  }

  function astProgressText(progress) {
    if (!progress) return "";
    if (progress.phase === "loading_model") return astT("progressLoadingModel");
    var elapsed = Math.round(Number(progress.elapsed_seconds) || 0);
    if (progress.phase === "local_merge") {
      return astFmt(astFmt(astT("progressMerge"), "pass", progress["pass"] || 1),
        "elapsed", elapsed);
    }
    var done = Number(progress.chunks_done) || 0;
    var budget = Number(progress.budget_seconds);
    if (!Number.isFinite(budget) || budget <= 0) {
      return astFmt(astFmt(astT("progressReduceNoBudget"), "done", done),
        "elapsed", elapsed);
    }
    return astFmt(astFmt(astFmt(astT("progressReduce"), "done", done),
      "elapsed", elapsed), "budget", Math.round(budget));
  }

  function astProgressFraction(progress) {
    // Chunk count has no known total, but the wall-clock budget does: it is the only
    // honest denominator available, and it is also what actually ends the wait.
    if (!progress || progress.phase === "loading_model") return 0;
    var elapsed = Number(progress.elapsed_seconds), budget = Number(progress.budget_seconds);
    if (!Number.isFinite(elapsed) || !Number.isFinite(budget) || budget <= 0) return 0;
    return Math.max(0, Math.min(1, elapsed / budget));
  }

  function astBuildProgress() {
    if (!astProgress) return null;
    var wrap = document.createElement("span");
    wrap.className = "ast-progress";
    wrap.textContent = astProgressText(astProgress);
    var fraction = astProgressFraction(astProgress);
    if (fraction > 0) {
      var bar = document.createElement("span");
      bar.className = "ast-progress-bar";
      bar.setAttribute("aria-hidden", "true");
      var fill = document.createElement("i");
      fill.style.width = Math.round(fraction * 100) + "%";
      bar.appendChild(fill); wrap.appendChild(bar);
    }
    return wrap;
  }

  function astRenderProgress() {
    var box = astMessages.querySelector(".ast-msg.ast-waiting");
    if (!box) return;
    var existing = box.querySelector(".ast-progress");
    if (existing) existing.remove();
    var built = astBuildProgress();
    if (built) box.appendChild(built);
  }

  function astAddMessage(role, text, evidence, meta, isError, outputLimited, state,
                         stoppedNote) {
    var empty = astMessages.querySelector(".ast-empty"); if (empty) empty.remove();
    var box = document.createElement("div"); box.className = "ast-msg " + role;
    if (state) box.setAttribute("data-ast-state", state);
    if (state === "pending" && !text) {
      // Nothing has arrived yet: the same compact three-dot bubble as before.
      box.className = "ast-msg assistant ast-waiting";
      box.setAttribute("role", "status"); box.setAttribute("aria-label", astT("thinking"));
      var dots = document.createElement("span"); dots.className = "ast-thinking";
      for (var d = 0; d < 3; d++) dots.appendChild(document.createElement("i"));
      box.appendChild(dots);
      var progressLine = astBuildProgress();
      if (progressLine) box.appendChild(progressLine);
      astMessages.appendChild(box); astMessages.scrollTop = astMessages.scrollHeight;
      return box;
    }
    var body = document.createElement("div"); body.className = "ast-answer" + (isError ? " ast-error" : "");
    if (role === "assistant" && !isError) astRenderMarkdown(body, text);
    else body.textContent = text;
    box.appendChild(body);
    if (state === "pending") {
      var caret = document.createElement("span"); caret.className = "ast-caret";
      caret.setAttribute("aria-hidden", "true"); box.appendChild(caret);
      box.setAttribute("aria-busy", "true");
    }
    if (state === "stopped") {
      var stopped = document.createElement("div"); stopped.className = "ast-stopped-note";
      stopped.setAttribute("role", "status");
      stopped.textContent = stoppedNote || astT("stoppedNote");
      box.appendChild(stopped);
    }
    if (role === "assistant" && outputLimited) {
      var warning = document.createElement("div"); warning.className = "ast-output-warning";
      warning.setAttribute("role", "status"); warning.textContent = astT("outputLimited");
      box.appendChild(warning);
    }
    if (evidence && evidence.length) {
      var sources = document.createElement("div"); sources.className = "ast-sources";
      evidence.forEach(function (item) {
        var button = document.createElement("button"); button.type = "button"; button.className = "ast-source";
        button.textContent = "[" + item.key + "] " + item.dag_id + " · " + item.task_id + " · " + item.run_id;
        button.addEventListener("click", function () { openDetail(item.report_id); });
        sources.appendChild(button);
      });
      box.appendChild(sources);
    }
    if (role === "assistant" && !isError && state !== "pending") {
      // A half-written answer has nothing worth copying yet, so the footer waits.
      var footer = document.createElement("div"); footer.className = "ast-msg-footer";
      astAppendMessageMeta(footer, meta); footer.appendChild(astCopyButton(text));
      box.appendChild(footer);
    } else if (state !== "pending") astAppendMessageMeta(box, meta);
    if (isError) {
      var retry = document.createElement("button"); retry.type = "button"; retry.className = "btn ast-retry";
      retry.textContent = astT("retry"); retry.addEventListener("click", function () { astSendQuestion(astLastQuestion); });
      box.appendChild(retry);
    }
    astMessages.appendChild(box); astMessages.scrollTop = astMessages.scrollHeight;
    return box;
  }

  function astSetPending(on) {
    astPending = on; astSend.disabled = on; astQuestion.disabled = on;
    // Stop replaces Send while an answer is streaming: the request is abortable, and
    // leaving a disabled Send as the only control gave the user nothing to do but wait.
    astSend.hidden = on; astStop.hidden = !on;
    astMessages.setAttribute("aria-busy", String(on));
    if (on) astStop.disabled = false;
    // The chat an answer is being written into must not be erased underneath it: the
    // reply would land in a transcript that no longer exists, and the server would keep
    // an exchange the user believes they deleted. Switching and New already refuse while
    // pending; these two are the same rule made visible.
    astClear.disabled = on;
    if (on) astHideClearConfirm();
    if (astChatsDialog.open) astRenderChatList();
  }

  function astErrorDetail(body, status) {
    // FastAPI answers a schema violation with a list of error objects, not a string.
    // Stringifying that list produced "[object Object]" in the bubble.
    var detail = body && body.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length) {
      var first = detail[0];
      if (first && typeof first.msg === "string" && first.msg) {
        return astFmt(astT("invalidRequest"), "reason", first.msg);
      }
    }
    return "HTTP " + status;
  }

  function astApplyMeta(userItem, body) {
    userItem.promptParts = astCleanPromptParts(body.prompt_bytes);
    userItem.reportContext = astCleanReportContext(body.report_context);
    if (userItem.promptParts && userItem.reportContext
        && userItem.promptParts.context !== userItem.reportContext.bytes) {
      userItem.reportContext = null;
    }
    if (userItem.promptParts) userItem.promptBytes = userItem.promptParts.total;
    else if (Number.isFinite(body.provider_input_bytes) && body.provider_input_bytes >= 0) {
      userItem.promptBytes = Math.floor(body.provider_input_bytes);
    }
  }

  function astApplyDone(item, body) {
    // Whatever the model wrote, including when no report matched: the dashboard language
    // is sent with the question now, so the answer already comes back in the right one.
    // Substituting a fixed sentence here used to overwrite real answers -- a question
    // about the product needs no reports at all.
    item.text = body.answer || item.text || "";
    item.pending = false;
    item.stopped = false;
    item.evidence = body.evidence || [];
    item.reports = body.reports_considered || 0;
    item.tokenUsage = astCleanTokenUsage(body.token_usage);
    item.contextLimited = body.context_limited === true
      || (body.context_limited == null && body.truncated === true);
    item.outputLimited = body.output_limited === true;
    item.truncated = body.truncated === true;
  }

  function astParseEvents(buffer, onEvent) {
    // SSE frames are separated by a blank line; JSON payloads never contain a raw newline,
    // so one `data:` line always holds a whole event.
    var blocks = buffer.split("\n\n");
    var rest = blocks.pop();
    blocks.forEach(function (block) {
      var name = "", data = "";
      block.split("\n").forEach(function (line) {
        if (line.indexOf("event: ") === 0) name = line.slice(7);
        else if (line.indexOf("data: ") === 0) data = line.slice(6);
      });
      if (!name || !data) return;
      var payload;
      try { payload = JSON.parse(data); } catch (error) { return; /* Partial frame. */ }
      onEvent(name, payload);
    });
    return rest;
  }

  function astStopStream() {
    if (astController) { try { astController.abort(); } catch (error) {} }
  }

  function astSendQuestion(raw) {
    var question = String(raw || "").trim(); if (!question || astPending) return;
    var history = astHistoryPayload();
    astLastQuestion = question;
    var userItem = { role: "user", text: question, evidence: [], reports: null,
      promptParts: null, promptBytes: null, reportContext: null, truncated: false };
    // The pending answer lives in the transcript, not only in the DOM: closing and
    // reopening the window re-renders from the transcript, and an answer that existed only
    // as a detached node used to vanish mid-flight.
    var pendingItem = { role: "assistant", text: "", evidence: [], reports: null,
      tokenUsage: null, contextLimited: false, outputLimited: false, truncated: false,
      pending: true, stopped: false };
    astTranscript.push(userItem); astTranscript.push(pendingItem);
    astPersistTranscript(); astRenderTranscript(); astQuestion.value = "";
    astCloseCommands(); astRenderGhost();
    var scope = astScope(); astUpdateScope(); astSetPending(true);
    astProgress = null;
    astController = typeof AbortController === "function" ? new AbortController() : null;
    var settled = false, sawDone = false, lastPersist = 0;

    function onEvent(name, payload) {
      if (name === "progress") {
        astProgress = payload || null;
        astRenderProgress();
      } else if (name === "meta") {
        // Preparation is over: from here the answer itself is the progress.
        astProgress = null;
        astApplyMeta(userItem, payload);
        astRenderTranscript();
      } else if (name === "delta" && typeof payload.text === "string") {
        pendingItem.text += payload.text;
        astUpdateStreamingAnswer(pendingItem);
        var now = Date.now();
        if (now - lastPersist > 600) { lastPersist = now; astPersistTranscript(); }
      } else if (name === "done") {
        sawDone = true;
        astApplyMeta(userItem, payload);
        astApplyDone(pendingItem, payload);
        astAddSessionTokens(pendingItem.tokenUsage);
        astRenderTranscript(); astPersistTranscript();
      } else if (name === "error") {
        settled = true;
        astFailPending(pendingItem, payload && payload.detail);
      }
    }

    fetch(API + "assistant/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      signal: astController ? astController.signal : undefined,
      body: JSON.stringify({ question: question, scope: scope.payload, history: history,
        conversation: astConversation, locale: LOCALE })
    }).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(astErrorDetail(body, response.status));
        });
      }
      if (!response.body || typeof response.body.getReader !== "function") {
        // No streaming reader available: take the whole body and replay its events.
        return response.text().then(function (text) { astParseEvents(text + "\n\n", onEvent); });
      }
      var reader = response.body.getReader(), decoder = new TextDecoder(), buffer = "";
      return (function pump() {
        return reader.read().then(function (chunk) {
          if (chunk.done) { buffer = astParseEvents(buffer + "\n\n", onEvent); return; }
          buffer = astParseEvents(buffer + decoder.decode(chunk.value, { stream: true }), onEvent);
          return pump();
        });
      })();
    }).then(function () {
      if (settled) return;
      if (!sawDone) astStopPending(pendingItem);
    }).catch(function (error) {
      if (settled) return;
      if (error && error.name === "AbortError") { astStopPending(pendingItem); return; }
      astFailPending(pendingItem, error && error.message);
    }).then(function () {
      astController = null; astSetPending(false); astQuestion.focus();
    });
  }

  function astStopPending(item) {
    item.pending = false;
    item.stopped = true;
    if (!item.text) item.text = astT("stoppedEmpty");
    astRenderTranscript(); astPersistTranscript();
  }

  function astFailPending(item, message) {
    if (item.text) {
      // The provider died part-way through. Throwing the text away would lose real work,
      // so keep it and say why it stopped, the same as an interrupted answer.
      item.pending = false; item.stopped = true;
      item.stoppedNote = message || astT("noDetail");
      astRenderTranscript(); astPersistTranscript();
      return;
    }
    var index = astTranscript.indexOf(item);
    if (index >= 0) astTranscript.splice(index, 1);
    astPersistTranscript(); astRenderTranscript();
    astAddMessage("assistant", message || astT("noDetail"), [], "", true);
  }

  function astWindowIsCompact() { return window.innerWidth <= 700; }

  function astHasWindowPrefs() {
    try { return Boolean(AST_WINDOW_PREFS_KEY && localStorage.getItem(AST_WINDOW_PREFS_KEY)); }
    catch (error) { return false; }
  }

  function astTrackWindowSize() {
    if (!astDialog.open) return;
    var rect = astDialog.getBoundingClientRect();
    astWindowWidth = rect.width; astWindowHeight = rect.height;
  }

  function astApplyWindowPrefs() {
    if (!AST_WINDOW_PREFS_KEY || astWindowIsCompact()) return;
    try {
      var saved = JSON.parse(localStorage.getItem(AST_WINDOW_PREFS_KEY) || "null");
      if (!saved || !Number.isFinite(saved.width) || !Number.isFinite(saved.height)) return;
      var maxWidth = Math.max(320, window.innerWidth * .94);
      var maxHeight = Math.max(320, window.innerHeight * .90);
      var minWidth = Math.min(680, maxWidth), minHeight = Math.min(520, maxHeight);
      astDialog.style.width = Math.round(Math.max(minWidth, Math.min(saved.width, maxWidth))) + "px";
      astDialog.style.height = Math.round(Math.max(minHeight, Math.min(saved.height, maxHeight))) + "px";
    } catch (error) { /* Corrupt or blocked preferences fall back to the CSS defaults. */ }
  }

  function astPersistWindowPrefs() {
    if (!AST_WINDOW_PREFS_KEY || !astDialog.open || astWindowIsCompact()) return;
    if (!astWindowDirty && !astHasWindowPrefs()) return;
    try {
      var rect = astDialog.getBoundingClientRect();
      if (rect.width >= 320 && rect.height >= 320) {
        localStorage.setItem(AST_WINDOW_PREFS_KEY, JSON.stringify({
          width: Math.round(rect.width), height: Math.round(rect.height)
        }));
        astWindowDirty = false;
      }
    } catch (error) { /* Window sizing remains usable when storage is unavailable. */ }
  }

  function astRememberOpen(open) {
    try { if (AST_WINDOW_OPEN_KEY) sessionStorage.setItem(AST_WINDOW_OPEN_KEY, open ? "1" : "0"); }
    catch (error) {}
  }
  function astWasOpen() {
    try { return AST_WINDOW_OPEN_KEY && sessionStorage.getItem(AST_WINDOW_OPEN_KEY) === "1"; }
    catch (error) { return false; }
  }

  function astOpen() {
    if (astDialog.open) return;
    astLastFocus = document.activeElement; astApplyText(); astUpdateScope();
    if (astUnavailable) {
      if (typeof astDialog.showModal === "function") astDialog.showModal();
      else astDialog.setAttribute("open", "");
      astButton.setAttribute("aria-expanded", "true");
      if (typeof updateParentDim === "function") updateParentDim();
      document.getElementById("ast-close").focus();
      return;
    }
    astApplyWindowPrefs();
    if (typeof astDialog.showModal === "function") astDialog.showModal();
    else astDialog.setAttribute("open", "");
    astWindowDirty = false; astTrackWindowSize();
    astButton.setAttribute("aria-expanded", "true"); astRememberOpen(true);
    if (typeof updateParentDim === "function") updateParentDim();
    if (!astMessages.children.length) {
      if (astTranscript.length) astRenderTranscript(); else astEmpty();
    }
    astQuestion.focus();
  }
  function astClose() {
    astHideClearConfirm();
    astPersistWindowPrefs();
    if (astDialog.open && typeof astDialog.close === "function") astDialog.close();
    else astDialog.removeAttribute("open");
  }

  function astOpenScopeList() {
    var scope = astScope(); if (!scope.selected.length) return;
    astRenderScopeList(scope);
    if (typeof astScopeDialog.showModal === "function") {
      if (!astScopeDialog.open) astScopeDialog.showModal();
    } else astScopeDialog.setAttribute("open", "");
    astScopeList.setAttribute("aria-expanded", "true");
    if (typeof updateParentDim === "function") updateParentDim();
  }
  function astCloseScopeList() {
    if (astScopeDialog.open && typeof astScopeDialog.close === "function") astScopeDialog.close();
    else astScopeDialog.removeAttribute("open");
    astScopeList.setAttribute("aria-expanded", "false");
  }

  function astLoadStatus() {
    fetch(API + "assistant/status").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (status) {
        if (!status) return;
        if (!status.enabled) {
          // A deployment that never set a provider gets no button at all: advertising a
          // feature it did not install would only be noise. One that did set a provider
          // and got it wrong gets the button and the reason, because otherwise the
          // symptom is an assistant that silently does not exist.
          if (status.configured) { astStatus = status; astShowUnavailable(status); }
          return;
        }
        astStatus = status;
        if (Number.isFinite(status.max_history_messages)) {
          AST_MAX_MESSAGES = status.max_history_messages;
        }
        if (Number.isFinite(status.max_history_chars) && status.max_history_chars > 0) {
          AST_MAX_HISTORY_CHARS = status.max_history_chars;
        }
        AST_COMMANDS = Array.isArray(status.commands) ? status.commands.filter(
          function (command) { return command && typeof command.name === "string"; }
        ) : [];
        AST_SERVER_HISTORY = status.history_server_side === true;
        astUseStorageNamespace(status.storage_namespace);
        astButton.hidden = false;
        astQuestion.maxLength = status.max_question_chars || 4000;
        astApplyProviderText();
        if (astWasOpen()) astOpen();
      }).catch(function () { /* Optional feature: keep its button hidden. */ });
  }

  astButton.addEventListener("click", function () { astDialog.open ? astClose() : astOpen(); });
  document.getElementById("ast-close").addEventListener("click", astClose);
  astClear.addEventListener("click", astAskToClear);
  document.getElementById("ast-clear-keep").addEventListener("click", function () {
    astHideClearConfirm(); astQuestion.focus();
  });
  document.getElementById("ast-clear-yes").addEventListener("click", astClearTranscript);
  astChats.addEventListener("click", function () {
    astChatsDialog.open ? astCloseChats() : astOpenChats();
  });
  document.getElementById("ast-chats-dialog-close").addEventListener("click", astCloseChats);
  document.getElementById("ast-chat-new").addEventListener("click", astNewChat);
  astChatsDialog.addEventListener("close", function () {
    astChats.setAttribute("aria-expanded", "false");
    if (typeof updateParentDim === "function") updateParentDim();
  });
  astStop.addEventListener("click", function () { astStop.disabled = true; astStopStream(); });
  astScopeList.addEventListener("click", astOpenScopeList);
  document.addEventListener("click", function (event) {
    var disclosure = document.getElementById("ast-limit-disclosure");
    if (disclosure && !disclosure.contains(event.target)) astCloseLimits(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && astCloseLimits(true)) {
      event.preventDefault(); event.stopPropagation();
    }
  });
  document.getElementById("ast-scope-dialog-close").addEventListener("click", astCloseScopeList);
  document.getElementById("ast-report-context-close").addEventListener("click", astCloseReportContext);
  astReportContextWrap.addEventListener("click", function () {
    astContextWrapped = !astContextWrapped; astApplyContextWrap();
    try {
      if (AST_CONTEXT_WRAP_KEY) {
        localStorage.setItem(AST_CONTEXT_WRAP_KEY, astContextWrapped ? "1" : "0");
      }
    } catch (error) { /* Wrapping still works when preferences cannot be stored. */ }
  });
  astReportContextCopy.addEventListener("click", function () {
    if (!astActiveReportContext) return;
    astReportContextCopy.disabled = true;
    astCopyText(astActiveReportContext.content).then(function () {
      astReportContextCopy.textContent = astT("copied");
    }).catch(function () {
      astReportContextCopy.textContent = astT("copyFailed");
    }).then(function () {
      setTimeout(function () {
        if (!astReportContextCopy.isConnected) return;
        astReportContextCopy.textContent = astT("copyContext");
        astReportContextCopy.disabled = false;
      }, 1500);
    });
  });
  astScopeDialog.addEventListener("close", function () {
    astScopeList.setAttribute("aria-expanded", "false");
    if (typeof updateParentDim === "function") updateParentDim();
  });
  astReportContextDialog.addEventListener("close", function () {
    var trigger = astReportContextTrigger;
    if (!trigger || !trigger.isConnected) trigger = astContextTrigger(astReportContextIndex);
    astActiveReportContext = null; astReportContextTrigger = null;
    astReportContextIndex = null;
    document.getElementById("ast-report-context-code").textContent = "";
    if (typeof updateParentDim === "function") updateParentDim();
    if (trigger && trigger.isConnected && trigger.focus) trigger.focus();
    else if (astDialog.open) astQuestion.focus();
  });
  if (typeof closeOnBackdrop === "function") closeOnBackdrop(astScopeDialog, astCloseScopeList);
  if (typeof closeOnBackdrop === "function") {
    closeOnBackdrop(astReportContextDialog, astCloseReportContext);
  }
  if (typeof closeOnBackdrop === "function") closeOnBackdrop(astDialog, astClose);
  astDialog.addEventListener("close", function () {
    astButton.setAttribute("aria-expanded", "false"); astRememberOpen(false);
    if (typeof updateParentDim === "function") updateParentDim();
    if (astLastFocus && astLastFocus.focus) astLastFocus.focus();
  });
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      if (!astDialog.open || astWindowIsCompact()) return;
      var rect = astDialog.getBoundingClientRect();
      if (astWindowWidth == null || astWindowHeight == null) {
        astWindowWidth = rect.width; astWindowHeight = rect.height; return;
      }
      var changed = Math.abs(rect.width - astWindowWidth) > 2
        || Math.abs(rect.height - astWindowHeight) > 2;
      astWindowWidth = rect.width; astWindowHeight = rect.height;
      if (!changed) return;
      astWindowDirty = true;
      clearTimeout(astResizeTimer);
      astResizeTimer = setTimeout(astPersistWindowPrefs, 180);
    }).observe(astDialog);
  }
  window.addEventListener("pagehide", astPersistWindowPrefs);
  document.getElementById("ast-form").addEventListener("submit", function (event) {
    event.preventDefault(); astSendQuestion(astQuestion.value);
  });
  astQuestion.addEventListener("keydown", function (event) {
    // While the command menu is open it owns the keys it needs. Sending "/" as a question
    // would be nonsense, and Escape here should close the menu, not the whole window.
    if (!astCommands.hidden && astCommandList.length) {
      if (event.key === "ArrowDown") { event.preventDefault(); astHighlightCommand(1); return; }
      if (event.key === "ArrowUp") { event.preventDefault(); astHighlightCommand(-1); return; }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault(); astUseCommand(astCommandIndex); return;
      }
      if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation(); astCloseCommands(); return;
      }
    }
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault(); astSendQuestion(astQuestion.value);
      return;
    }
    // Tab is only taken when there is something to take it for. With no suggestion it
    // keeps its usual job and moves focus, or a keyboard user is trapped in the field.
    if (event.key === "Tab" && !event.shiftKey && astSuggestion) {
      event.preventDefault(); astAcceptSuggestion();
    }
  });
  astQuestion.addEventListener("input", function () {
    astRenderCommands(); astRenderGhost();
  });
  astQuestion.addEventListener("scroll", function () {
    astGhost.scrollTop = astQuestion.scrollTop;
  });
  astQuestion.addEventListener("blur", function () {
    astGhost.hidden = true; astCloseCommands();
  });
  astQuestion.addEventListener("focus", astRenderGhost);
  ["f-dag", "f-task", "f-run"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", function () {
      if (astDialog.open) astUpdateScope();
    });
  });
  astClear.hidden = true;
  astApplyText(); astLoadStatus();
"""


def assistant_css() -> str:
    """Return the assistant-only stylesheet fragment."""
    return _CSS


def assistant_button_html() -> str:
    """Return the lazy header trigger."""
    return _BUTTON


def assistant_panel_html() -> str:
    """Return the centered, resizable assistant dialog markup."""
    return _PANEL


def assistant_js() -> str:
    """Return behavior injected inside the dashboard's existing JS closure."""
    return _JS


__all__ = [
    "assistant_button_html",
    "assistant_css",
    "assistant_js",
    "assistant_panel_html",
]
