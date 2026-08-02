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

"""Dependency-free, bilingual user guide for the Pytest Reports viewer."""

from __future__ import annotations

from functools import lru_cache
from html import escape

from ..version import __version__

_HELP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Pytest Reports help</title>
<style>
  :root {
    --bg: #ffffff; --surface: #ffffff; --surface-2: #f4f4f5;
    --surface-blue: #eff6ff; --fg: #18181b; --muted: #52525b;
    --border: #e4e4e7; --primary: #017cee; --on-primary: #ffffff;
    --ring: #017cee; --code-bg: #f4f4f5; --success: #15803d;
    --warning: #a16207; --danger: #dc2626;
    --shadow: 0 1px 2px #0000000d, 0 1px 3px #00000014;
  }
  html[data-theme="dark"] {
    --bg: #07121e; --surface: #1c2a3a; --surface-2: #243651;
    --surface-blue: #102a46; --fg: #e6edf3; --muted: #a8b5c7;
    --border: #2c4262; --primary: #4ba3f5; --on-primary: #07121e;
    --ring: #4ba3f5; --code-bg: #101c2a; --success: #4ade80;
    --warning: #facc15; --danger: #f87171;
    --shadow: 0 1px 3px #00000040, 0 2px 8px #00000033;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; scroll-padding-top: 88px; }
  body {
    margin: 0; min-width: 0; background: var(--bg); color: var(--fg);
    font: 16px/1.65 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  a { color: var(--primary); }
  a:focus-visible, button:focus-visible, summary:focus-visible {
    outline: 3px solid var(--ring); outline-offset: 2px;
  }
  .skip-link {
    position: fixed; z-index: 100; left: 16px; top: 8px; width: 1px; height: 1px;
    margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0);
    clip-path: inset(50%); white-space: nowrap; border: 0; border-radius: 8px;
    background: var(--primary); color: var(--on-primary);
  }
  .skip-link:focus {
    width: auto; height: auto; min-height: 44px; margin: 0; padding: 9px 14px;
    overflow: visible; clip: auto; clip-path: none;
  }
  header {
    position: sticky; z-index: 30; top: 0; min-height: 60px;
    border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--bg) 92%, transparent);
    backdrop-filter: blur(10px);
  }
  .header-inner {
    max-width: 1280px; min-height: 60px; margin: 0 auto; padding: 8px 24px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }
  .header-actions {
    display: flex; align-items: center; justify-content: flex-end; gap: 8px;
    flex: 0 0 auto;
  }
  .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .brand-mark {
    width: 32px; height: 32px; display: grid; place-items: center; flex: 0 0 auto;
    border-radius: 9px; color: var(--primary); background: var(--surface-blue);
  }
  .brand-mark svg { width: 19px; height: 19px; }
  .brand-copy { min-width: 0; line-height: 1.2; }
  .brand-title { display: block; font-size: 14px; font-weight: 700; }
  .brand-subtitle { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }
  .btn {
    min-height: 44px; padding: 0 14px; display: inline-flex; align-items: center;
    justify-content: center; gap: 8px; border: 1px solid var(--border); border-radius: 8px;
    color: var(--fg); background: var(--surface); font: inherit; font-size: 14px;
    font-weight: 600; line-height: 1; text-decoration: none; cursor: pointer;
    transition: background 160ms ease-out, border-color 160ms ease-out;
    touch-action: manipulation;
  }
  .btn-label {
    min-height: 20px; display: inline-flex; align-items: center; line-height: 1.2;
  }
  .btn:hover { border-color: color-mix(in srgb, var(--primary) 55%, var(--border));
    background: var(--surface-2); }
  .btn svg { width: 17px; height: 17px; flex: 0 0 auto; }
  .page {
    width: min(1280px, 100%); margin: 0 auto; padding: 40px 24px 80px;
  }
  .hero {
    position: relative; overflow: hidden; padding: 40px;
    border: 1px solid var(--border); border-radius: 16px; background: var(--surface);
    box-shadow: var(--shadow);
  }
  .hero::after {
    content: ""; position: absolute; right: -90px; top: -120px; width: 320px; height: 320px;
    border-radius: 50%; background: color-mix(in srgb, var(--primary) 10%, transparent);
    pointer-events: none;
  }
  .eyebrow {
    margin: 0 0 10px; color: var(--primary); font-size: 13px; font-weight: 750;
    letter-spacing: .08em; text-transform: uppercase;
  }
  h1 {
    position: relative; z-index: 1; max-width: 850px; margin: 0;
    font-size: clamp(32px, 5vw, 52px); line-height: 1.08; letter-spacing: -.035em;
  }
  .lede {
    position: relative; z-index: 1; max-width: 760px; margin: 18px 0 0;
    color: var(--muted); font-size: 18px; line-height: 1.65;
  }
  .hero-tags { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; }
  .tag {
    padding: 5px 10px; border: 1px solid var(--border); border-radius: 999px;
    color: var(--muted); background: var(--surface-2); font-size: 13px; font-weight: 600;
  }
  .mobile-toc { display: none; margin-top: 20px; }
  .mobile-toc details {
    border: 1px solid var(--border); border-radius: 10px; background: var(--surface);
  }
  .mobile-toc summary {
    min-height: 48px; padding: 11px 14px; display: flex; align-items: center;
    justify-content: space-between; cursor: pointer; font-weight: 700;
  }
  .mobile-toc summary::after { content: "⌄"; color: var(--muted); }
  .mobile-links { padding: 4px 8px 10px; display: grid; }
  .mobile-links a {
    min-height: 44px; padding: 10px; color: var(--muted); text-decoration: none;
    border-radius: 7px;
  }
  .mobile-links a:hover { color: var(--fg); background: var(--surface-2); }
  .help-layout {
    display: grid; grid-template-columns: 248px minmax(0, 780px);
    justify-content: center; gap: 56px; margin-top: 48px;
  }
  .help-sidebar {
    align-self: start; position: sticky; top: 88px; max-height: calc(100vh - 112px);
    overflow: auto; padding-right: 8px;
  }
  .toc-label {
    margin: 0 0 10px 12px; color: var(--muted); font-size: 12px;
    font-weight: 750; letter-spacing: .08em; text-transform: uppercase;
  }
  .toc { display: grid; gap: 2px; }
  .toc a {
    min-height: 40px; padding: 8px 12px; display: flex; align-items: center;
    border-left: 2px solid transparent; border-radius: 0 7px 7px 0;
    color: var(--muted); font-size: 14px; font-weight: 550; line-height: 1.35;
    text-decoration: none; transition: color 160ms ease-out, background 160ms ease-out;
  }
  .toc a:hover { color: var(--fg); background: var(--surface-2); }
  .toc a[aria-current="true"] {
    border-left-color: var(--primary); color: var(--primary); background: var(--surface-blue);
  }
  article { min-width: 0; max-width: 100%; }
  .doc-section { padding: 0 0 56px; margin: 0 0 56px; border-bottom: 1px solid var(--border); }
  .doc-section:last-child { border-bottom: 0; margin-bottom: 0; padding-bottom: 0; }
  .section-kicker { margin: 0 0 8px; color: var(--primary); font-size: 13px; font-weight: 750; }
  h2 { margin: 0 0 16px; font-size: clamp(26px, 4vw, 34px); line-height: 1.2; letter-spacing: -.025em; }
  h3 { margin: 32px 0 10px; font-size: 19px; line-height: 1.35; }
  p { margin: 0 0 16px; }
  p, li { color: var(--muted); }
  strong { color: var(--fg); }
  code, .mono {
    padding: 2px 5px; border-radius: 5px; color: var(--fg); background: var(--code-bg);
    font: .88em/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    overflow-wrap: anywhere;
  }
  .steps { margin: 24px 0 0; padding: 0; display: grid; gap: 14px; list-style: none; counter-reset: step; }
  .steps li {
    position: relative; min-height: 52px; padding: 4px 0 4px 54px; counter-increment: step;
  }
  .steps li::before {
    content: counter(step); position: absolute; left: 0; top: 0; width: 38px; height: 38px;
    display: grid; place-items: center; border-radius: 50%; color: var(--on-primary);
    background: var(--primary); font-weight: 750;
  }
  .cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 20px 0; }
  .card { padding: 18px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
  .card h3 { margin: 0 0 6px; font-size: 16px; }
  .card p { margin: 0; font-size: 14px; }
  .metric { display: flex; align-items: baseline; gap: 9px; margin-bottom: 7px; }
  .metric strong { font-size: 16px; }
  .status-dot { width: 9px; height: 9px; flex: 0 0 auto; border-radius: 50%; }
  .pass { background: var(--success); } .warn { background: var(--warning); } .fail { background: var(--danger); }
  .callout {
    margin: 22px 0; padding: 16px 18px; border-left: 4px solid var(--primary);
    border-radius: 0 9px 9px 0; background: var(--surface-blue);
  }
  .callout p { margin: 0; color: var(--fg); }
  .example {
    margin: 20px 0; overflow: hidden; border: 1px solid var(--border);
    border-radius: 10px; background: var(--code-bg);
  }
  .example-label {
    padding: 8px 14px; border-bottom: 1px solid var(--border); color: var(--muted);
    background: var(--surface); font-size: 12px; font-weight: 750; letter-spacing: .05em;
    text-transform: uppercase;
  }
  pre {
    margin: 0; padding: 16px; overflow: auto; color: var(--fg);
    font: 13px/1.65 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  .table-wrap { margin: 20px 0; overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
  table { width: 100%; border-collapse: collapse; min-width: 560px; }
  th, td { padding: 12px 14px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--border); }
  th { color: var(--fg); background: var(--surface-2); font-size: 13px; }
  td { color: var(--muted); font-size: 14px; }
  tr:last-child td { border-bottom: 0; }
  /* An identifier broken across lines ("logs_only_f / ail", "Fals / e") is not a name or a
     value any more. The name and default columns keep their code on one line; the wrapper
     scrolls if that needs room. On a phone the table is a stack of cards with nowhere to
     scroll, so there the longest names (the retention env vars) wrap rather than being
     clipped out of sight -- see below. Defaults are short enough to always fit. */
  td:first-child code,
  td:nth-child(2) code { white-space: nowrap; }
  .check-list { margin: 18px 0; padding: 0; display: grid; gap: 10px; list-style: none; }
  .check-list li { position: relative; padding-left: 30px; }
  .check-list li::before {
    content: ""; position: absolute; left: 2px; top: .45em; width: 15px; height: 9px;
    border-left: 2px solid var(--success); border-bottom: 2px solid var(--success);
    transform: rotate(-45deg);
  }
  .faq { display: grid; gap: 10px; margin-top: 20px; }
  .faq details { border: 1px solid var(--border); border-radius: 9px; background: var(--surface); }
  .faq summary {
    min-height: 48px; padding: 12px 16px; display: flex; align-items: center;
    cursor: pointer; color: var(--fg); font-weight: 650;
  }
  .faq details p { padding: 0 16px 16px; margin: 0; }
  footer { max-width: 780px; margin: 56px auto 0; color: var(--muted); font-size: 13px; text-align: center; }
  .ver { font-size: 12px; color: var(--muted); user-select: all; }
  .rel-links { margin: 18px 0; display: flex; flex-wrap: wrap; gap: 10px; }
  .rel-links .btn { text-decoration: none; }
  footer a {
    min-height: 44px; padding: 0 4px; display: inline-flex; align-items: center;
    color: var(--primary); font-weight: 650; text-underline-offset: 3px;
  }
  @media (max-width: 1100px) and (min-width: 901px) {
    .page { padding-inline: 20px; }
    .help-layout { grid-template-columns: 220px minmax(0, 1fr); gap: 32px; }
    .hero { padding: 32px; }
  }
  @media (max-width: 900px) {
    .page { padding-top: 24px; }
    .hero { padding: 28px 24px; }
    .help-layout { display: block; margin-top: 40px; }
    .help-sidebar { display: none; }
    .mobile-toc {
      position: sticky; z-index: 20; top: 68px; display: block;
      background: color-mix(in srgb, var(--bg) 92%, transparent);
      backdrop-filter: blur(10px);
    }
    article { max-width: 760px; margin: 0 auto; }
    /* Below 900px the table of contents becomes a second sticky bar under the header, so an
       anchor jump has to clear both -- otherwise the section kicker lands behind it. */
    html { scroll-padding-top: 134px; }
  }
  @media (max-width: 600px) {
    .header-inner { padding: 8px 12px; }
    .header-actions { gap: 6px; }
    .brand-subtitle { display: none; }
    .btn .btn-label { display: none; }
    .btn { width: 44px; padding: 0; }
    .page { padding: 16px 12px 56px; }
    .hero { padding: 24px 20px; border-radius: 12px; }
    .lede { font-size: 16px; }
    .cards { grid-template-columns: 1fr; }
    .doc-section { padding-bottom: 42px; margin-bottom: 42px; }
    .table-wrap { overflow: visible; border: 0; border-radius: 0; }
    table { min-width: 0; display: block; }
    thead { display: none; }
    tbody { display: grid; gap: 10px; }
    tr {
      display: grid; overflow: hidden; border: 1px solid var(--border);
      border-radius: 9px; background: var(--surface);
    }
    td { display: block; border: 0; }
    td:first-child code { white-space: normal; overflow-wrap: anywhere; }
    td:first-child {
      padding-bottom: 6px; color: var(--fg); background: var(--surface-2);
      font-weight: 700;
    }
    td + td { padding-top: 10px; }
    pre { font-size: 12px; }
  }
  @media (max-width: 360px) {
    .hero { padding-inline: 16px; }
    .hero-tags { gap: 6px; }
    .tag { padding-inline: 8px; }
    h1 { font-size: 29px; }
  }
  @media (max-width: 900px) and (max-height: 600px) {
    /* Landscape phones: the contents bar stops sticking, so only the header has to be cleared. */
    .mobile-toc { position: static; }
    html { scroll-padding-top: 76px; }
  }
  @media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    *, *::before, *::after { transition-duration: .01ms !important; animation-duration: .01ms !important; }
  }
</style>
<script>
(function () {
  try {
    var top = window.top;
    if (top && top !== window.self) {
      var bg = getComputedStyle(top.document.documentElement).backgroundColor;
      var m = bg && bg.match(/(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
      if (m) {
        var lum = 0.299 * +m[1] + 0.587 * +m[2] + 0.114 * +m[3];
        document.documentElement.setAttribute("data-theme", lum < 128 ? "dark" : "light");
        if (bg.indexOf("rgba(0, 0, 0, 0)") === -1) {
          document.documentElement.style.setProperty("--bg", bg);
        }
        return;
      }
    }
    if (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) {
      document.documentElement.setAttribute("data-theme", "dark");
    }
  } catch (e) {}
})();
</script>
</head>
<body>
<a class="skip-link" href="#help-content" data-i18n="skip">Skip to the guide</a>
<header>
  <div class="header-inner">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 3h6M10 3v6.3a2 2 0 0 1-.4 1.2L4.5 18a2 2 0 0 0 1.6 3.2h11.8a2 2 0 0 0 1.6-3.2l-5.1-7.5a2 2 0 0 1-.4-1.2V3"/>
          <path d="M7.2 15h9.6"/>
        </svg>
      </span>
      <span class="brand-copy">
        <span class="brand-title">Pytest Reports</span>
        <span class="brand-subtitle" data-i18n="guide">User guide</span>
      </span>
    </div>
    <div class="header-actions">
      <a id="help-github-link" class="btn" href="https://github.com/IKrysanov/airflow-pytest-plugin"
        target="_blank" rel="noopener noreferrer" aria-label="GitHub">
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17 5 18 5.3 18 5.3c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/>
        </svg>
        <span class="btn-label">GitHub</span>
      </a>
      <a id="help-api-link" class="btn" href="/api/docs" target="_blank"
        rel="noopener noreferrer" data-i18n-al="apiDocs">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m8 9-3 3 3 3M16 9l3 3-3 3M14 5l-4 14"/>
        </svg>
        <span class="btn-label" data-i18n="apiDocs">API docs</span>
      </a>
      <a id="back-btn" class="btn" href="/" data-i18n-al="back">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m15 18-6-6 6-6"/>
        </svg>
        <span class="btn-label" data-i18n="back">Back to reports</span>
      </a>
    </div>
  </div>
</header>

<div class="page">
  <section class="hero" aria-labelledby="help-title">
    <p class="eyebrow" data-i18n="guide">User guide</p>
    <h1 id="help-title" data-i18n="title">Understand every test run at a glance</h1>
    <p class="lede" data-i18n="lede">Find a run, see what broke, spot flaky or slow tests, and share the result — without leaving Airflow.</p>
    <div class="hero-tags" aria-label="Guide topics" data-i18n-al="guideTopics">
      <span class="tag" data-i18n="tagRuns">Runs</span>
      <span class="tag" data-i18n="tagFailures">Failures</span>
      <span class="tag" data-i18n="tagTrends">Trends</span>
      <span class="tag" data-i18n="tagTriage">AI triage</span>
      <span class="tag" data-i18n="tagSharing">Sharing</span>
    </div>
  </section>

  <nav class="mobile-toc" aria-label="Help sections" data-i18n-al="helpSections">
    <details>
      <summary data-i18n="contents">On this page</summary>
      <div class="mobile-links"></div>
    </details>
  </nav>

  <div class="help-layout">
    <aside class="help-sidebar">
      <p class="toc-label" data-i18n="contents">On this page</p>
      <nav class="toc" aria-label="Help sections" data-i18n-al="helpSections">
        <a href="#getting-started" data-i18n="navStart">Getting started</a>
        <a href="#setup" data-i18n="navSetup">Set up the plugin</a>
        <a href="#dashboard" data-i18n="navDashboard">Dashboard</a>
        <a href="#find" data-i18n="navFind">Find a run</a>
        <a href="#run-details" data-i18n="navDetails">Run details</a>
        <a href="#flaky" data-i18n="navFlaky">Flaky tests & history</a>
        <a href="#compare" data-i18n="navCompare">Compare & heatmap</a>
        <a href="#failures" data-i18n="navFailures">Failures & performance</a>
        <a href="#ai-triage" data-i18n="navTriage">Coverage & AI triage</a>
        <a href="#email" data-i18n="navShare">Allure & email</a>
        <a href="#access" data-i18n="navAccess">Settings & access</a>
        <a href="#faq" data-i18n="navFaq">FAQ</a>
        <a href="#whats-new" data-i18n="navRelease">Release notes</a>
      </nav>
    </aside>

    <article id="help-content" tabindex="-1">
      <section class="doc-section" id="getting-started">
        <p class="section-kicker" data-i18n="s1Kicker">01 · First visit</p>
        <h2 data-i18n="s1Title">Getting started</h2>
        <p data-i18n-html="s1Intro">Open <strong>Browse → Pytest</strong> in Airflow. The newest archived runs appear first. No separate sign-in or plugin language setting is needed.</p>
        <ol class="steps">
          <li data-i18n-html="s1Step1"><strong>Start with the KPIs.</strong> They tell you how many runs and unique tests are visible, what is currently failing, and whether anything slowed down.</li>
          <li data-i18n-html="s1Step2"><strong>Narrow the list.</strong> Filter by DAG, task, or run ID. The cards, chart, reliability score, and lists follow the same view.</li>
          <li data-i18n-html="s1Step3"><strong>Open a run.</strong> Click its row to inspect individual tests, captured output, coverage, AI verdicts, and links back to Airflow.</li>
        </ol>
        <div class="callout"><p data-i18n-html="s1Tip"><strong>Tip:</strong> the tracking link in a PytestOperator task log opens the exact archived run, including its try number.</p></div>
      </section>

      <section class="doc-section" id="setup">
        <p class="section-kicker" data-i18n="setupKicker">02 · Airflow administrator</p>
        <h2 data-i18n="setupTitle">Set up the plugin correctly</h2>
        <p data-i18n="setupIntro">This one-time checklist is for the person who operates Airflow. Application users can skip directly to the dashboard section.</p>
        <ol class="steps">
          <li data-i18n-html="setupStep1"><strong>Install the same plugin version</strong> on the API server and every worker that runs pytest tasks.</li>
          <li data-i18n-html="setupStep2"><strong>Choose one shared report directory.</strong> Mount it at the same path on workers and the API server, then set <code>AIRFLOW_PYTEST_REPORTS_ROOT</code> everywhere.</li>
          <li data-i18n-html="setupStep3"><strong>Archive operator results.</strong> Pass <code>ArchivingResultParser()</code> to each PytestOperator that should appear in the viewer.</li>
          <li data-i18n-html="setupStep4"><strong>Restart and verify.</strong> Restart the Airflow API server after installation, open Browse → Pytest, and confirm that health reports <code>ready: true</code>.</li>
        </ol>
        <div class="example">
          <div class="example-label" data-i18n="setupInstallLabel">Install on API server and workers</div>
          <pre>pip install airflow-pytest-plugin</pre>
        </div>
        <div class="callout"><p data-i18n-html="setupSecurity"><strong>Production hardening:</strong> if archived JUnit files may come from code you do not fully trust, install <code>airflow-pytest-plugin[secure-xml]</code> on the API server for hardened XML parsing.</p></div>
        <div class="example">
          <div class="example-label" data-i18n="setupRootLabel">Shared report storage</div>
          <pre>export AIRFLOW_PYTEST_REPORTS_ROOT=/opt/airflow/pytest-reports</pre>
        </div>
        <div class="example">
          <div class="example-label" data-i18n="setupDagLabel">DAG configuration</div>
          <pre>from airflow_pytest_plugin import ArchivingResultParser

PytestOperator(
    task_id="pytest",
    test_path="tests/",
    parser=ArchivingResultParser(),
)</pre>
        </div>
        <div class="callout"><p data-i18n-html="setupTip"><strong>No special cleanup mode is required.</strong> The archiving parser owns its report directory, so you do not need <code>cleanup="never"</code>.</p></div>
        <h3 data-i18n="setupOptionalTitle">Enable optional features deliberately</h3>
        <p data-i18n="setupOptionalBody">Coverage, Allure export, AI triage, email, retention, and Prometheus metrics are independent. Enable only the features your team will use, verify their buttons or cards on one test DAG, and keep secrets in Airflow connections or environment variables rather than DAG source.</p>

        <h3 data-i18n="paramsTitle">Every parser option</h3>
        <p data-i18n-html="paramsIntro">Bare <code>ArchivingResultParser()</code> already archives the run and its captured output — everything below is optional. Options marked <em>worker-side</em> need their package installed where the tests run, or pytest stops on an unknown argument.</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th data-i18n="paramCol">Option</th><th data-i18n="paramDefault">Default</th><th data-i18n="meaning">Meaning</th></tr></thead>
            <tbody>
              <tr><td><code>report_root</code></td><td><code>None</code></td><td data-i18n-html="pReportRoot">Where runs are archived. Unset, it follows <code>AIRFLOW_PYTEST_REPORTS_ROOT</code> — set that once for the whole install instead of repeating a path in every DAG.</td></tr>
              <tr><td><code>layout</code></td><td><code>None</code></td><td data-i18n="pLayout">The directory scheme inside that root. Leave it alone unless you are migrating an existing archive; the viewer expects the default.</td></tr>
              <tr><td><code>logs</code></td><td><code>True</code></td><td data-i18n="pLogs">Archive what each test printed and logged. Off, the run keeps tracebacks only — for a suite whose logging would dwarf its report.</td></tr>
              <tr><td><code>logs_only_fail</code></td><td><code>False</code></td><td data-i18n="pLogsOnlyFail">Keep that output for failed and errored tests alone. The passing majority writes most of the volume and is the part nobody reads.</td></tr>
              <tr><td><code>allure</code></td><td><code>False</code></td><td data-i18n-html="pAllure">Archive raw Allure results beside the run and show a download button for TestOps. <em>Worker-side:</em> needs <code>allure-pytest</code>.</td></tr>
              <tr><td><code>coverage</code></td><td><code>False</code></td><td data-i18n-html="pCoverage">Measure coverage and store it with the run, so the Coverage card survives even a failed run. <em>Worker-side:</em> needs <code>pytest-cov</code>.</td></tr>
              <tr><td><code>coverage_source</code></td><td><code>None</code></td><td data-i18n-html="pCoverageSource">What to measure, as in <code>coverage_source="src"</code>. Set it when the project already narrows coverage itself — otherwise measurement widens and the percentage silently changes.</td></tr>
              <tr><td><code>coverage_threshold</code></td><td><code>None</code></td><td data-i18n="pCoverageThreshold">The bar this suite is judged against, 0 to 1. It only colours the card — it never fails a run. Unset, the server-wide default applies.</td></tr>
              <tr><td><code>triage</code></td><td><code>None</code></td><td data-i18n-html="pTriage">AI triage. Left unset it follows <code>triage_provider</code>. <code>True</code> alone archives a failure report with no model calls; <code>False</code> is an off switch and wins even when a provider is named. <em>Worker-side:</em> needs <code>pytest-triage</code>.</td></tr>
              <tr><td><code>triage_provider</code></td><td><code>None</code></td><td data-i18n-html="pTriageProvider">Which model service judges the failures — <code>"anthropic"</code>, <code>"openai"</code>, <code>"gigachat"</code>, or <code>"fake"</code> for an offline dry run. Naming one turns triage on. Keys come from the environment; the plugin never stores them.</td></tr>
              <tr><td><code>triage_budget</code></td><td><code>None</code></td><td data-i18n="pTriageBudget">Most model calls one run may make — the cost ceiling, since each failing test costs one call. Unset, the library's own default (10) applies.</td></tr>
              <tr><td><code>triage_timeout</code></td><td><code>None</code></td><td data-i18n="pTriageTimeout">Seconds one call may take before the run gives up on it and says the pass was incomplete.</td></tr>
              <tr><td><code>email</code></td><td><code>False</code></td><td data-i18n="pEmail">Email the result after every run of this task. Needs a mail transport and recipients configured on the server.</td></tr>
              <tr><td><code>email_only_fail</code></td><td><code>False</code></td><td data-i18n="pEmailOnlyFail">Email only when the run failed or a test is flaky — the setting most teams want, so a green night stays quiet.</td></tr>
            </tbody>
          </table>
        </div>
        <div class="callout"><p data-i18n-html="paramsCapture"><strong>Captured output is archived verbatim.</strong> Whatever a test prints or logs is stored as the run produced it — the plugin does not mask secrets, so a test that prints a token archives that token. Keep credentials out of test output, or archive with <code>logs=False</code>; who can read it is decided by the same Airflow DAG permissions as the run itself.</p></div>
        <div class="example">
          <div class="example-label" data-i18n="paramsExampleLabel">A fully equipped task</div>
          <pre data-i18n="paramsExampleCode">ArchivingResultParser(
    logs_only_fail=True,
    allure=True,
    coverage=True,
    coverage_source="src",
    triage_provider="anthropic",
    triage_budget=20,
    email_only_fail=True,
)</pre>
        </div>

        <h3 data-i18n="retentionTitle">Delete old reports automatically</h3>
        <p data-i18n="retentionIntro">Reports are kept forever until someone prunes them: the plugin never deletes on its own. Turn on any of the limits below and schedule the cleanup from a maintenance DAG.</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th data-i18n="paramCol">Setting</th><th data-i18n="paramDefault">Default</th><th data-i18n="meaning">Meaning</th></tr></thead>
            <tbody>
              <tr><td><code>AIRFLOW_PYTEST_RETENTION_MAX_AGE_DAYS</code></td><td data-i18n="retNone">unset</td><td data-i18n="retAge">Delete runs older than N days.</td></tr>
              <tr><td><code>AIRFLOW_PYTEST_RETENTION_MAX_RUNS</code></td><td data-i18n="retNone">unset</td><td data-i18n="retRuns">Keep only the N newest runs of each DAG·task.</td></tr>
              <tr><td><code>AIRFLOW_PYTEST_RETENTION_MAX_TOTAL_MB</code></td><td data-i18n="retNone">unset</td><td data-i18n="retSize">Keep the whole archive under N megabytes, deleting oldest first.</td></tr>
              <tr><td><code>AIRFLOW_PYTEST_MAX_REPORT_MIB</code></td><td><code>64</code></td><td data-i18n="limReport">Largest report the viewer will open. A run past it stays in the list with its real numbers, but opening it says so instead. Raise it if a suite really archives more; 0 removes the limit.</td></tr>
              <tr><td><code>AIRFLOW_PYTEST_MAX_META_MIB</code></td><td><code>16</code></td><td data-i18n="limMeta">Largest run index a scan decodes whole (about a quarter-million tests). Past it a run still lists, opens and is cleaned up as usual; only its per-test data is read from the report instead.</td></tr>
            </tbody>
          </table>
        </div>
        <div class="example">
          <div class="example-label" data-i18n="retentionDagLabel">Maintenance DAG</div>
          <pre>from airflow_pytest_plugin import prune_reports

with DAG("pytest_reports_retention", schedule="@daily", catchup=False):
    PythonOperator(task_id="prune", python_callable=prune_reports)</pre>
        </div>
        <p data-i18n-html="retentionRules">Set as many limits as you like: a run goes if <strong>any</strong> of them says so. The <strong>newest run of every DAG·task is always kept</strong>, so a task's latest result never disappears no matter how tight the limits are. To see what a policy would remove before trusting it, call <code>prune_reports(dry_run=True)</code> — it deletes nothing and reports how many runs and bytes it would have freed.</p>
        <h3 data-i18n="setupAccessTitle">Check access with two roles</h3>
        <p data-i18n="setupAccessBody">Test with a normal reader and an operator: the reader should see only permitted DAG reports, while deletion should remain available only to a role that can trigger the DAG.</p>
      </section>

      <section class="doc-section" id="dashboard">
        <p class="section-kicker" data-i18n="s2Kicker">03 · Overview</p>
        <h2 data-i18n="s2Title">Read the dashboard</h2>
        <p data-i18n="s2Intro">The dashboard answers three questions: how much ran, how healthy it is now, and whether the direction is improving.</p>
        <div class="cards">
          <div class="card"><div class="metric"><span class="status-dot pass"></span><strong data-i18n="kpiRuns">Runs & passing runs</strong></div><p data-i18n="kpiRunsBody">All visible archived runs, and the number that cleared the configured pass-rate threshold.</p></div>
          <div class="card"><div class="metric"><span class="status-dot pass"></span><strong data-i18n="kpiUnique">Unique tests</strong></div><p data-i18n="kpiUniqueBody">Distinct pytest node IDs across the visible history. Click for the searchable catalogue and per-test totals.</p></div>
          <div class="card"><div class="metric"><span class="status-dot fail"></span><strong data-i18n="kpiFailures">Failures</strong></div><p data-i18n="kpiFailuresBody">Tests broken in the latest run of each DAG·task. A fixed test disappears after the next green run.</p></div>
          <div class="card"><div class="metric"><span class="status-dot warn"></span><strong data-i18n="kpiSlow">Slowdowns</strong></div><p data-i18n="kpiSlowBody">Tests whose recent execution time is meaningfully worse than their older baseline.</p></div>
        </div>
        <h3 data-i18n="chartTitle">Recent runs chart</h3>
        <p data-i18n-html="chartBody">Each bar is one run, stacked by <strong>passed, failed, error, and skipped</strong>. Click the legend to focus statuses, drag or use the arrows for older runs, and tick list rows to chart only those runs. The optional pass-rate line includes the suite's success threshold.</p>
        <h3 data-i18n="reliabilityTitle">Reliability</h3>
        <p data-i18n="reliabilityBody">The radar combines pass rate, absence of errors, current green DAG·tasks, stability, and completeness. The line below it shows run health over time; use the arrow to compare the recent half with the older half.</p>
        <h3 data-i18n="flakyPanelTitle">Flaky panel</h3>
        <p data-i18n="flakyPanelBody">This is the quick watchlist for tests that switch between pass and fail. Search within it, show quarantined tests only, or click a row for the full history.</p>
      </section>

      <section class="doc-section" id="find">
        <p class="section-kicker" data-i18n="s3Kicker">04 · Navigation</p>
        <h2 data-i18n="s3Title">Find the run you need</h2>
        <ul class="check-list">
          <li data-i18n-html="find1"><strong>DAG filter</strong> — isolate one pipeline, for example <code>payments_daily</code>.</li>
          <li data-i18n-html="find2"><strong>Task filter</strong> — compare only the pytest task within that DAG.</li>
          <li data-i18n-html="find3"><strong>Run filter</strong> — paste part of a scheduled or manual run ID.</li>
          <li data-i18n-html="find4"><strong>Group by DAG·task</strong> — collapse a busy history into suites with run count, pass rate, average time, and latest status.</li>
          <li data-i18n-html="find5"><strong>Sort and select</strong> — sort columns by clicking their labels; tick runs or a whole group to focus the charts and analytics.</li>
        </ul>
        <div class="example">
          <div class="example-label" data-i18n="example">Example</div>
          <pre>payments_daily
scheduled__2026-07-27T06:00:00+00:00
pytest_integration · try 1</pre>
        </div>
        <p data-i18n="findNote">Filters are suggestions, not exact-match fields: a meaningful fragment is usually enough. Clear them with the × button in the header.</p>
      </section>

      <section class="doc-section" id="run-details">
        <p class="section-kicker" data-i18n="s4Kicker">05 · Investigation</p>
        <h2 data-i18n="s4Title">Investigate one run</h2>
        <p data-i18n="s4Intro">A run opens as a focused report while preserving the dashboard underneath. Its toolbar links back to the DAG, DAG run, and task instance in Airflow.</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th data-i18n="detailArea">Area</th><th data-i18n="detailUse">How to use it</th></tr></thead>
            <tbody>
              <tr><td data-i18n="detailSummary">Summary & donut</td><td data-i18n="detailSummaryBody">Check totals and pass rate. Click a donut slice to filter the case table by outcome.</td></tr>
              <tr><td data-i18n="detailDuration">Duration histogram</td><td data-i18n="detailDurationBody">See whether time is spread evenly or dominated by a few long-running tests.</td></tr>
              <tr><td data-i18n="detailCases">Case table</td><td data-i18n="detailCasesBody">Search by node ID, group by module, sort by test or duration, and expand a row for its failure and captured output.</td></tr>
              <tr><td data-i18n="detailTry">Try number</td><td data-i18n="detailTryBody">Retries stay separate. Compare tries when the same task changes outcome or diagnosis.</td></tr>
              <tr><td data-i18n="detailLink">Copy link</td><td data-i18n="detailLinkBody">Share a deep link to this exact DAG, run, task, and try. The recipient still needs Airflow access.</td></tr>
            </tbody>
          </table>
        </div>
        <div class="callout"><p data-i18n-html="s4Tip"><strong>Fast path:</strong> sort the case table by time to surface the slowest tests first, or click a status to isolate only failures and errors.</p></div>
      </section>

      <section class="doc-section" id="flaky">
        <p class="section-kicker" data-i18n="s5Kicker">06 · Stability</p>
        <h2 data-i18n="s5Title">Understand flaky tests and history</h2>
        <p data-i18n="s5Intro">A test is flaky when it both passes and fails within the recent window for the same DAG·task. The same node ID in another task is evaluated separately.</p>
        <div class="cards">
          <div class="card"><h3 data-i18n="scoreTitle">Flakiness score</h3><p data-i18n="scoreBody">How often the result flips between pass and fail. Higher means less predictable.</p></div>
          <div class="card"><h3 data-i18n="trendTitle">Trend</h3><p data-i18n="trendBody">Compares the recent half of the window with the older half: getting worse, calming down, or steady.</p></div>
          <div class="card"><h3 data-i18n="quarantineTitle">Quarantine</h3><p data-i18n="quarantineBody">A visible badge once the score crosses the configured quarantine threshold. It is a signal, not an automatic pytest action.</p></div>
          <div class="card"><h3 data-i18n="historyCardTitle">Test history</h3><p data-i18n="historyCardBody">A run-by-run strip of outcomes. “Did not run” stays distinct from skipped, failed, and passed.</p></div>
        </div>
        <p data-i18n="flakyAction">Open Flaky tests from a group or run, choose the analysis window, and click a test to see exactly when it started changing.</p>
      </section>

      <section class="doc-section" id="compare">
        <p class="section-kicker" data-i18n="s6Kicker">07 · Change over time</p>
        <h2 data-i18n="s6Title">Compare runs and scan the heatmap</h2>
        <h3 data-i18n="compareTitle">Compare to previous</h3>
        <p data-i18n-html="compareBody">From a run, choose <strong>Compare to previous</strong> to classify every test as newly failed, fixed, still failing, added, or removed. This is the fastest answer to “what changed in this build?”</p>
        <h3 data-i18n="heatmapTitle">Test × run heatmap</h3>
        <p data-i18n="heatmapBody">Rows are tests and columns are recent runs. Alternating outcomes expose flakiness; a red block on the right suggests a regression; a red column suggests one bad run or environment event.</p>
        <ul class="check-list">
          <li data-i18n="heatmap1">Click a cell to open that exact run.</li>
          <li data-i18n="heatmap2">Click a test name to open its history.</li>
          <li data-i18n="heatmap3">Use the legend to focus outcomes; empty dashed cells mean the test did not run.</li>
          <li data-i18n="heatmap4">Hover an AI-analysed failure to see its category without opening the run.</li>
        </ul>
      </section>

      <section class="doc-section" id="failures">
        <p class="section-kicker" data-i18n="s7Kicker">08 · Priorities</p>
        <h2 data-i18n="s7Title">Triage failures and performance</h2>
        <h3 data-i18n="clustersTitle">Failure clusters</h3>
        <p data-i18n="clustersBody">The Failures KPI shows current breakage: failed and errored tests from each DAG·task's latest run. Similar error messages are normalized into clusters, largest first, so one root cause does not look like dozens of unrelated failures.</p>
        <h3 data-i18n="uniqueTitle">Unique-test catalogue</h3>
        <p data-i18n="uniqueBody">Search all distinct tests and compare their run count, pass/fail/error/skip totals, and average duration. Use it when you know the test name but not the run where it failed.</p>
        <h3 data-i18n="slowTitle">Slowdowns and slowest tests</h3>
        <p data-i18n="slowBody">Slowdowns compare recent average duration with the older half and ignore tiny timing noise. The same view also lists the slowest tests by average time. A recovered test automatically leaves the slowdown list.</p>
      </section>

      <section class="doc-section" id="ai-triage">
        <p class="section-kicker" data-i18n="s8Kicker">09 · Extra signals</p>
        <h2 data-i18n="s8Title">Use coverage and AI triage</h2>
        <h3 data-i18n="coverageTitle">Coverage</h3>
        <p data-i18n="coverageBody">When a run includes coverage data, its card shows line coverage and the configured target. Green means the target was met; red means it was missed. Coverage is presentational and never changes the run's pass/fail result.</p>
        <h3 data-i18n="triageTitle">AI triage</h3>
        <p data-i18n="triageBody">For analysed failures, the report puts a diagnosis before the traceback: category, hypothesis, suggested fix, confidence, and a command that reruns only that test.</p>
        <p data-i18n-html="triageEnable">Triage is switched on where the tests run, not in the viewer: install <code>airflow-pytest-plugin[triage-anthropic]</code> on the workers and pass the options to the parser. With <code>triage=True</code> alone there are no model calls — the run still archives an exception type and a rerun command for every failure. Naming a provider adds the AI verdicts.</p>
        <div class="example">
          <div class="example-label" data-i18n="triageConfigLabel">Worker-side configuration</div>
          <pre data-i18n="triageConfigCode">ArchivingResultParser(
    triage=True,
    triage_provider="anthropic",  # omit for the report only
    triage_budget=20,             # max model calls per run
    triage_timeout=45,            # seconds per call
)</pre>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th data-i18n="category">Category</th><th data-i18n="meaning">Meaning</th></tr></thead>
            <tbody>
              <tr><td><code>regression</code></td><td data-i18n="catRegression">Product code probably broke.</td></tr>
              <tr><td><code>flaky</code></td><td data-i18n="catFlaky">The test changes outcome without a stable code change.</td></tr>
              <tr><td><code>environment</code></td><td data-i18n="catEnvironment">Network, service, test data, or runtime environment caused the failure.</td></tr>
              <tr><td><code>test bug</code></td><td data-i18n="catTestBug">The expectation, fixture, or test code itself is likely wrong.</td></tr>
              <tr><td><code>unclear</code></td><td data-i18n="catUnclear">There was not enough evidence for a reliable category.</td></tr>
            </tbody>
          </table>
        </div>
        <div class="example">
          <div class="example-label" data-i18n="rerunExample">Ready-to-copy rerun</div>
          <pre>pytest tests/payments/test_refund.py::test_partial_refund</pre>
        </div>
        <h3 data-i18n="markTitle">The mark in the run list</h3>
        <p data-i18n="markBody">Runs that carried a triage pass are marked in the list, so you can tell what a run holds before opening it. Hover the mark for details; the model name appears only when there are verdicts to attribute.</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th data-i18n="markColour">Mark</th><th data-i18n="meaning">Meaning</th></tr></thead>
            <tbody>
              <tr><td data-i18n="markBlue">Blue</td><td data-i18n-html="markBlueBody">The model judged the failures. The tooltip names it, for example <code>claude-sonnet-5</code>.</td></tr>
              <tr><td data-i18n="markRed">Red</td><td data-i18n="markRedBody">The triage pass itself broke — a rejected key, a timeout, or an unreachable provider. The run shows the provider's own message.</td></tr>
              <tr><td data-i18n="markGrey">Grey</td><td data-i18n="markGreyBody">Failure report only: no provider was configured, so failures are listed without verdicts.</td></tr>
            </tbody>
          </table>
        </div>
        <h3 data-i18n="triageFilterTitle">Work through the failures</h3>
        <p data-i18n="triageFilterBody">Inside a run, the triage card counts how many failures were judged and shows the category mix as one bar. Click a category to keep only those failures in the case table; the other colours dim so the bar keeps showing the proportion. Click it again to clear the filter.</p>
        <p data-i18n-html="triageCostBody"><strong>What a run costs.</strong> One model call per failing test, so a wide breakage is the expensive case — that is what <code>triage_budget</code> caps. A retry analyses the same failures again and pays again, which is why a comparison across tries shows independent verdicts. Passing tests are never sent.</p>
        <div class="callout"><p data-i18n-html="triageNote"><strong>Treat verdicts as guidance.</strong> If the provider times out, rejects a key, or reaches its budget, the run says that triage is incomplete instead of inventing verdicts. A green run makes no model calls.</p></div>
        <h3 data-i18n="assistantTitle">Ask the report history</h3>
        <p data-i18n="assistantBody">When an administrator enables report chat on the API server, the AI assistant button opens a centered, resizable window and answers questions about selected runs or the current dashboard filters. Its size is remembered per Airflow user. The scope shows the selected count and opens the full run list before a question is sent. Replies render safe Markdown, including tables that scroll inside the answer, source buttons open the exact reports used for the answer, and the same DAG read permissions are checked again for every question. The Context overview button shows the exact RBAC-filtered report-evidence block sent to the final provider, without the system prompt or chat history. Exact input, output and total token usage appears after an answer when the provider returns it. The header sums provider-reported total tokens across the whole chat session; refresh preserves the total and Clear chat resets it.</p>
        <div class="example">
          <div class="example-label" data-i18n="assistantConfigLabel">Install on the API server</div>
          <pre data-i18n="assistantConfigCode">pip install 'airflow-pytest-plugin[assistant-anthropic,assistant-local]'
mkdir -p /models
curl -fL 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf?download=true' -o /models/qwen2.5-0.5b-instruct-q4_k_m.gguf
export AIRFLOW_PYTEST_ASSISTANT_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
export AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL=/models/qwen2.5-0.5b-instruct-q4_k_m.gguf
export AIRFLOW_PYTEST_ASSISTANT_CONTEXT_BYTES=49152
export AIRFLOW_PYTEST_ASSISTANT_DIRECT_MAX_SUMMARIES=100
export AIRFLOW_PYTEST_ASSISTANT_TRACEBACK_BYTES=3072
export AIRFLOW_PYTEST_ASSISTANT_CAPTURE_BYTES=2048
export AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS=3072</pre>
        </div>
        <p data-i18n="assistantInstall">The assistant-local extra installs the llama.cpp runtime only; it does not bundle a model. The setting must point to a readable .gguf file, not a URL or directory. In Docker or Kubernetes, bake that file into the API-server image or mount /models read-only, then restart every API-server process. Workers and schedulers do not need the model.</p>
        <p data-i18n-html="assistantLimits"><strong>The chat shows the effective server values.</strong> Open <strong>Limits</strong> to see them as a vertical list. <code>CONTEXT_BYTES</code> is one shared report-evidence budget for every report in a direct-mode request, not a per-report allowance. Summary records are written first and keep the aggregate success counters; 100 summaries is a ceiling, so the byte budget can still omit the oldest summaries. Failure records are appended only whole. If the newest-first snapshot exceeds the budget, the answer is marked as context-limited and the request still completes. Chat history has its own 16,000-byte cap: it does not consume report evidence, but it is part of the final provider input and token usage. The final answer defaults to 3,072 output tokens; if the provider reaches that limit, the chat preserves the partial response and visibly warns that it may be incomplete. The API server reads the variables above at startup and publishes the resolved values through <code>GET /api/assistant/status</code>; the browser does not own a second configuration. In Docker Compose, put them under <code>environment</code> on the Airflow API-server service. All displayed data sizes use <code>KiB</code>, where <code>1 KiB = 1024 bytes</code>. Tunable data limits are bounded to safe ranges; invalid values fall back to defaults. Local chunks can be smaller than <code>CONTEXT_BYTES</code> so they fit <code>CONTEXT_N_CTX</code>.</p>
        <div class="callout"><p data-i18n-html="assistantPrivacy"><strong>Know what leaves the server.</strong> A remote provider receives redacted report evidence, which can include failure tracebacks and a bounded part of captured stdout/stderr/log. With a local model, every readable run and test case is processed in chunks and hierarchically reduced; without one, a bounded direct snapshot is used. The local model costs API-server resources and does not replace the final provider. The current tab restores its user-separated chat after refresh and clears it when the tab closes or Clear chat is clicked.</p></div>
      </section>

      <section class="doc-section" id="email">
        <p class="section-kicker" data-i18n="s9Kicker">10 · Share and notify</p>
        <h2 data-i18n="s9Title">Export and share results</h2>
        <h3 data-i18n="allureTitle">Allure results</h3>
        <p data-i18n="allureBody">If raw Allure data was archived with the run, the Allure results button downloads it as a ZIP for import into Allure TestOps or another compatible workflow. The button is hidden when the run has no Allure data.</p>
        <h3 data-i18n="emailTitle">Email one run</h3>
        <p data-i18n="emailBody">When mail is available, open a run and click Email. Enter recipients or leave the field empty to use the team's configured list. Addresses are validated before sending.</p>
        <h3 data-i18n="alertsTitle">Automatic notifications</h3>
        <p data-i18n="alertsBody">A suite may be configured to email every result, or only failed and flaky runs. Messages are styled by outcome and link back to the run. Delivery failures never change the pytest task result.</p>
        <div class="callout"><p data-i18n-html="emailDomains"><strong>Recipients are bounded by the server, not by the form.</strong> Anyone who may read a run can email it anywhere unless an administrator lists the allowed domains in <code>AIRFLOW_PYTEST_ALERTS_EMAIL_DOMAINS</code>; an address outside them is refused instead of quietly dropped.</p></div>
        <p data-i18n="emailLog">The Emails badge in the run toolbar opens the latest delivery attempts — recipients, time, automatic or manual source, and delivered/failed status.</p>
      </section>

      <section class="doc-section" id="access">
        <p class="section-kicker" data-i18n="s10Kicker">11 · Personal view and permissions</p>
        <h2 data-i18n="s10Title">Settings, language, and access</h2>
        <h3 data-i18n="settingsTitle">Dashboard settings</h3>
        <p data-i18n="settingsBody">The gear button lets you hide Recent runs, Reliability, or Flaky tests. The run list always remains. These choices stay in this browser only and do not affect teammates or server data.</p>
        <h3 data-i18n="languageTitle">Language and theme</h3>
        <p data-i18n="languageBody">The viewer and this guide follow Airflow's selected Russian or English language and its light or dark theme. There is intentionally no separate plugin language switch.</p>
        <h3 data-i18n="permissionsTitle">Permissions</h3>
        <ul class="check-list">
          <li data-i18n="permission1">You see only reports for DAGs you are allowed to read.</li>
          <li data-i18n="permission2">Opening, comparing, exporting, and emailing a visible run require read access to its DAG.</li>
          <li data-i18n="permission3">Deleting a report is permanent and requires permission to trigger that DAG.</li>
          <li data-i18n="permission4">This help page contains no report data and is available independently of DAG permissions.</li>
        </ul>

        <h3 data-i18n="rolesTitle">What your Airflow role lets you do here</h3>
        <p data-i18n-html="rolesIntro">The plugin adds no roles and no permission screen of its own. Every check asks Airflow the same question its own DAG pages ask — <em>may this user read this DAG, and may they trigger it?</em> — so whatever your team already granted per DAG decides what you see here. Two permissions cover everything:</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th data-i18n="rolesAction">In the plugin</th><th data-i18n="rolesNeeds">Needs on that DAG</th><th data-i18n="rolesRole">Typical Airflow role</th></tr></thead>
            <tbody>
              <tr><td data-i18n="rolesSee">See a run in the list, open it, read tests, output and AI verdicts</td><td data-i18n="rolesRead">read</td><td data-i18n="rolesViewer">Viewer and above</td></tr>
              <tr><td data-i18n="rolesCompare">Compare runs, flaky history, heatmap, coverage, failure clusters</td><td data-i18n="rolesRead">read</td><td data-i18n="rolesViewer">Viewer and above</td></tr>
              <tr><td data-i18n="rolesExport">Download Allure results, copy a link, email a run</td><td data-i18n="rolesRead">read</td><td data-i18n="rolesViewer">Viewer and above</td></tr>
              <tr><td data-i18n="rolesDelete">Delete a report — one, or a whole selection</td><td data-i18n="rolesTrigger">trigger (run the DAG)</td><td data-i18n="rolesUser">User / Op and above</td></tr>
              <tr><td data-i18n="rolesConfigure">Turn features on, set the report directory, schedule cleanup</td><td data-i18n="rolesDeploy">no plugin permission — it is DAG code and environment</td><td data-i18n="rolesAdmin">whoever deploys DAGs</td></tr>
            </tbody>
          </table>
        </div>
        <p data-i18n-html="rolesPerDag">Permissions are <strong>per DAG, not per plugin</strong>. Someone who may read two of twenty DAGs sees exactly those two suites — the list, the charts, the KPIs and the flaky panel are all built from what they may read, so the dashboard tells them nothing about the rest. Deleting is checked the same way for every run in a selection: a mixed batch removes only the DAGs you may trigger and reports the others as kept.</p>
        <div class="callout"><p data-i18n-html="rolesNote"><strong>Two things to know.</strong> The menu entry is visible to everyone who can sign in to Airflow — Airflow has no per-permission gate for plugin links — but a user with no readable DAG sees an empty list, and a direct link to someone else's run answers "not allowed". And if Airflow's permission system cannot be consulted at all, the plugin refuses <em>everyone</em> rather than guessing.</p></div>

        <p data-i18n="retentionBody">Administrators may configure automatic retention, so older reports can disappear. The newest run of every DAG·task is always kept by the built-in retention policy.</p>
      </section>

      <section class="doc-section" id="faq">
        <p class="section-kicker" data-i18n="s11Kicker">12 · Troubleshooting</p>
        <h2 data-i18n="s11Title">Frequently asked questions</h2>
        <div class="faq">
          <details><summary data-i18n="faqEmptyQ">Why is the page empty?</summary><p data-i18n="faqEmptyA">No archived runs match your access and filters yet. Clear the filters, run the PytestOperator task, then use Refresh. If other users can see it, ask for read access to the DAG.</p></details>
          <details><summary data-i18n="faqPassingQ">Why can a “passing run” contain failures?</summary><p data-i18n="faqPassingA">Passing runs use the configured pass-rate threshold, which defaults to 85%, not necessarily 100%. The report still shows every failed and errored test.</p></details>
          <details><summary data-i18n="faqCoverageQ">Why is there no Coverage card?</summary><p data-i18n="faqCoverageA">That run was archived without coverage data. The card is omitted rather than showing a misleading zero.</p></details>
          <details><summary data-i18n="faqTriageQ">Why do some failures have no AI verdict?</summary><p data-i18n="faqTriageA">Triage may be disabled, report-only, over budget, or incomplete because the provider failed. The traceback and rerun command remain available whenever a failure report exists.</p></details>
          <details><summary data-i18n="faqEmailQ">Why is the Email button missing?</summary><p data-i18n="faqEmailA">No mail transport is available to the plugin. Ask your Airflow administrator whether email notifications are configured.</p></details>
          <details><summary data-i18n="faqFreshQ">Why did a new run not appear immediately?</summary><p data-i18n="faqFreshA">The report index is briefly cached. Click Refresh; new runs normally appear within a few seconds.</p></details>
          <details><summary data-i18n="faqDeleteQ">Why can't I delete a report?</summary><p data-i18n="faqDeleteA">Deletion requires trigger permission for that DAG. This is stricter than viewing because deletion removes the archived files for everyone.</p></details>
        </div>
      </section>

      <section class="doc-section" id="whats-new">
        <p class="section-kicker" data-i18n="relKicker">13 · Release notes</p>
        <h2 data-i18n="relTitle">What changed, and when</h2>
        <p data-i18n-html="relIntro">This install runs <strong class="mono" id="rel-version">v__APX_VERSION__</strong>. Every release carries its own summary of what changed — new features, fixes and anything that needs attention on upgrade — so the release notes are the one place to look before or after an upgrade.</p>
        <div class="rel-links">
          <a id="rel-current-link" class="btn" href="https://github.com/IKrysanov/airflow-pytest-plugin/releases/tag/v__APX_VERSION__" target="_blank" rel="noopener noreferrer">
            <span class="btn-label" data-i18n="relThis">Notes for this version</span>
          </a>
          <a id="rel-all-link" class="btn" href="https://github.com/IKrysanov/airflow-pytest-plugin/releases" target="_blank" rel="noopener noreferrer">
            <span class="btn-label" data-i18n="relAll">All releases</span>
          </a>
        </div>
        <p data-i18n="relNote">If the notes for this version do not open, the release is not published yet — the list of all releases always works.</p>
      </section>
    </article>
  </div>
  <footer>
    <span data-i18n="footer">Pytest Reports · user documentation</span>
    ·
    <!-- The version of the plugin actually serving this page: the first thing anyone is
         asked for in a bug report, and the one thing a user cannot otherwise find in the
         UI. Selectable, so it can be copied into an issue. -->
    <span class="ver mono" id="help-version" data-i18n-al="pluginVersion">v__APX_VERSION__</span>
    ·
    <a id="footer-github-link" href="https://github.com/IKrysanov/airflow-pytest-plugin"
      target="_blank" rel="noopener noreferrer">GitHub</a>
  </footer>
</div>

<script>
(function () {
  var HELP_I18N = {
    en: {
      skip: "Skip to the guide", guide: "User guide", back: "Back to reports",
      apiDocs: "API docs",
      title: "Understand every test run at a glance",
      lede: "Find a run, see what broke, spot flaky or slow tests, and share the result — without leaving Airflow.",
      tagRuns: "Runs", tagFailures: "Failures", tagTrends: "Trends",
      tagTriage: "AI triage", tagSharing: "Sharing", contents: "On this page",
      guideTopics: "Guide topics", helpSections: "Help sections",
      navStart: "Getting started", navSetup: "Set up the plugin",
      navDashboard: "Dashboard", navFind: "Find a run",
      navDetails: "Run details", navFlaky: "Flaky tests & history",
      navCompare: "Compare & heatmap", navFailures: "Failures & performance",
      navTriage: "Coverage & AI triage", navShare: "Allure & email",
      navAccess: "Settings & access", navFaq: "FAQ", navRelease: "Release notes",
      relKicker: "13 · Release notes", relTitle: "What changed, and when",
      relIntro: "This install runs <strong class=\"mono\" id=\"rel-version\">v__APX_VERSION__</strong>. Every release carries its own summary of what changed — new features, fixes and anything that needs attention on upgrade — so the release notes are the one place to look before or after an upgrade.",
      relThis: "Notes for this version", relAll: "All releases",
      relNote: "If the notes for this version do not open, the release is not published yet — the list of all releases always works.",
      s1Kicker: "01 · First visit", s1Title: "Getting started",
      s1Intro: "Open <strong>Browse → Pytest</strong> in Airflow. The newest archived runs appear first. No separate sign-in or plugin language setting is needed.",
      s1Step1: "<strong>Start with the KPIs.</strong> They tell you how many runs and unique tests are visible, what is currently failing, and whether anything slowed down.",
      s1Step2: "<strong>Narrow the list.</strong> Filter by DAG, task, or run ID. The cards, chart, reliability score, and lists follow the same view.",
      s1Step3: "<strong>Open a run.</strong> Click its row to inspect individual tests, captured output, coverage, AI verdicts, and links back to Airflow.",
      s1Tip: "<strong>Tip:</strong> the tracking link in a PytestOperator task log opens the exact archived run, including its try number.",
      setupKicker: "02 · Airflow administrator", setupTitle: "Set up the plugin correctly",
      setupIntro: "This one-time checklist is for the person who operates Airflow. Application users can skip directly to the dashboard section.",
      setupStep1: "<strong>Install the same plugin version</strong> on the API server and every worker that runs pytest tasks.",
      setupStep2: "<strong>Choose one shared report directory.</strong> Mount it at the same path on workers and the API server, then set <code>AIRFLOW_PYTEST_REPORTS_ROOT</code> everywhere.",
      setupStep3: "<strong>Archive operator results.</strong> Pass <code>ArchivingResultParser()</code> to each PytestOperator that should appear in the viewer.",
      setupStep4: "<strong>Restart and verify.</strong> Restart the Airflow API server after installation, open Browse → Pytest, and confirm that health reports <code>ready: true</code>.",
      setupInstallLabel: "Install on API server and workers",
      setupSecurity: "<strong>Production hardening:</strong> if archived JUnit files may come from code you do not fully trust, install <code>airflow-pytest-plugin[secure-xml]</code> on the API server for hardened XML parsing.",
      setupRootLabel: "Shared report storage", setupDagLabel: "DAG configuration",
      setupTip: "<strong>No special cleanup mode is required.</strong> The archiving parser owns its report directory, so you do not need <code>cleanup=\"never\"</code>.",
      setupOptionalTitle: "Enable optional features deliberately",
      setupOptionalBody: "Coverage, Allure export, AI triage, email, retention, and Prometheus metrics are independent. Enable only the features your team will use, verify their buttons or cards on one test DAG, and keep secrets in Airflow connections or environment variables rather than DAG source.",
      paramsTitle: "Every parser option",
      paramsIntro: "Bare <code>ArchivingResultParser()</code> already archives the run and its captured output — everything below is optional. Options marked <em>worker-side</em> need their package installed where the tests run, or pytest stops on an unknown argument.",
      paramCol: "Option", paramDefault: "Default",
      pReportRoot: "Where runs are archived. Unset, it follows <code>AIRFLOW_PYTEST_REPORTS_ROOT</code> — set that once for the whole install instead of repeating a path in every DAG.",
      pLayout: "The directory scheme inside that root. Leave it alone unless you are migrating an existing archive; the viewer expects the default.",
      pLogs: "Archive what each test printed and logged. Off, the run keeps tracebacks only — for a suite whose logging would dwarf its report.",
      pLogsOnlyFail: "Keep that output for failed and errored tests alone — the passing and skipped majority writes most of the volume and none of the part anyone reads.",
      pAllure: "Archive raw Allure results beside the run and show a download button for TestOps. <em>Worker-side:</em> needs <code>allure-pytest</code>.",
      pCoverage: "Measure coverage and store it with the run, so the Coverage card survives even a failed run. <em>Worker-side:</em> needs <code>pytest-cov</code>.",
      pCoverageSource: "What to measure, as in <code>coverage_source=\"src\"</code>. Set it when the project already narrows coverage itself — otherwise measurement widens and the percentage silently changes.",
      pCoverageThreshold: "The bar this suite is judged against, 0 to 1. It only colours the card — it never fails a run. Unset, the server-wide default applies.",
      pTriage: "AI triage. Left unset it follows <code>triage_provider</code>. <code>True</code> alone archives a failure report with no model calls; <code>False</code> is an off switch and wins even when a provider is named. <em>Worker-side:</em> needs <code>pytest-triage</code>.",
      pTriageProvider: "Which model service judges the failures — <code>\"anthropic\"</code>, <code>\"openai\"</code>, <code>\"gigachat\"</code>, or <code>\"fake\"</code> for an offline dry run. Naming one turns triage on. Keys come from the environment; the plugin never stores them.",
      pTriageBudget: "Most model calls one run may make — the cost ceiling, since each failing test costs one call. Unset, the library's own default (10) applies.",
      pTriageTimeout: "Seconds one call may take before the run gives up on it and says the pass was incomplete.",
      pEmail: "Email the result after every run of this task. Needs a mail transport and recipients configured on the server.",
      pEmailOnlyFail: "Email only when the run failed or a test is flaky — the setting most teams want, so a green night stays quiet.",
      paramsCapture: "<strong>Captured output is archived verbatim.</strong> Whatever a test prints or logs is stored as the run produced it \u2014 the plugin does not mask secrets, so a test that prints a token archives that token. Keep credentials out of test output, or archive with <code>logs=False</code>; who can read it is decided by the same Airflow DAG permissions as the run itself.",
      paramsExampleLabel: "A fully equipped task",
      paramsExampleCode: "ArchivingResultParser(\n    logs_only_fail=True,\n    allure=True,\n    coverage=True,\n    coverage_source=\"src\",\n    triage_provider=\"anthropic\",\n    triage_budget=20,\n    email_only_fail=True,\n)",
      retentionTitle: "Delete old reports automatically",
      retentionIntro: "Reports are kept forever until someone prunes them: the plugin never deletes on its own. Turn on any of the limits below and schedule the cleanup from a maintenance DAG.",
      retNone: "unset",
      retAge: "Delete runs older than N days.",
      retRuns: "Keep only the N newest runs of each DAG·task.",
      retSize: "Keep the whole archive under N megabytes, deleting oldest first.",
      limReport: "Largest report the viewer will open. A run past it stays in the list with its real numbers, but opening it says so instead. Raise it if a suite really archives more; 0 removes the limit.",
      limMeta: "Largest run index a scan decodes whole (about a quarter-million tests). Past it a run still lists, opens and is cleaned up as usual; only its per-test data is read from the report instead.",
      retentionDagLabel: "Maintenance DAG",
      retentionRules: "Set as many limits as you like: a run goes if <strong>any</strong> of them says so. The <strong>newest run of every DAG·task is always kept</strong>, so a task's latest result never disappears no matter how tight the limits are. To see what a policy would remove before trusting it, call <code>prune_reports(dry_run=True)</code> — it deletes nothing and reports how many runs and bytes it would have freed.",
      setupAccessTitle: "Check access with two roles",
      setupAccessBody: "Test with a normal reader and an operator: the reader should see only permitted DAG reports, while deletion should remain available only to a role that can trigger the DAG.",
      s2Kicker: "03 · Overview", s2Title: "Read the dashboard",
      s2Intro: "The dashboard answers three questions: how much ran, how healthy it is now, and whether the direction is improving.",
      kpiRuns: "Runs & passing runs", kpiRunsBody: "All visible archived runs, and the number that cleared the configured pass-rate threshold.",
      kpiUnique: "Unique tests", kpiUniqueBody: "Distinct pytest node IDs across the visible history. Click for the searchable catalogue and per-test totals.",
      kpiFailures: "Failures", kpiFailuresBody: "Tests broken in the latest run of each DAG·task. A fixed test disappears after the next green run.",
      kpiSlow: "Slowdowns", kpiSlowBody: "Tests whose recent execution time is meaningfully worse than their older baseline.",
      chartTitle: "Recent runs chart",
      chartBody: "Each bar is one run, stacked by <strong>passed, failed, error, and skipped</strong>. Click the legend to focus statuses, drag or use the arrows for older runs, and tick list rows to chart only those runs. The optional pass-rate line includes the suite's success threshold.",
      reliabilityTitle: "Reliability",
      reliabilityBody: "The radar combines pass rate, absence of errors, current green DAG·tasks, stability, and completeness. The line below it shows run health over time; use the arrow to compare the recent half with the older half.",
      flakyPanelTitle: "Flaky panel",
      flakyPanelBody: "This is the quick watchlist for tests that switch between pass and fail. Search within it, show quarantined tests only, or click a row for the full history.",
      s3Kicker: "04 · Navigation", s3Title: "Find the run you need",
      find1: "<strong>DAG filter</strong> — isolate one pipeline, for example <code>payments_daily</code>.",
      find2: "<strong>Task filter</strong> — compare only the pytest task within that DAG.",
      find3: "<strong>Run filter</strong> — paste part of a scheduled or manual run ID.",
      find4: "<strong>Group by DAG·task</strong> — collapse a busy history into suites with run count, pass rate, average time, and latest status.",
      find5: "<strong>Sort and select</strong> — sort columns by clicking their labels; tick runs or a whole group to focus the charts and analytics.",
      example: "Example",
      findNote: "Filters are suggestions, not exact-match fields: a meaningful fragment is usually enough. Clear them with the × button in the header.",
      s4Kicker: "05 · Investigation", s4Title: "Investigate one run",
      s4Intro: "A run opens as a focused report while preserving the dashboard underneath. Its toolbar links back to the DAG, DAG run, and task instance in Airflow.",
      detailArea: "Area", detailUse: "How to use it", detailSummary: "Summary & donut",
      detailSummaryBody: "Check totals and pass rate. Click a donut slice to filter the case table by outcome.",
      detailDuration: "Duration histogram", detailDurationBody: "See whether time is spread evenly or dominated by a few long-running tests.",
      detailCases: "Case table", detailCasesBody: "Search by node ID, group by module, sort by test or duration, and expand a row for its failure and captured output.",
      detailTry: "Try number", detailTryBody: "Retries stay separate. Compare tries when the same task changes outcome or diagnosis.",
      detailLink: "Copy link", detailLinkBody: "Share a deep link to this exact DAG, run, task, and try. The recipient still needs Airflow access.",
      s4Tip: "<strong>Fast path:</strong> sort the case table by time to surface the slowest tests first, or click a status to isolate only failures and errors.",
      s5Kicker: "06 · Stability", s5Title: "Understand flaky tests and history",
      s5Intro: "A test is flaky when it both passes and fails within the recent window for the same DAG·task. The same node ID in another task is evaluated separately.",
      scoreTitle: "Flakiness score", scoreBody: "How often the result flips between pass and fail. Higher means less predictable.",
      trendTitle: "Trend", trendBody: "Compares the recent half of the window with the older half: getting worse, calming down, or steady.",
      quarantineTitle: "Quarantine", quarantineBody: "A visible badge once the score crosses the configured quarantine threshold. It is a signal, not an automatic pytest action.",
      historyCardTitle: "Test history", historyCardBody: "A run-by-run strip of outcomes. “Did not run” stays distinct from skipped, failed, and passed.",
      flakyAction: "Open Flaky tests from a group or run, choose the analysis window, and click a test to see exactly when it started changing.",
      s6Kicker: "07 · Change over time", s6Title: "Compare runs and scan the heatmap",
      compareTitle: "Compare to previous",
      compareBody: "From a run, choose <strong>Compare to previous</strong> to classify every test as newly failed, fixed, still failing, added, or removed. This is the fastest answer to “what changed in this build?”",
      heatmapTitle: "Test × run heatmap",
      heatmapBody: "Rows are tests and columns are recent runs. Alternating outcomes expose flakiness; a red block on the right suggests a regression; a red column suggests one bad run or environment event.",
      heatmap1: "Click a cell to open that exact run.", heatmap2: "Click a test name to open its history.",
      heatmap3: "Use the legend to focus outcomes; empty dashed cells mean the test did not run.",
      heatmap4: "Hover an AI-analysed failure to see its category without opening the run.",
      s7Kicker: "08 · Priorities", s7Title: "Triage failures and performance",
      clustersTitle: "Failure clusters",
      clustersBody: "The Failures KPI shows current breakage: failed and errored tests from each DAG·task's latest run. Similar error messages are normalized into clusters, largest first, so one root cause does not look like dozens of unrelated failures.",
      uniqueTitle: "Unique-test catalogue",
      uniqueBody: "Search all distinct tests and compare their run count, pass/fail/error/skip totals, and average duration. Use it when you know the test name but not the run where it failed.",
      slowTitle: "Slowdowns and slowest tests",
      slowBody: "Slowdowns compare recent average duration with the older half and ignore tiny timing noise. The same view also lists the slowest tests by average time. A recovered test automatically leaves the slowdown list.",
      s8Kicker: "09 · Extra signals", s8Title: "Use coverage and AI helpers",
      coverageTitle: "Coverage",
      coverageBody: "When a run includes coverage data, its card shows line coverage and the configured target. Green means the target was met; red means it was missed. Coverage is presentational and never changes the run's pass/fail result.",
      triageTitle: "AI triage",
      triageBody: "For analysed failures, the report puts a diagnosis before the traceback: category, hypothesis, suggested fix, confidence, and a command that reruns only that test.",
      triageEnable: "Triage is switched on where the tests run, not in the viewer: install <code>airflow-pytest-plugin[triage-anthropic]</code> on the workers and pass the options to the parser. With <code>triage=True</code> alone there are no model calls — the run still archives an exception type and a rerun command for every failure. Naming a provider adds the AI verdicts.",
      triageConfigLabel: "Worker-side configuration",
      triageConfigCode: "ArchivingResultParser(\n    triage=True,\n    triage_provider=\"anthropic\",  # omit for the report only\n    triage_budget=20,             # max model calls per run\n    triage_timeout=45,            # seconds per call\n)",
      markTitle: "The mark in the run list",
      markBody: "Runs that carried a triage pass are marked in the list, so you can tell what a run holds before opening it. Hover the mark for details; the model name appears only when there are verdicts to attribute.",
      markColour: "Mark",
      markBlue: "Blue",
      markBlueBody: "The model judged the failures. The tooltip names it, for example <code>claude-sonnet-5</code>.",
      markRed: "Red",
      markRedBody: "The triage pass itself broke — a rejected key, a timeout, or an unreachable provider. The run shows the provider's own message.",
      markGrey: "Grey",
      markGreyBody: "Failure report only: no provider was configured, so failures are listed without verdicts.",
      triageFilterTitle: "Work through the failures",
      triageFilterBody: "Inside a run, the triage card counts how many failures were judged and shows the category mix as one bar. Click a category to keep only those failures in the case table; the other colours dim so the bar keeps showing the proportion. Click it again to clear the filter.",
      triageCostBody: "<strong>What a run costs.</strong> One model call per failing test, so a wide breakage is the expensive case — that is what <code>triage_budget</code> caps. A retry analyses the same failures again and pays again, which is why a comparison across tries shows independent verdicts. Passing tests are never sent.",
      category: "Category", meaning: "Meaning", catRegression: "Product code probably broke.",
      catFlaky: "The test changes outcome without a stable code change.",
      catEnvironment: "Network, service, test data, or runtime environment caused the failure.",
      catTestBug: "The expectation, fixture, or test code itself is likely wrong.",
      catUnclear: "There was not enough evidence for a reliable category.",
      rerunExample: "Ready-to-copy rerun",
      triageNote: "<strong>Treat verdicts as guidance.</strong> If the provider times out, rejects a key, or reaches its budget, the run says that triage is incomplete instead of inventing verdicts. A green run makes no model calls.",
      assistantTitle: "Ask the report history",
      assistantBody: "When an administrator enables report chat on the API server, the AI assistant button opens a centered, resizable window and answers questions about selected runs or the current dashboard filters. Its size is remembered per Airflow user. Before a question is sent, the scope shows the selected count, opens the full run list, and explains how many RBAC-readable reports will be handled in local full-tree or direct bounded mode. Replies render safe Markdown, can be copied as their original Markdown, and show the UTF-8 bytes sent as system, user, report context, history and prompt structure. Context overview shows the exact RBAC-filtered report-evidence block sent to the final provider, without the system prompt or history. Exact input, output and total token usage appears after an answer when the provider returns it. The header sums provider-reported total tokens across the whole chat session; refresh preserves the total and Clear chat resets it. Source buttons open the exact reports used for the answer, and the same DAG read permissions are checked again for every question.",
      assistantConfigLabel: "Install on the API server",
      assistantConfigCode: "pip install 'airflow-pytest-plugin[assistant-anthropic,assistant-local]'\nmkdir -p /models\ncurl -fL 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf?download=true' -o /models/qwen2.5-0.5b-instruct-q4_k_m.gguf\nexport AIRFLOW_PYTEST_ASSISTANT_PROVIDER=anthropic\nexport ANTHROPIC_API_KEY=...\nexport AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL=/models/qwen2.5-0.5b-instruct-q4_k_m.gguf\nexport AIRFLOW_PYTEST_ASSISTANT_CONTEXT_BYTES=49152\nexport AIRFLOW_PYTEST_ASSISTANT_DIRECT_MAX_SUMMARIES=100\nexport AIRFLOW_PYTEST_ASSISTANT_TRACEBACK_BYTES=3072\nexport AIRFLOW_PYTEST_ASSISTANT_CAPTURE_BYTES=2048\nexport AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS=3072",
      assistantInstall: "The assistant-local extra installs the llama.cpp runtime only; it does not bundle a model. The setting must point to a readable .gguf file, not a URL or directory. In Docker or Kubernetes, bake that file into the API-server image or mount /models read-only, then restart every API-server process. Workers and schedulers do not need the model.",
      assistantLimits: "<strong>The chat shows the effective server values.</strong> Open <strong>Limits</strong> to see them as a vertical list. <code>CONTEXT_BYTES</code> is one shared report-evidence budget for every report in a direct-mode request, not a per-report allowance. Summary records are written first and keep the aggregate success counters; 100 summaries is a ceiling, so the byte budget can still omit the oldest summaries. Failure records are appended only whole. If the newest-first snapshot exceeds the budget, the answer is marked as context-limited and the request still completes. Chat history has its own 16,000-byte cap: it does not consume report evidence, but it is part of the final provider input and token usage. The final answer defaults to 3,072 output tokens; if the provider reaches that limit, the chat preserves the partial response and visibly warns that it may be incomplete. The API server reads the variables above at startup and publishes the resolved values through <code>GET /api/assistant/status</code>; the browser does not own a second configuration. In Docker Compose, put them under <code>environment</code> on the Airflow API-server service. All displayed data sizes use <code>KiB</code>, where <code>1 KiB = 1024 bytes</code>. Tunable data limits are bounded to safe ranges; invalid values fall back to defaults. Local chunks can be smaller than <code>CONTEXT_BYTES</code> so they fit <code>CONTEXT_N_CTX</code>.",
      assistantPrivacy: "<strong>Know what leaves the server.</strong> A remote provider receives redacted report evidence, which can include failure tracebacks and a bounded part of captured stdout/stderr/log. With a local model, every readable run and test case is processed in chunks and hierarchically reduced; without one, a bounded direct snapshot is used. The local model costs API-server resources and does not replace the final provider. The current tab restores its user-separated chat after refresh and clears it when the tab closes or Clear chat is clicked.",
      s9Kicker: "10 · Share and notify", s9Title: "Export and share results",
      allureTitle: "Allure results",
      allureBody: "If raw Allure data was archived with the run, the Allure results button downloads it as a ZIP for import into Allure TestOps or another compatible workflow. The button is hidden when the run has no Allure data.",
      emailTitle: "Email one run",
      emailBody: "When mail is available, open a run and click Email. Enter recipients or leave the field empty to use the team's configured list. Addresses are validated before sending.",
      alertsTitle: "Automatic notifications",
      alertsBody: "A suite may be configured to email every result, or only failed and flaky runs. Messages are styled by outcome and link back to the run. Delivery failures never change the pytest task result.",
      emailDomains: "<strong>Recipients are bounded by the server, not by the form.</strong> Anyone who may read a run can email it anywhere unless an administrator lists the allowed domains in <code>AIRFLOW_PYTEST_ALERTS_EMAIL_DOMAINS</code>; an address outside them is refused instead of quietly dropped.",
      emailLog: "The Emails badge in the run toolbar opens the latest delivery attempts — recipients, time, automatic or manual source, and delivered/failed status.",
      s10Kicker: "11 · Personal view and permissions", s10Title: "Settings, language, and access",
      settingsTitle: "Dashboard settings",
      settingsBody: "The gear button lets you hide Recent runs, Reliability, or Flaky tests. The run list always remains. These choices stay in this browser only and do not affect teammates or server data.",
      languageTitle: "Language and theme",
      languageBody: "The viewer and this guide follow Airflow's selected Russian or English language and its light or dark theme. There is intentionally no separate plugin language switch.",
      rolesTitle: "What your Airflow role lets you do here",
      rolesIntro: "The plugin adds no roles and no permission screen of its own. Every check asks Airflow the same question its own DAG pages ask — <em>may this user read this DAG, and may they trigger it?</em> — so whatever your team already granted per DAG decides what you see here. Two permissions cover everything:",
      rolesAction: "In the plugin", rolesNeeds: "Needs on that DAG", rolesRole: "Typical Airflow role",
      rolesSee: "See a run in the list, open it, read tests, output and AI verdicts",
      rolesCompare: "Compare runs, flaky history, heatmap, coverage, failure clusters",
      rolesExport: "Download Allure results, copy a link, email a run",
      rolesDelete: "Delete a report — one, or a whole selection",
      rolesConfigure: "Turn features on, set the report directory, schedule cleanup",
      rolesRead: "read", rolesTrigger: "trigger (run the DAG)",
      rolesDeploy: "no plugin permission — it is DAG code and environment",
      rolesViewer: "Viewer and above", rolesUser: "User / Op and above",
      rolesAdmin: "whoever deploys DAGs",
      rolesPerDag: "Permissions are <strong>per DAG, not per plugin</strong>. Someone who may read two of twenty DAGs sees exactly those two suites — the list, the charts, the KPIs and the flaky panel are all built from what they may read, so the dashboard tells them nothing about the rest. Deleting is checked the same way for every run in a selection: a mixed batch removes only the DAGs you may trigger and reports the others as kept.",
      rolesNote: "<strong>Two things to know.</strong> The menu entry is visible to everyone who can sign in to Airflow — Airflow has no per-permission gate for plugin links — but a user with no readable DAG sees an empty list, and a direct link to someone else's run answers \"not allowed\". And if Airflow's permission system cannot be consulted at all, the plugin refuses <em>everyone</em> rather than guessing.",
      permissionsTitle: "Permissions",
      permission1: "You see only reports for DAGs you are allowed to read.",
      permission2: "Opening, comparing, exporting, and emailing a visible run require read access to its DAG.",
      permission3: "Deleting a report is permanent and requires permission to trigger that DAG.",
      permission4: "This help page contains no report data and is available independently of DAG permissions.",
      retentionBody: "Administrators may configure automatic retention, so older reports can disappear. The newest run of every DAG·task is always kept by the built-in retention policy.",
      s11Kicker: "12 · Troubleshooting", s11Title: "Frequently asked questions",
      faqEmptyQ: "Why is the page empty?", faqEmptyA: "No archived runs match your access and filters yet. Clear the filters, run the PytestOperator task, then use Refresh. If other users can see it, ask for read access to the DAG.",
      faqPassingQ: "Why can a “passing run” contain failures?", faqPassingA: "Passing runs use the configured pass-rate threshold, which defaults to 85%, not necessarily 100%. The report still shows every failed and errored test.",
      faqCoverageQ: "Why is there no Coverage card?", faqCoverageA: "That run was archived without coverage data. The card is omitted rather than showing a misleading zero.",
      faqTriageQ: "Why do some failures have no AI verdict?", faqTriageA: "Triage may be disabled, report-only, over budget, or incomplete because the provider failed. The traceback and rerun command remain available whenever a failure report exists.",
      faqEmailQ: "Why is the Email button missing?", faqEmailA: "No mail transport is available to the plugin. Ask your Airflow administrator whether email notifications are configured.",
      faqFreshQ: "Why did a new run not appear immediately?", faqFreshA: "The report index is briefly cached. Click Refresh; new runs normally appear within a few seconds.",
      faqDeleteQ: "Why can't I delete a report?", faqDeleteA: "Deletion requires trigger permission for that DAG. This is stricter than viewing because deletion removes the archived files for everyone.",
      footer: "Pytest Reports · user documentation",
      pluginVersion: "Installed plugin version"
    },
    ru: {
      skip: "Перейти к справке", guide: "Руководство пользователя", back: "К отчётам",
      apiDocs: "Документация API",
      title: "Разберитесь в любом прогоне с первого взгляда",
      lede: "Найдите прогон, поймите причину сбоя, заметите нестабильные и медленные тесты и поделитесь результатом — не выходя из Airflow.",
      tagRuns: "Прогоны", tagFailures: "Сбои", tagTrends: "Тренды",
      tagTriage: "AI-разбор", tagSharing: "Совместная работа", contents: "На этой странице",
      guideTopics: "Темы руководства", helpSections: "Разделы справки",
      navStart: "С чего начать", navSetup: "Настройка плагина",
      navDashboard: "Дашборд", navFind: "Как найти прогон",
      navDetails: "Детали прогона", navFlaky: "Нестабильность и история",
      navCompare: "Сравнение и тепловая карта", navFailures: "Сбои и скорость",
      navTriage: "Покрытие и AI-разбор", navShare: "Allure и почта",
      navAccess: "Настройки и доступ", navFaq: "Частые вопросы", navRelease: "История изменений",
      relKicker: "13 · История изменений", relTitle: "Что изменилось и когда",
      relIntro: "Установлена версия <strong class=\"mono\" id=\"rel-version\">v__APX_VERSION__</strong>. У каждого релиза своё описание изменений — что появилось, что исправлено и на что обратить внимание при обновлении. Это и есть то единственное место, куда стоит заглянуть до или после обновления.",
      relThis: "Заметки к этой версии", relAll: "Все релизы",
      relNote: "Если заметки к этой версии не открываются, релиз ещё не опубликован — список всех релизов работает всегда.",
      s1Kicker: "01 · Первый визит", s1Title: "С чего начать",
      s1Intro: "Откройте в Airflow <strong>Обзор → Pytest</strong>. Сначала показаны самые новые архивные прогоны. Отдельный вход или настройка языка плагина не нужны.",
      s1Step1: "<strong>Начните с показателей.</strong> Они покажут число прогонов и уникальных тестов, текущие сбои и замедления.",
      s1Step2: "<strong>Сузьте список.</strong> Отфильтруйте по DAG, задаче или ID запуска. Карточки, график, надёжность и списки следуют выбранному срезу.",
      s1Step3: "<strong>Откройте прогон.</strong> Нажмите строку, чтобы увидеть отдельные тесты, сохранённый вывод, покрытие, AI-вердикты и ссылки обратно в Airflow.",
      s1Tip: "<strong>Подсказка:</strong> ссылка в логе задачи PytestOperator сразу открывает нужный архивный прогон с учётом номера попытки.",
      setupKicker: "02 · Администратор Airflow", setupTitle: "Правильно настройте плагин",
      setupIntro: "Это одноразовая проверка для человека, который обслуживает Airflow. Пользователи могут сразу перейти к разделу о дашборде.",
      setupStep1: "<strong>Установите одну версию плагина</strong> на API-сервер и на каждый worker, где выполняются pytest-задачи.",
      setupStep2: "<strong>Выберите общий каталог отчётов.</strong> Подключите его по одному пути на workers и API-сервере, затем везде задайте <code>AIRFLOW_PYTEST_REPORTS_ROOT</code>.",
      setupStep3: "<strong>Архивируйте результаты оператора.</strong> Передайте <code>ArchivingResultParser()</code> каждому PytestOperator, который должен появляться во вьюере.",
      setupStep4: "<strong>Перезапустите и проверьте.</strong> После установки перезапустите API-сервер Airflow, откройте Обзор → Pytest и убедитесь, что health возвращает <code>ready: true</code>.",
      setupInstallLabel: "Установка на API-сервере и workers",
      setupSecurity: "<strong>Защита production:</strong> если архивные JUnit-файлы могут приходить из кода, которому вы доверяете не полностью, установите <code>airflow-pytest-plugin[secure-xml]</code> на API-сервере для усиленного разбора XML.",
      setupRootLabel: "Общее хранилище отчётов", setupDagLabel: "Настройка DAG",
      setupTip: "<strong>Особый режим очистки не нужен.</strong> Каталогом отчёта владеет архивирующий парсер, поэтому <code>cleanup=\"never\"</code> не требуется.",
      setupOptionalTitle: "Включайте дополнительные возможности осознанно",
      setupOptionalBody: "Покрытие, экспорт Allure, AI-разбор, почта, хранение и метрики Prometheus независимы. Включайте только нужное команде, проверяйте карточки и кнопки на одном тестовом DAG, а секреты храните в подключениях Airflow или переменных среды, а не в коде DAG.",
      paramsTitle: "Все параметры парсера",
      paramsIntro: "Голый <code>ArchivingResultParser()</code> уже сохраняет прогон и вывод тестов — всё остальное необязательно. Параметры с пометкой <em>на воркере</em> требуют установленного пакета там, где идут тесты, иначе pytest остановится на незнакомом аргументе.",
      paramCol: "Параметр", paramDefault: "По умолчанию",
      pReportRoot: "Куда складывать прогоны. Если не задан, берётся <code>AIRFLOW_PYTEST_REPORTS_ROOT</code> — задайте его один раз на всю установку, а не путь в каждом DAG.",
      pLayout: "Схема каталогов внутри этого корня. Не трогайте без переезда существующего архива: просмотрщик рассчитывает на схему по умолчанию.",
      pLogs: "Сохранять то, что тест печатал и логировал. Выключено — в прогоне останутся только трассировки; для набора, чьи логи перевесят сам отчёт.",
      pLogsOnlyFail: "Оставлять вывод только у упавших и сломавшихся тестов — прошедшие и пропущенные дают основной объём и ровно ту часть, которую никто не читает.",
      pAllure: "Складывать исходные результаты Allure рядом с прогоном и показывать кнопку выгрузки в TestOps. <em>На воркере:</em> нужен <code>allure-pytest</code>.",
      pCoverage: "Мерить покрытие и хранить его вместе с прогоном — карточка покрытия переживает даже упавший прогон. <em>На воркере:</em> нужен <code>pytest-cov</code>.",
      pCoverageSource: "Что мерить, например <code>coverage_source=\"src\"</code>. Указывайте, если проект уже сужает покрытие сам: иначе область расширится, а процент незаметно изменится.",
      pCoverageThreshold: "Планка для этого набора, от 0 до 1. Влияет только на цвет карточки и никогда не заваливает прогон. Не задана — действует общесерверное значение.",
      pTriage: "ИИ-разбор падений. Не задан — следует за <code>triage_provider</code>. <code>True</code> без провайдера сохраняет отчёт о падениях без обращений к модели; <code>False</code> — выключатель, он побеждает даже при указанном провайдере. <em>На воркере:</em> нужен <code>pytest-triage</code>.",
      pTriageProvider: "Какой сервис моделей разбирает падения — <code>\"anthropic\"</code>, <code>\"openai\"</code>, <code>\"gigachat\"</code> или <code>\"fake\"</code> для офлайн-прогона. Указание провайдера включает разбор. Ключи берутся из окружения, плагин их не хранит.",
      pTriageBudget: "Предел вызовов модели за прогон — потолок расходов, поскольку каждый упавший тест стоит один вызов. Не задан — действует значение библиотеки (10).",
      pTriageTimeout: "Сколько секунд отводится одному вызову, прежде чем прогон откажется его ждать и сообщит, что разбор не завершён.",
      pEmail: "Отправлять письмо после каждого прогона этой задачи. Нужны настроенные на сервере транспорт почты и получатели.",
      pEmailOnlyFail: "Писать только при падении или нестабильности — то, что нужно большинству команд: зелёная ночь остаётся тихой.",
      paramsCapture: "<strong>Захват сохраняется буквально.</strong> Всё, что тест напечатал или залогировал, кладётся в архив в том же виде: плагин не маскирует секреты, и тест, печатающий токен, архивирует его. Не выводите учётные данные в тестах или архивируйте с <code>logs=False</code>; кому это видно, решают те же права на DAG в Airflow, что и для самого запуска.",
      paramsExampleLabel: "Задача со всеми возможностями",
      paramsExampleCode: "ArchivingResultParser(\n    logs_only_fail=True,\n    allure=True,\n    coverage=True,\n    coverage_source=\"src\",\n    triage_provider=\"anthropic\",\n    triage_budget=20,\n    email_only_fail=True,\n)",
      retentionTitle: "Автоматическая очистка старых отчётов",
      retentionIntro: "Отчёты хранятся вечно, пока их кто-нибудь не удалит: сам плагин ничего не стирает. Включите любые из ограничений ниже и поставьте очистку в обслуживающий DAG.",
      retNone: "не задано",
      retAge: "Удалять прогоны старше N дней.",
      retRuns: "Оставлять только N последних прогонов каждой пары DAG·задача.",
      retSize: "Держать весь архив в пределах N мегабайт, удаляя самые старые.",
      limReport: "Наибольший отчёт, который вьювер откроет. Прогон сверх предела остаётся в списке с настоящими числами, но при открытии сообщает об этом. Поднимите значение, если сюита действительно архивирует больше; 0 снимает предел.",
      limMeta: "Наибольший индекс прогона, который скан разбирает целиком (около четверти миллиона тестов). Сверх предела прогон так же виден, открывается и очищается; только построчные данные берутся из отчёта.",
      retentionDagLabel: "Обслуживающий DAG",
      retentionRules: "Ограничений можно включить сколько угодно: прогон удаляется, если сработало <strong>любое</strong>. <strong>Самый свежий прогон каждой пары DAG·задача сохраняется всегда</strong> — последний результат задачи не исчезнет, как бы жёстко ни были выставлены лимиты. Чтобы посмотреть, что политика удалит, до того как ей довериться, вызовите <code>prune_reports(dry_run=True)</code>: он ничего не удаляет и сообщает, сколько прогонов и байтов освободил бы.",
      setupAccessTitle: "Проверьте доступ под двумя ролями",
      setupAccessBody: "Проверьте обычного читателя и оператора: читатель должен видеть отчёты только разрешённых DAG, а удаление должно оставаться доступно лишь роли с правом запуска DAG.",
      s2Kicker: "03 · Обзор", s2Title: "Как читать дашборд",
      s2Intro: "Дашборд отвечает на три вопроса: сколько было запущено, насколько всё исправно сейчас и улучшается ли ситуация.",
      kpiRuns: "Прогоны и успешные", kpiRunsBody: "Все видимые архивные прогоны и те из них, что достигли настроенного порога прохождения.",
      kpiUnique: "Уникальные тесты", kpiUniqueBody: "Разные pytest node ID во всей видимой истории. Нажмите для поиска по каталогу и статистики каждого теста.",
      kpiFailures: "Сбои", kpiFailuresBody: "Тесты, сломанные в последнем прогоне каждой пары DAG·задача. После следующего успешного прогона исправленный тест исчезнет.",
      kpiSlow: "Замедления", kpiSlowBody: "Тесты, чьё недавнее время выполнения заметно ухудшилось относительно прежнего уровня.",
      chartTitle: "График последних прогонов",
      chartBody: "Каждый столбец — один прогон, разбитый на <strong>успешные, проваленные, ошибочные и пропущенные</strong> тесты. Нажимайте легенду для фильтра, перетаскивайте график или используйте стрелки для старых прогонов, отмечайте строки списка для выбранного среза. Дополнительная линия прохождения показывает порог успеха набора.",
      reliabilityTitle: "Надёжность",
      reliabilityBody: "Радар объединяет проходимость, отсутствие ошибок, долю зелёных DAG·задач сейчас, стабильность и полноту. Линия под ним показывает здоровье во времени, а стрелка сравнивает недавнюю половину с ранней.",
      flakyPanelTitle: "Панель нестабильных тестов",
      flakyPanelBody: "Это быстрый список тестов, которые меняют результат с успешного на провальный. Используйте поиск, оставьте только карантин или нажмите строку для полной истории.",
      s3Kicker: "04 · Навигация", s3Title: "Найдите нужный прогон",
      find1: "<strong>Фильтр DAG</strong> — оставьте один пайплайн, например <code>payments_daily</code>.",
      find2: "<strong>Фильтр задачи</strong> — сравнивайте только pytest-задачу внутри этого DAG.",
      find3: "<strong>Фильтр запуска</strong> — вставьте часть ID планового или ручного запуска.",
      find4: "<strong>Группировка по DAG·задаче</strong> — сверните длинную историю в наборы с числом прогонов, проходимостью, средним временем и последним статусом.",
      find5: "<strong>Сортировка и выбор</strong> — нажимайте названия колонок; отмечайте прогоны или целую группу, чтобы сфокусировать графики и аналитику.",
      example: "Пример",
      findNote: "Фильтры работают по фрагменту, поэтому обычно достаточно значимой части названия. Сбросьте их кнопкой × в шапке.",
      s4Kicker: "05 · Исследование", s4Title: "Разберите один прогон",
      s4Intro: "Прогон открывается как отдельный подробный отчёт поверх дашборда. В панели действий есть ссылки на DAG, запуск DAG и экземпляр задачи в Airflow.",
      detailArea: "Область", detailUse: "Как использовать", detailSummary: "Итоги и кольцевая диаграмма",
      detailSummaryBody: "Проверьте количества и долю прохождения. Нажмите сектор диаграммы, чтобы отфильтровать таблицу по результату.",
      detailDuration: "Гистограмма времени", detailDurationBody: "Посмотрите, распределено ли время равномерно или его забирают несколько долгих тестов.",
      detailCases: "Таблица тестов", detailCasesBody: "Ищите по node ID, группируйте по модулю, сортируйте по имени или времени и раскрывайте строку со сбоем и сохранённым выводом.",
      detailTry: "Номер попытки", detailTryBody: "Повторы хранятся отдельно. Сравнивайте попытки, если одна задача меняет результат или диагноз.",
      detailLink: "Копировать ссылку", detailLinkBody: "Поделитесь глубокой ссылкой на конкретные DAG, запуск, задачу и попытку. Получателю всё равно нужен доступ в Airflow.",
      s4Tip: "<strong>Быстрый путь:</strong> сортировка таблицы по времени поднимет самые медленные тесты, а нажатие статуса оставит только сбои и ошибки.",
      s5Kicker: "06 · Стабильность", s5Title: "Нестабильные тесты и их история",
      s5Intro: "Тест считается нестабильным, если в недавнем окне одной пары DAG·задача он и проходит, и падает. Тот же node ID в другой задаче оценивается отдельно.",
      scoreTitle: "Оценка нестабильности", scoreBody: "Как часто результат меняется между успехом и сбоем. Чем выше, тем меньше предсказуемость.",
      trendTitle: "Тренд", trendBody: "Сравнивает недавнюю половину окна с ранней: становится хуже, успокаивается или без изменений.",
      quarantineTitle: "Карантин", quarantineBody: "Видимый бейдж появляется, когда оценка пересекает настроенный порог. Это сигнал, а не автоматическое действие pytest.",
      historyCardTitle: "История теста", historyCardBody: "Полоса результатов по прогонам. «Не запускался» отличается от пропуска, сбоя и успеха.",
      flakyAction: "Откройте нестабильные тесты из группы или прогона, выберите окно анализа и нажмите тест, чтобы увидеть момент начала изменений.",
      s6Kicker: "07 · Изменение во времени", s6Title: "Сравните прогоны и изучите тепловую карту",
      compareTitle: "Сравнение с предыдущим",
      compareBody: "В прогоне выберите <strong>Сравнить с предыдущим</strong>, чтобы разделить тесты на новые сбои, исправленные, всё ещё падающие, добавленные и удалённые. Это самый быстрый ответ на вопрос «что изменилось в этой сборке?».",
      heatmapTitle: "Тепловая карта тест × прогон",
      heatmapBody: "Строки — тесты, столбцы — недавние прогоны. Чередование результатов выдаёт нестабильность; красный блок справа похож на регрессию; красный столбец указывает на один плохой прогон или сбой среды.",
      heatmap1: "Нажмите ячейку, чтобы открыть точный прогон.", heatmap2: "Нажмите имя теста, чтобы открыть его историю.",
      heatmap3: "Используйте легенду для нужных результатов; пустая пунктирная ячейка означает, что тест не запускался.",
      heatmap4: "Наведите на AI-разобранный сбой, чтобы увидеть категорию без открытия прогона.",
      s7Kicker: "08 · Приоритеты", s7Title: "Разберите сбои и производительность",
      clustersTitle: "Кластеры ошибок",
      clustersBody: "Показатель «Сбои» отражает текущие проблемы: проваленные и ошибочные тесты последнего прогона каждой пары DAG·задача. Похожие сообщения объединяются в кластеры от крупнейшего, чтобы одна первопричина не выглядела десятками отдельных сбоев.",
      uniqueTitle: "Каталог уникальных тестов",
      uniqueBody: "Ищите все разные тесты и сравнивайте число прогонов, успехов, сбоев, ошибок, пропусков и среднее время. Полезно, когда известно имя теста, но не прогон, где он упал.",
      slowTitle: "Замедления и самые долгие тесты",
      slowBody: "Замедления сравнивают недавнее среднее время с ранней половиной и игнорируют мелкий шум. Здесь же перечислены самые долгие тесты по среднему времени. Восстановившийся тест автоматически уйдёт из списка замедлений.",
      s8Kicker: "09 · Дополнительные сигналы", s8Title: "Покрытие и AI-помощники",
      coverageTitle: "Покрытие",
      coverageBody: "Если в прогоне есть данные о покрытии, карточка показывает покрытие строк и настроенную цель. Зелёный означает достижение цели, красный — недобор. Покрытие носит информационный характер и не меняет результат прогона.",
      triageTitle: "AI-разбор",
      triageBody: "Для разобранных сбоев отчёт ставит диагноз перед трассировкой: категорию, гипотезу, предлагаемое исправление, уверенность и команду перезапуска одного теста.",
      triageEnable: "Разбор включается там, где идут тесты, а не в просмотрщике: установите <code>airflow-pytest-plugin[triage-anthropic]</code> на воркерах и передайте параметры в парсер. С одним <code>triage=True</code> обращений к модели нет — прогон всё равно сохранит тип исключения и команду перезапуска для каждого падения. Указанный провайдер добавляет вердикты ИИ.",
      triageConfigLabel: "Настройка на стороне воркера",
      triageConfigCode: "ArchivingResultParser(\n    triage=True,\n    triage_provider=\"anthropic\",  # без него — только отчёт\n    triage_budget=20,             # предел вызовов модели за прогон\n    triage_timeout=45,            # секунд на один вызов\n)",
      markTitle: "Метка в списке прогонов",
      markBody: "Прогоны с разбором помечены прямо в списке — видно, что внутри, ещё до открытия. Наведите на метку для подробностей; название модели показывается, только если есть вердикты, которые ей принадлежат.",
      markColour: "Метка",
      markBlue: "Синяя",
      markBlueBody: "Модель оценила падения. Подсказка называет её, например <code>claude-sonnet-5</code>.",
      markRed: "Красная",
      markRedBody: "Сломался сам разбор — отклонённый ключ, таймаут или недоступный провайдер. Прогон показывает сообщение провайдера дословно.",
      markGrey: "Серая",
      markGreyBody: "Только отчёт о падениях: провайдер не настроен, поэтому сбои перечислены без вердиктов.",
      triageFilterTitle: "Разбор падений по очереди",
      triageFilterBody: "Внутри прогона карточка разбора считает, сколько падений оценено, и показывает состав категорий одной полосой. Нажмите категорию — в таблице останутся только эти падения, остальные цвета на полосе притухнут, но пропорция останется видна. Повторное нажатие снимает фильтр.",
      triageCostBody: "<strong>Во что обходится прогон.</strong> Один вызов модели на каждый упавший тест — поэтому дорогой случай это массовое падение, и именно его ограничивает <code>triage_budget</code>. Перезапуск разбирает те же падения заново и платит снова: поэтому при сравнении попыток вердикты независимы. Успешные тесты не отправляются никогда.",
      category: "Категория", meaning: "Что означает", catRegression: "Вероятно, сломался код продукта.",
      catFlaky: "Тест меняет результат без устойчивого изменения кода.",
      catEnvironment: "Сбой вызвали сеть, сервис, тестовые данные или среда выполнения.",
      catTestBug: "Вероятно, неверны ожидание, фикстура или код самого теста.",
      catUnclear: "Данных недостаточно для надёжной категории.",
      rerunExample: "Готовая команда перезапуска",
      triageNote: "<strong>Считайте вердикты подсказкой.</strong> Если провайдер не ответил, отклонил ключ или исчерпал бюджет, прогон сообщит о незавершённом разборе, а не выдумает вердикты. Зелёный прогон не вызывает модель.",
      assistantTitle: "Спросите историю прогонов",
      assistantBody: "Когда администратор включает чат по отчётам на API-сервере, кнопка «AI-ассистент» открывает по центру большое окно с изменяемым размером и отвечает по выбранным прогонам или текущим фильтрам дашборда. Размер окна сохраняется отдельно для пользователя Airflow. До отправки область показывает число выбранных прогонов, открывает их полный список и объясняет, сколько доступных по RBAC отчётов будет обработано в полном локальном либо ограниченном прямом режиме. Ответ отображается как безопасный Markdown, копируется в исходном Markdown, а широкие таблицы прокручиваются внутри сообщения. Под вопросом отдельно показан объём UTF-8 для system, user, данных отчётов, истории и структуры промпта. Кнопка «Обзор контекста» показывает точный блок данных отчётов после RBAC-фильтрации, отправленный итоговому провайдеру, без системной инструкции и истории. После ответа показываются точные входные, выходные и общие токены, если провайдер вернул статистику. В заголовке суммируются общие токены всех запросов чат-сессии; refresh сохраняет сумму, а «Очистить чат» сбрасывает её. Кнопки источников открывают точные отчёты ответа, а право чтения каждого DAG проверяется заново.",
      assistantConfigLabel: "Установка на API-сервер",
      assistantConfigCode: "pip install 'airflow-pytest-plugin[assistant-anthropic,assistant-local]'\nmkdir -p /models\ncurl -fL 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf?download=true' -o /models/qwen2.5-0.5b-instruct-q4_k_m.gguf\nexport AIRFLOW_PYTEST_ASSISTANT_PROVIDER=anthropic\nexport ANTHROPIC_API_KEY=...\nexport AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL=/models/qwen2.5-0.5b-instruct-q4_k_m.gguf\nexport AIRFLOW_PYTEST_ASSISTANT_CONTEXT_BYTES=49152\nexport AIRFLOW_PYTEST_ASSISTANT_DIRECT_MAX_SUMMARIES=100\nexport AIRFLOW_PYTEST_ASSISTANT_TRACEBACK_BYTES=3072\nexport AIRFLOW_PYTEST_ASSISTANT_CAPTURE_BYTES=2048\nexport AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS=3072",
      assistantInstall: "Дополнение assistant-local устанавливает только движок llama.cpp и не содержит модель. Настройка должна указывать на доступный для чтения файл .gguf, а не на URL или каталог. В Docker или Kubernetes добавьте файл в образ API-сервера либо подключите /models только для чтения, затем перезапустите все процессы API-сервера. Воркерам и планировщику модель не нужна.",
      assistantLimits: "<strong>Чат показывает фактические значения сервера.</strong> Откройте <strong>«Ограничения»</strong>, чтобы увидеть их вертикальным списком. <code>CONTEXT_BYTES</code> — единый бюджет данных всех отчётов в одном запросе прямого режима, а не лимит на каждый отчёт. Сначала записываются сводки с общими счётчиками успеха; 100 сводок — верхняя граница, поэтому byte budget всё равно может исключить самые старые. Записи падений добавляются только целиком. При превышении бюджета ответ получает отметку об ограниченном контексте, но запрос завершается. У истории отдельный лимит 16 000 байт: она не отнимает место у данных отчётов, но входит в итоговый запрос и расход токенов. По умолчанию итоговому ответу доступно 3072 выходных токена; если провайдер достигает лимита, чат сохраняет частичный ответ и явно предупреждает, что он может быть неполным. API-сервер читает переменные выше при запуске и публикует рассчитанные значения через <code>GET /api/assistant/status</code>; в браузере нет второго набора настроек. В Docker Compose задайте их в <code>environment</code> сервиса Airflow API server. Размеры данных показываются в <code>KiB</code>, где <code>1 KiB = 1024 байта</code>. Настраиваемые лимиты данных ограничены безопасными диапазонами, а некорректные значения заменяются значениями по умолчанию. Локальные порции могут быть меньше <code>CONTEXT_BYTES</code>, чтобы помещаться в <code>CONTEXT_N_CTX</code>.",
      assistantPrivacy: "<strong>Учитывайте, что покидает сервер.</strong> Удалённый провайдер получает очищенные от известных секретов данные отчётов: в них могут входить traceback и ограниченная часть captured stdout/stderr/log упавших тестов. С локальной моделью все доступные прогоны и тест-кейсы обрабатываются порциями и иерархически сжимаются; без неё используется ограниченный прямой срез. Локальная модель расходует ресурсы API-сервера и не заменяет итогового провайдера. Текущая вкладка восстанавливает разделённый по пользователям чат после обновления и очищает его при закрытии вкладки или по кнопке «Очистить чат».",
      s9Kicker: "10 · Экспорт и уведомления", s9Title: "Экспортируйте и делитесь результатами",
      allureTitle: "Результаты Allure",
      allureBody: "Если с прогоном сохранены исходные данные Allure, кнопка скачивает ZIP для импорта в Allure TestOps или совместимый процесс. Когда данных нет, кнопка скрыта.",
      emailTitle: "Отправить один прогон",
      emailBody: "Если почта доступна, откройте прогон и нажмите «Почта». Укажите получателей или оставьте поле пустым для командного списка. Адреса проверяются до отправки.",
      alertsTitle: "Автоматические уведомления",
      alertsBody: "Набор может отправлять письма после каждого результата либо только при сбоях и нестабильности. Письма оформлены по результату и ведут к прогону. Ошибка доставки не меняет результат pytest-задачи.",
      emailDomains: "<strong>Круг получателей задаёт сервер, а не форма.</strong> Любой, кто может открыть прогон, отправит его на любой адрес, пока администратор не перечислит разрешённые домены в <code>AIRFLOW_PYTEST_ALERTS_EMAIL_DOMAINS</code>; адрес вне списка получает отказ, а не тихо отбрасывается.",
      emailLog: "Бейдж «Письма» в панели прогона открывает последние попытки доставки: получатели, время, автоматический или ручной источник и статус доставки.",
      s10Kicker: "11 · Личный вид и права", s10Title: "Настройки, язык и доступ",
      settingsTitle: "Настройки дашборда",
      settingsBody: "Кнопка-шестерёнка позволяет скрыть последние прогоны, надёжность или нестабильные тесты. Список прогонов остаётся всегда. Выбор хранится только в этом браузере и не влияет на коллег или данные сервера.",
      languageTitle: "Язык и тема",
      languageBody: "Вьюер и эта справка следуют выбранному в Airflow русскому или английскому языку и светлой или тёмной теме. Отдельного переключателя языка у плагина намеренно нет.",
      rolesTitle: "Что доступно в плагине при вашей роли в Airflow",
      rolesIntro: "Плагин не заводит своих ролей и своего экрана прав. Каждая проверка задаёт Airflow тот же вопрос, что и его собственные страницы DAG — <em>может ли этот пользователь читать этот DAG и может ли его запускать?</em> — так что выданные вашей командой права по DAG и определяют, что вы здесь увидите. Всё сводится к двум разрешениям:",
      rolesAction: "Действие в плагине", rolesNeeds: "Нужно на этом DAG", rolesRole: "Типовая роль Airflow",
      rolesSee: "Видеть прогон в списке, открывать его, читать тесты, вывод и ИИ-вердикты",
      rolesCompare: "Сравнение прогонов, история нестабильности, тепловая карта, покрытие, кластеры ошибок",
      rolesExport: "Скачивать результаты Allure, копировать ссылку, отправлять прогон почтой",
      rolesDelete: "Удалять отчёт — один или всю выборку",
      rolesConfigure: "Включать возможности, задавать каталог отчётов, ставить автоочистку",
      rolesRead: "чтение", rolesTrigger: "запуск DAG",
      rolesDeploy: "разрешение плагина не нужно — это код DAG и окружение",
      rolesViewer: "Viewer и выше", rolesUser: "User / Op и выше",
      rolesAdmin: "тот, кто выкладывает DAG",
      rolesPerDag: "Права выдаются <strong>по DAG, а не на плагин целиком</strong>. Тот, кому доступны два DAG из двадцати, видит ровно эти два набора: список, графики, показатели и панель нестабильности строятся только из доступного ему, поэтому дашборд не расскажет ему об остальных. Удаление проверяется так же для каждого прогона выборки: смешанный пакет удалит только те DAG, которые вам разрешено запускать, а остальные вернёт как сохранённые.",
      rolesNote: "<strong>Два момента.</strong> Пункт меню виден всем, кто вошёл в Airflow — у ссылок плагинов в Airflow нет отдельной проверки прав, — но пользователь без доступных DAG увидит пустой список, а прямая ссылка на чужой прогон ответит «недостаточно прав». А если систему прав Airflow вообще не удаётся опросить, плагин откажет <em>всем</em>, а не станет угадывать.",
      permissionsTitle: "Права",
      permission1: "Вы видите отчёты только тех DAG, на чтение которых у вас есть право.",
      permission2: "Открытие, сравнение, экспорт и отправка видимого прогона требуют права чтения его DAG.",
      permission3: "Удаление отчёта необратимо и требует права запуска этого DAG.",
      permission4: "Эта справка не содержит данных отчётов и доступна независимо от прав на DAG.",
      retentionBody: "Администраторы могут настроить автоматическое хранение, поэтому старые отчёты иногда исчезают. Встроенная политика всегда сохраняет самый новый прогон каждой пары DAG·задача.",
      s11Kicker: "12 · Решение проблем", s11Title: "Частые вопросы",
      faqEmptyQ: "Почему страница пустая?", faqEmptyA: "Пока нет архивных прогонов, подходящих под ваши права и фильтры. Сбросьте фильтры, запустите задачу PytestOperator и нажмите «Обновить». Если коллеги видят отчёт, запросите право чтения DAG.",
      faqPassingQ: "Почему в «успешном прогоне» есть сбои?", faqPassingA: "Успешность определяется настроенным порогом прохождения — по умолчанию 85%, а не обязательно 100%. В отчёте всё равно видны все сбои и ошибки.",
      faqCoverageQ: "Почему нет карточки покрытия?", faqCoverageA: "Этот прогон сохранён без данных покрытия. Карточка скрыта вместо показа вводящего в заблуждение нуля.",
      faqTriageQ: "Почему у части сбоев нет AI-вердикта?", faqTriageA: "Разбор может быть выключен, работать только как отчёт, исчерпать бюджет или не завершиться из-за провайдера. Если отчёт о сбое создан, трассировка и команда перезапуска остаются.",
      faqEmailQ: "Почему нет кнопки «Почта»?", faqEmailA: "Плагину недоступен почтовый транспорт. Уточните у администратора Airflow, настроены ли почтовые уведомления.",
      faqFreshQ: "Почему новый прогон не появился сразу?", faqFreshA: "Индекс отчётов ненадолго кэшируется. Нажмите «Обновить»; обычно новый прогон появляется за несколько секунд.",
      faqDeleteQ: "Почему я не могу удалить отчёт?", faqDeleteA: "Для удаления нужно право запуска этого DAG. Оно строже просмотра, потому что удаление стирает архивные файлы для всех.",
      footer: "Pytest Reports · документация для пользователей",
      pluginVersion: "Установленная версия плагина"
    }
  };

  function parentWin() {
    try { return window.parent && window.parent !== window ? window.parent : null; }
    catch (e) { return null; }
  }
  function sameOriginTop() {
    try {
      var top = window.top;
      return top && top !== window && top.location.origin === window.location.origin
        ? top : null;
    } catch (e) { return null; }
  }
  function localeSignals() {
    var out = [], p = parentWin();
    if (p) {
      try { out.push(p.localStorage.getItem("i18nextLng")); } catch (e) {}
      try { out.push(p.document.documentElement.getAttribute("lang")); } catch (e) {}
    }
    try { out.push(localStorage.getItem("i18nextLng")); } catch (e) {}
    out.push(navigator.language || navigator.userLanguage || "en");
    return out;
  }
  function detectLocale() {
    var signals = localeSignals();
    for (var i = 0; i < signals.length; i++) {
      var value = String(signals[i] || "").toLowerCase();
      if (value.indexOf("ru") === 0) return "ru";
      if (value.indexOf("en") === 0) return "en";
    }
    return "en";
  }
  var LOCALE = detectLocale();
  function t(key) { return HELP_I18N[LOCALE][key] || HELP_I18N.en[key] || key; }
  function applyI18n() {
    document.documentElement.setAttribute("lang", LOCALE);
    document.title = t("title") + " · Pytest Reports";
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      el.innerHTML = t(el.getAttribute("data-i18n-html"));
    });
    document.querySelectorAll("[data-i18n-al]").forEach(function (el) {
      el.setAttribute("aria-label", t(el.getAttribute("data-i18n-al")));
    });
  }
  function luminance(rgb) {
    var m = /rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/.exec(rgb || "");
    return m ? (0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]) / 255 : null;
  }
  function airflowTheme() {
    var p = parentWin();
    if (!p) return null;
    try {
      var doc = p.document, el = doc.documentElement, body = doc.body;
      var hint = ((el.className || "") + " " + (body ? body.className || "" : "") + " "
        + (el.getAttribute("data-theme") || "") + " " + (el.getAttribute("data-color-mode") || "")
        + " " + (el.style.colorScheme || "")).toLowerCase();
      if (/\bdark\b/.test(hint)) return "dark";
      if (/\blight\b/.test(hint)) return "light";
      var lum = luminance(getComputedStyle(body || el).backgroundColor);
      return lum == null ? null : (lum < 0.5 ? "dark" : "light");
    } catch (e) { return null; }
  }
  function applyTheme() {
    var system = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", airflowTheme() || system);
    var p = parentWin();
    if (p) {
      try {
        var bg = getComputedStyle(p.document.documentElement).backgroundColor;
        if (bg && bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent") {
          document.documentElement.style.setProperty("--bg", bg);
        }
      } catch (e) {}
    }
  }
  function viewerUrl() {
    var path = location.pathname.replace(/\/help\/?$/, "/");
    return path || "/";
  }
  document.getElementById("back-btn").setAttribute("href", viewerUrl());
  document.getElementById("help-api-link").setAttribute("href", viewerUrl() + "api/docs");
  function openHelpLink(event) {
    var top = sameOriginTop();
    if (!top) return;
    event.preventDefault();
    top.open(event.currentTarget.href, "_blank", "noopener");
  }
  // Inside Airflow the page is an iframe whose sandbox blocks target=_blank, so every
  // outward link goes through the same-origin parent instead.
  ["help-github-link", "help-api-link", "footer-github-link",
   "rel-current-link", "rel-all-link"].forEach(function (id) {
    document.getElementById(id).addEventListener("click", openHelpLink);
  });
  applyI18n();
  applyTheme();

  // Airflow renders the plugin icon as a plain image, so it cannot inherit the active
  // sidebar item's white foreground. Keep the same active treatment as the report page.
  (function activeNavIcon() {
    try {
      var top = sameOriginTop();
      if (!top || !top.document) return;
      var mount = viewerUrl().replace(/\/+$/, "");
      var iconPath = (mount || "") + "/icon";
      var styleId = "apx-nav-style";
      var add = function () {
        if (top.document.getElementById(styleId)) return;
        var style = top.document.createElement("style");
        style.id = styleId;
        style.textContent = 'img[src*="' + iconPath + '"]'
          + "{filter:brightness(0) invert(1)!important;}";
        (top.document.head || top.document.documentElement).appendChild(style);
      };
      var remove = function () {
        var style = top.document.getElementById(styleId);
        if (style && style.parentNode) style.parentNode.removeChild(style);
      };
      add();
      window.addEventListener("pagehide", remove);
    } catch (e) {}
  })();

  (function bindAirflowNavReturn() {
    try {
      var top = sameOriginTop();
      if (!top || !top.document) return;
      var iconPath = viewerUrl().replace(/\/+$/, "") + "/icon";
      var onNavClick = function (event) {
        var target = event.target;
        if (!target || typeof target.closest !== "function") return;
        var control = target.closest("a, button, [role='link'], [role='menuitem']");
        if (!control || typeof control.querySelectorAll !== "function") return;
        var images = control.querySelectorAll("img[src]");
        for (var i = 0; i < images.length; i++) {
          if ((images[i].getAttribute("src") || "").indexOf(iconPath) !== -1) {
            window.location.assign(viewerUrl());
            return;
          }
        }
      };
      top.document.addEventListener("click", onNavClick, true);
      window.addEventListener("pagehide", function () {
        top.document.removeEventListener("click", onNavClick, true);
      });
    } catch (e) {}
  })();

  var desktopLinks = Array.prototype.slice.call(document.querySelectorAll(".toc a"));
  var mobileLinks = document.querySelector(".mobile-links");
  desktopLinks.forEach(function (link) { mobileLinks.appendChild(link.cloneNode(true)); });
  var allLinks = Array.prototype.slice.call(document.querySelectorAll('.toc a, .mobile-links a'));
  function setCurrent(id) {
    allLinks.forEach(function (link) {
      if (link.getAttribute("href") === "#" + id) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  }
  var sections = Array.prototype.slice.call(document.querySelectorAll(".doc-section"));
  var scrollTick = null;
  function atPageEnd() {
    return Math.ceil(window.scrollY + window.innerHeight)
      >= document.documentElement.scrollHeight - 2;
  }
  function updateCurrentSection() {
    scrollTick = null;
    if (!sections.length) return;
    var current = sections[0];
    var activationLine = window.innerWidth <= 900 ? 148 : 108;
    if (atPageEnd()) {
      current = sections[sections.length - 1];
    } else {
      sections.forEach(function (section) {
        if (section.getBoundingClientRect().top <= activationLine) current = section;
      });
    }
    setCurrent(current.id);
  }
  function scheduleCurrentSection() {
    if (scrollTick !== null) return;
    scrollTick = requestAnimationFrame(updateCurrentSection);
  }
  updateCurrentSection();
  window.addEventListener("scroll", scheduleCurrentSection, { passive: true });
  window.addEventListener("resize", scheduleCurrentSection);
  document.querySelectorAll(".mobile-links a").forEach(function (link) {
    link.addEventListener("click", function () {
      setCurrent(link.getAttribute("href").slice(1));
      var details = document.querySelector(".mobile-toc details");
      if (details) details.open = false;
    });
  });

  function syncFromParent() {
    applyTheme();
    var next = detectLocale();
    if (next !== LOCALE) { LOCALE = next; applyI18n(); }
  }
  var p = parentWin();
  if (p && window.MutationObserver) {
    try {
      var pending = null;
      var mo = new MutationObserver(function () {
        if (pending) return;
        pending = setTimeout(function () { pending = null; syncFromParent(); }, 60);
      });
      mo.observe(p.document.documentElement, {
        attributes: true, attributeFilter: ["class", "style", "lang", "data-theme", "data-color-mode"]
      });
      if (p.document.body) mo.observe(p.document.body, {
        attributes: true, attributeFilter: ["class", "style", "lang", "data-theme", "data-color-mode"]
      });
    } catch (e) {}
  }
  window.addEventListener("storage", syncFromParent);
  if (window.matchMedia) {
    try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme); } catch (e) {}
  }
  var tries = 0;
  var lateLocale = setInterval(function () {
    syncFromParent();
    if (++tries >= 6) clearInterval(lateLocale);
  }, 500);
})();
</script>
</body>
</html>
"""


@lru_cache(maxsize=1)
def help_html() -> str:
    """Return the bilingual, dependency-free user guide HTML.

    The version is substituted rather than baked into the constant so it follows the
    installed distribution -- a page that named the version it was written against would
    be worse than no version at all.
    """
    return _HELP_HTML.replace("__APX_VERSION__", escape(__version__, quote=True))
