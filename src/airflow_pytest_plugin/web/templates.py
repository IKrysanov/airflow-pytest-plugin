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

"""The single-page viewer (dependency-free HTML/CSS/JS, no build step)."""

from __future__ import annotations

_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Pytest Reports</title>
<style>
  /* Palette tracks Airflow 3's Chakra theme; page bg re-read live from parent when embedded. */
  :root {
    --bg: #ffffff; --surface: #ffffff; --surface-2: #f4f4f5;
    --fg: #18181b; --muted: #52525b; --border: #e4e4e7;
    --primary: #017cee; --on-primary: #ffffff; --ring: #017cee40;
    --pass: #008000; --fail: #ff0000; --skip: #ff69b4; --error: #9370db;
    --pass-bg: #0080001a; --fail-bg: #ff00001a; --skip-bg: #ff69b41f; --error-bg: #9370db1f;
    --shadow: 0 1px 2px #0000000d, 0 1px 3px #00000014;
    /* Tooltip inverts the page: dark bubble on the light theme. */
    --tip-bg: #18181b; --tip-fg: #fafafa; --tip-border: #3f3f46;
  }
  html[data-theme="dark"] {
    --bg: #07121e; --surface: #1c2a3a; --surface-2: #243651;
    --fg: #e6edf3; --muted: #94a3b8; --border: #2c4262;
    --primary: #4ba3f5; --on-primary: #07121e; --ring: #017cee66;
    --pass: #2ecc71; --fail: #ff6b6b; --skip: #ff8ecb; --error: #b39ddb;
    --pass-bg: #2ecc711f; --fail-bg: #ff6b6b1f; --skip-bg: #ff8ecb1f; --error-bg: #b39ddb1f;
    --shadow: 0 1px 3px #00000040, 0 2px 8px #00000033;
    /* ...and a white bubble on the dark theme. */
    --tip-bg: #fafafa; --tip-fg: #18181b; --tip-border: #d4d4d8;
  }
  * { box-sizing: border-box; }
  /* Force the hidden attribute to win over display:grid/flex (e.g. .kpis). */
  [hidden] { display: none !important; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.5 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
    -webkit-font-smoothing: antialiased;
  }
  /* Dark theme: darken scrollbar track + thumb like Airflow. */
  html[data-theme="dark"] { scrollbar-color: var(--surface-2) var(--bg); }
  html[data-theme="dark"] ::-webkit-scrollbar { width: 12px; height: 12px; }
  html[data-theme="dark"] ::-webkit-scrollbar-track { background: var(--bg); }
  html[data-theme="dark"] ::-webkit-scrollbar-thumb {
    background: var(--surface-2); border-radius: 7px; border: 3px solid var(--bg);
  }
  html[data-theme="dark"] ::-webkit-scrollbar-thumb:hover { background: var(--border); }
  html[data-theme="dark"] ::-webkit-scrollbar-corner { background: var(--bg); }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .num { font-variant-numeric: tabular-nums; }
  .muted { color: var(--muted); }

  header {
    position: sticky; top: 0; z-index: 20; background: var(--bg);
  }
  .header-inner {
    max-width: 1600px; margin: 0 auto; padding: 14px 20px;
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
  }
  .brand { font-weight: 600; font-size: 18px; letter-spacing: -.01em;
    white-space: nowrap; color: var(--fg); flex: 0 0 auto; }
  /* min-width:0 lets the group actually shrink (Safari otherwise pins flex items
     to their intrinsic width and overflows); wrap is the final safety valve. */
  .controls { display: flex; align-items: center; gap: 10px;
    flex: 1 1 auto; min-width: 0; flex-wrap: wrap; justify-content: flex-end; }
  input, button { font: inherit; color: var(--fg); }
  .field {
    height: 36px; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 8px; padding: 0 11px;
    flex: 1 1 150px; min-width: 0; max-width: 200px;
  }
  #refresh { flex: 0 0 auto; }
  .field:focus { outline: 2px solid var(--ring); outline-offset: 1px; border-color: var(--primary); }
  .btn {
    height: 36px; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 8px; padding: 0 13px; cursor: pointer; white-space: nowrap;
    display: inline-flex; align-items: center; gap: 7px; transition: background .15s, border-color .15s;
  }
  .btn:hover { background: var(--border); }
  .btn:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .btn.primary { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
  .btn.primary:hover { filter: brightness(1.08); }
  .icon-btn { height: auto; padding: 7px; }

  main { padding: 18px 20px 40px; max-width: 1600px; margin: 0 auto; }

  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 18px; }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; box-shadow: var(--shadow); }
  .kpi .label { font-size: 12px; color: var(--muted); text-transform: uppercase;
    letter-spacing: .04em; }
  .kpi .value { font-size: 26px; font-weight: 700; margin-top: 4px; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    overflow: hidden; box-shadow: var(--shadow); }
  .chart-card { margin-bottom: 18px; padding: 14px 16px 8px; }
  .chart-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
  .legend { display: inline-flex; gap: 6px; flex-wrap: wrap; }
  .legend button { display: inline-flex; align-items: center; gap: 5px; border: 0;
    background: none; color: var(--fg); cursor: pointer; font: inherit; font-weight: 500;
    padding: 3px 7px; border-radius: 999px; transition: opacity .12s, background .12s; }
  .legend button:hover { background: var(--surface-2); }
  .legend button:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .legend button.off { opacity: .4; text-decoration: line-through; }
  .legend i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  /* Bars are absolutely placed at integer x/width (one gradient element each), so
     edges land on whole pixels -> crisp, no anti-aliased colour halo.
     The bars live in a fixed-width strip inside a horizontal scroll viewport:
     drag (mouse) or swipe/trackpad (native) or the arrows pan it smoothly. The
     scrollbar is hidden -- the arrows + grab cursor are the affordance. */
  .chart-bars { position: relative; height: 122px; overflow-x: auto; overflow-y: hidden;
    cursor: grab; touch-action: pan-x; overscroll-behavior-x: contain; scrollbar-width: none;
    user-select: none; -webkit-user-select: none; }
  .chart-bars::-webkit-scrollbar { display: none; }
  .chart-bars.dragging { cursor: grabbing; }
  .chart-bars.dragging .bar { cursor: grabbing; }
  .bars-strip { position: relative; height: 100%; }
  .bar { position: absolute; bottom: 22px; height: 100px; border-radius: 2px;
    background: var(--surface-2); transition: filter .12s; cursor: pointer; }
  .bar:hover { filter: brightness(1.08); }
  .bnum { position: absolute; bottom: 0; width: 36px; text-align: center; font-size: 10px;
    color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
  /* Hover tooltip: inverts the page theme. */
  #tip {
    position: fixed; z-index: 100; display: none; pointer-events: none;
    background: var(--tip-bg); color: var(--tip-fg);
    border: 1px solid var(--tip-border); border-radius: 10px;
    padding: 10px 12px; font-size: 12.5px; line-height: 1.55;
    box-shadow: 0 10px 30px #00000038; max-width: 320px;
  }
  #tip .tt { font-weight: 650; font-size: 13px; }
  #tip .tm { opacity: .72; }
  #tip .tr { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 5px; }
  #tip .tr span { white-space: nowrap; font-variant-numeric: tabular-nums; }
  #tip i { display: inline-block; width: 8px; height: 8px; border-radius: 2px;
    margin-right: 5px; vertical-align: middle; }
  .chart-nav { display: inline-flex; align-items: center; gap: 8px; font-size: 12px;
    color: var(--muted); font-weight: 500; }
  .nav-btn { background: var(--surface-2); border: 1px solid var(--border); color: var(--fg);
    border-radius: 6px; padding: 2px 9px; cursor: pointer; line-height: 1.4; font: inherit; }
  .nav-btn:hover:not([disabled]) { background: var(--border); }
  .nav-btn:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .nav-btn[disabled] { opacity: .4; cursor: default; }
  .pager { display: flex; align-items: center; justify-content: flex-end; gap: 10px;
    padding: 10px 12px; border-top: 1px solid var(--border); font-size: 13px; color: var(--muted); }

  .detail-top { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
  .detail-top .kpis { flex: 1 1 280px; margin: 0; }
  .donut { width: 124px; height: 124px; flex: 0 0 auto; }
  .donut-pct { font-size: 27px; font-weight: 700; fill: var(--fg); }
  .donut-lbl { font-size: 11px; fill: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
  .dseg { cursor: pointer; transition: opacity .12s; }
  .dseg:hover { opacity: 1; }
  .af-links { display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
    margin: 16px 0 2px; font-size: 13px; }
  .af-link { display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px;
    border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2);
    color: var(--fg); text-decoration: none; transition: background .12s, border-color .12s; }
  .af-link:hover { border-color: var(--primary); background: var(--border); }
  .af-link:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .af-link svg { width: 13px; height: 13px; color: var(--muted); }

  .row-del { background: none; border: 0; color: var(--muted); cursor: pointer;
    padding: 4px; border-radius: 6px; display: inline-flex; opacity: .5;
    transition: opacity .12s, color .12s, background .12s; }
  tbody tr:hover .row-del { opacity: 1; }
  .row-del:hover { color: var(--fail); background: var(--fail-bg); }
  .row-del:focus-visible { opacity: 1; outline: 2px solid var(--ring); }
  .btn.danger { background: var(--fail); border-color: var(--fail); color: #fff; }
  .btn.danger:hover { filter: brightness(1.08); }
  #confirm { max-width: min(430px, 92vw); }
  #confirm .dlg-body { display: flex; flex-direction: column; gap: 18px; }
  #confirm .cbody { color: var(--muted); line-height: 1.5; }
  #confirm .cbody b { color: var(--fg); overflow-wrap: anywhere; }
  #confirm .cactions { display: flex; justify-content: flex-end; gap: 10px; }

  /* Floating bulk-action toolbar, centred at the bottom of the viewport. */
  .bulk-bar { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    z-index: 90; display: flex; align-items: center; gap: 10px; font-size: 13px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 8px 10px; box-shadow: 0 12px 32px #00000059; }
  .bulk-count { display: inline-flex; align-items: center; padding: 7px 14px; color: var(--fg);
    border: 1px dashed var(--border); border-radius: 8px; }
  .bulk-sep { width: 1px; align-self: stretch; background: var(--border); margin: 3px 2px; }
  .bulk-del { display: inline-flex; align-items: center; gap: 7px; background: none;
    border: 1px solid var(--fail); color: var(--fail); border-radius: 8px; padding: 7px 13px;
    cursor: pointer; font: inherit; font-weight: 500; transition: background .12s; }
  .bulk-del:hover { background: var(--fail-bg); }
  .bulk-close { background: none; border: 0; color: var(--muted); cursor: pointer;
    padding: 7px; border-radius: 8px; display: inline-flex; transition: background .12s, color .12s; }
  .bulk-close:hover { background: var(--surface-2); color: var(--fg); }
  .bulk-del:focus-visible, .bulk-close:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  /* Checkboxes styled like Airflow's (Chakra): rounded square, brand-blue + white tick when on. */
  .sel-cell { width: 1%; white-space: nowrap; padding-right: 0; }
  .sel-cell input[type="checkbox"] {
    appearance: none; -webkit-appearance: none; margin: 0; width: 16px; height: 16px;
    cursor: pointer; vertical-align: middle; background: var(--surface);
    border: 1px solid var(--border); border-radius: 4px;
    display: inline-grid; place-content: center; transition: background .12s, border-color .12s; }
  .sel-cell input[type="checkbox"]:hover { border-color: var(--primary); }
  .sel-cell input[type="checkbox"]:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .sel-cell input[type="checkbox"]:checked,
  .sel-cell input[type="checkbox"]:indeterminate {
    background: var(--primary); border-color: var(--primary); }
  .sel-cell input[type="checkbox"]:checked::after {
    content: ""; width: 4px; height: 8px; border: solid #fff; border-width: 0 2px 2px 0;
    transform: rotate(45deg) translate(-0.5px, -1px); }
  .sel-cell input[type="checkbox"]:indeterminate::after {
    content: ""; width: 8px; height: 2px; background: #fff; border-radius: 1px; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 10px 12px; white-space: nowrap; }
  thead th {
    position: sticky; top: 0; background: var(--surface-2); color: var(--muted);
    font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em;
    border-bottom: 1px solid var(--border); user-select: none;
  }
  th.sortable { cursor: pointer; }
  th.sortable:hover { color: var(--fg); }
  th .arrow { opacity: .9; margin-left: 4px; }
  tbody td { border-bottom: 1px solid var(--border); }
  tbody tr { transition: background .12s; }
  tbody tr.clickable { cursor: pointer; }
  tbody tr.clickable:hover { background: var(--surface-2); }
  tbody tr:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
  td.right { text-align: right; }

  .badge { display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px 2px 7px;
    border-radius: 999px; font-size: 12px; font-weight: 600; line-height: 1.6; }
  .badge svg { width: 13px; height: 13px; }
  .b-pass { color: var(--pass); background: var(--pass-bg); }
  .b-fail { color: var(--fail); background: var(--fail-bg); }
  .b-skip { color: var(--skip); background: var(--skip-bg); }
  .b-error { color: var(--error); background: var(--error-bg); }
  .c-pass { color: var(--pass); } .c-fail { color: var(--fail); }
  .c-skip { color: var(--skip); } .c-error { color: var(--error); }

  .state { padding: 56px 20px; text-align: center; color: var(--muted); }
  .skeleton { height: 14px; border-radius: 6px;
    background: linear-gradient(90deg, var(--surface-2) 25%, var(--border) 37%, var(--surface-2) 63%);
    background-size: 400% 100%; animation: shimmer 1.2s ease infinite; }
  @keyframes shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }

  dialog {
    border: 1px solid var(--border); border-radius: 14px; background: var(--surface);
    color: var(--fg); max-width: min(980px, 94vw); width: 100%; padding: 0;
    box-shadow: 0 20px 60px #0007;
  }
  dialog::backdrop { background: rgba(0, 0, 0, 0.5); }
  .dlg-head { display: flex; align-items: center; gap: 10px; padding: 16px 20px;
    border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); }
  .dlg-head h2 { margin: 0; font-size: 15px; font-weight: 650; overflow-wrap: anywhere; }
  .d-seq { color: var(--muted); font-weight: 600; font-size: 14px;
    font-variant-numeric: tabular-nums; flex: 0 0 auto; }
  .d-seq:empty { display: none; }
  .dlg-body { padding: 18px 20px 22px; max-height: 72vh; overflow: auto; }
  .pills { display: flex; flex-wrap: wrap; gap: 7px; margin: 16px 0 12px; }
  .pill { border: 1px solid var(--border); background: var(--surface-2); color: var(--fg);
    border-radius: 999px; padding: 5px 12px; cursor: pointer; font-size: 13px;
    transition: background .12s, border-color .12s; }
  .pill:hover { border-color: var(--primary); }
  .pill[aria-pressed="true"] { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
  .pill:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  /* Let a long test id keep the cell on one line; the table-wrap scrolls
     horizontally to its full width so it never overlaps the Time column. */
  .case-node { display: inline-block; white-space: nowrap; }
  .case-table { overflow-x: auto; }
  .case-table table { width: max-content; min-width: 100%; }
  .case.clickable[aria-expanded="true"] { background: var(--surface-2); }
  .chev { display: inline-flex; color: var(--muted); transition: transform .15s; }
  .case[aria-expanded="true"] .chev { transform: rotate(90deg); }
  .case-exp > td { padding: 0 12px 12px; border-bottom: 1px solid var(--border); }
  .tb { margin: 0; padding: 2px 0 6px 12px; border-left: 2px solid var(--border);
    overflow-x: auto; max-width: 100%; font-size: 12.5px; line-height: 1.55;
    white-space: pre; color: var(--fg); }
  .copied { font-size: 12px; color: var(--pass); }

  @media (max-width: 680px) {
    .header-inner { flex-direction: column; align-items: stretch; gap: 10px; padding: 10px 12px; }
    .controls { width: 100%; flex-wrap: nowrap; }
    .controls .field { flex: 1 1 0; min-width: 0; max-width: none; }
    #refresh { flex: 0 0 auto; }
    main { padding: 12px 12px 32px; }
    th, td { padding: 8px 9px; }
    .kpi { padding: 12px 13px; }
    .kpi .value { font-size: 22px; }
    .dlg-head { padding: 13px 14px; }
    .dlg-body { padding: 14px 14px 18px; }
  }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>
<script>
/* Pre-paint: set theme + bg from the parent BEFORE body renders, so embedding in Airflow's dark UI never flashes light. */
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
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      document.documentElement.setAttribute("data-theme", "dark");
    }
  } catch (e) { /* cross-origin parent: the main script will theme on load */ }
})();
</script>
</head>
<body>
<header>
 <div class="header-inner">
  <span class="brand" data-i18n="brand">Pytest Reports</span>
  <div class="controls">
    <input id="f-dag" class="field" data-i18n-ph="filterDag" data-i18n-al="filterDagAl"
           list="dags" autocomplete="off" />
    <input id="f-run" class="field" data-i18n-ph="filterRun" data-i18n-al="filterRunAl"
           list="runs" autocomplete="off" />
    <button id="refresh" class="btn primary" type="button">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/>
      </svg>
      <span data-i18n="refresh">Refresh</span>
    </button>
  </div>
  <datalist id="dags"></datalist>
  <datalist id="runs"></datalist>
 </div>
</header>

<main>
  <div class="kpis" id="kpis" hidden></div>
  <div class="card chart-card" id="chart-card" hidden>
    <div class="chart-head">
      <span data-i18n="history">Recent runs</span>
      <span class="legend" id="legend"></span>
      <span style="flex:1"></span>
      <span class="chart-nav" id="chart-nav"></span>
    </div>
    <div id="chart"></div>
  </div>
  <div class="card"><div id="list"></div></div>
</main>

<dialog id="detail" aria-labelledby="d-title">
  <div class="dlg-head">
    <span id="d-seq" class="d-seq"></span>
    <h2 id="d-title">Report</h2>
    <span class="grow" style="flex:1"></span>
    <span id="d-copied" class="copied" hidden data-i18n="copied">Copied</span>
    <button id="d-copy" class="btn icon-btn" type="button" data-i18n-al="copyLink" title="Copy link">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"/>
      </svg>
    </button>
    <button id="d-delete" class="btn icon-btn" type="button" data-i18n-al="deleteReport" title="Delete">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
        <path d="M10 11v6M14 11v6"/>
      </svg>
    </button>
    <button id="d-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="d-body"></div>
</dialog>

<dialog id="confirm" aria-labelledby="c-title">
  <div class="dlg-head"><h2 id="c-title" data-i18n="deleteTitle">Delete report?</h2></div>
  <div class="dlg-body">
    <div class="cbody"><span data-i18n="deleteConfirm">This permanently removes the report and its files.</span> <b id="c-name"></b></div>
    <div class="cactions">
      <button id="c-cancel" class="btn" type="button" data-i18n="cancel">Cancel</button>
      <button id="c-ok" class="btn danger" type="button" data-i18n="delete">Delete</button>
    </div>
  </div>
</dialog>

<div id="bulk-bar" class="bulk-bar" hidden></div>

<script>
(function () {
  // API base derived from the current path so it works under any mount prefix / iframe.
  var API = location.pathname.replace(/\/+$/, "") + "/api/";

  var I18N = {
    en: {
      title: "Pytest Reports", brand: "Pytest Reports", refresh: "Refresh",
      filterDag: "filter dag_id", filterRun: "filter run_id",
      filterDagAl: "Filter by dag_id", filterRunAl: "Filter by run_id",
      history: "Recent runs", copyLink: "Copy link", copied: "Copied",
      closeReport: "Close report",
      cId: "ID", cStatus: "Status", cDag: "DAG", cTask: "Task", cRun: "Run", cTry: "Try",
      cTotal: "Total", cPass: "Pass", cFail: "Fail", cErr: "Err", cSkip: "Skip",
      cDuration: "Duration", cWhen: "When",
      kRuns: "Runs", kPassingRuns: "Passing runs", kTests: "Tests", kFailures: "Failures",
      kPassed: "Passed", kFailed: "Failed", kErrors: "Errors", kSkipped: "Skipped",
      sPass: "PASS", sFail: "FAIL", sError: "ERROR", success: "success",
      passed: "passed", failed: "failed", error: "error", skipped: "skipped", all: "all",
      hOutcome: "Outcome", hTest: "Test", hTime: "Time",
      afDag: "DAG", afRun: "Run", afTask: "Task", downloadAllure: "Allure results",
      loading: "Loading…", noOutput: "No output captured.",
      noMatch: "No reports match the current filter.",
      noReports: "No reports found yet. Run a PytestOperator task with ArchivingResultParser to populate this view.",
      noCases: "No matching cases.", tryWord: "try",
      loadFail: "Failed to load reports: ", reportFail: "Failed to load report: ",
      deleteReport: "Delete report", deleteTitle: "Delete report?",
      deleteTitleN: "Delete {n} reports?",
      deleteConfirm: "This permanently removes the report and its files everywhere.",
      cancel: "Cancel", delete: "Delete", deleting: "Deleting…",
      deleteFail: "Failed to delete: ",
      deleteFailedN: "{n} could not be deleted (no permission).",
      nSelected: "{n} selected", deleteSelected: "Delete", clearSel: "Clear",
      selectRow: "Select row", selectAll: "Select all",
      forbidden: "You don't have permission to delete this report (it requires permission to trigger the DAG).",
      older: "Older runs", newer: "Newer runs",
      prevPage: "Previous page", nextPage: "Next page", page: "Page",
    },
    ru: {
      title: "Pytest Reports", brand: "Pytest-отчёты", refresh: "Обновить",
      filterDag: "фильтр dag_id", filterRun: "фильтр run_id",
      filterDagAl: "Фильтр по dag_id", filterRunAl: "Фильтр по run_id",
      history: "Последние прогоны", copyLink: "Копировать ссылку", copied: "Скопировано",
      closeReport: "Закрыть отчёт",
      cId: "ID", cStatus: "Статус", cDag: "DAG", cTask: "Задача", cRun: "Запуск", cTry: "Попытка",
      cTotal: "Всего", cPass: "Усп", cFail: "Пров", cErr: "Ошиб", cSkip: "Проп",
      cDuration: "Время", cWhen: "Когда",
      kRuns: "Прогонов", kPassingRuns: "Успешных прогонов", kTests: "Тестов", kFailures: "Падений",
      kPassed: "Пройдено", kFailed: "Провалено", kErrors: "Ошибки", kSkipped: "Пропущено",
      sPass: "OK", sFail: "СБОЙ", sError: "ОШИБКА", success: "успех",
      passed: "пройден", failed: "провален", error: "ошибка", skipped: "пропущен", all: "все",
      hOutcome: "Итог", hTest: "Тест", hTime: "Время",
      afDag: "DAG", afRun: "Запуск", afTask: "Задача", downloadAllure: "Allure-отчёт",
      loading: "Загрузка…", noOutput: "Вывод не захвачен.",
      noMatch: "Нет отчётов под текущий фильтр.",
      noReports: "Отчётов пока нет. Запусти задачу PytestOperator с ArchivingResultParser, чтобы они появились здесь.",
      noCases: "Нет подходящих тестов.", tryWord: "попытка",
      loadFail: "Не удалось загрузить отчёты: ", reportFail: "Не удалось загрузить отчёт: ",
      deleteReport: "Удалить отчёт", deleteTitle: "Удалить отчёт?",
      deleteTitleN: "Удалить отчётов: {n}?",
      deleteConfirm: "Отчёт и его файлы будут удалены безвозвратно — везде.",
      cancel: "Отмена", delete: "Удалить", deleting: "Удаление…",
      deleteFail: "Не удалось удалить: ",
      deleteFailedN: "Не удалось удалить: {n} (нет прав).",
      nSelected: "Выбрано: {n}", deleteSelected: "Удалить", clearSel: "Снять",
      selectRow: "Выбрать строку", selectAll: "Выбрать все",
      forbidden: "Нет прав на удаление этого отчёта (нужно право запускать DAG).",
      older: "Старее", newer: "Новее",
      prevPage: "Предыдущая страница", nextPage: "Следующая страница", page: "Страница",
    },
  };
  function parentWin() {
    try { if (window.parent && window.parent !== window) return window.parent; }
    catch (e) {}
    return null;
  }
  function detectLocale() {
    var loc = null, p = parentWin();
    if (p) {
      try { loc = p.document.documentElement.getAttribute("lang"); } catch (e) {}
      if (!loc) { try { loc = p.localStorage.getItem("i18nextLng"); } catch (e) {} }
    }
    if (!loc) { try { loc = localStorage.getItem("i18nextLng"); } catch (e) {} }
    if (!loc) loc = navigator.language || navigator.userLanguage || "en";
    return String(loc).toLowerCase().indexOf("ru") === 0 ? "ru" : "en";
  }
  var LOCALE = detectLocale();
  function t(k) { return (I18N[LOCALE] && I18N[LOCALE][k]) || I18N.en[k] || k; }
  function applyI18n() {
    document.documentElement.setAttribute("lang", LOCALE);
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-ph]").forEach(function (el) {
      el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph")));
    });
    document.querySelectorAll("[data-i18n-al]").forEach(function (el) {
      el.setAttribute("aria-label", t(el.getAttribute("data-i18n-al")));
    });
  }

  var ICONS = {
    pass: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
    fail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    skip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4v16M19 5v14"/><path d="M19 12 9 5v14z"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></svg>',
  };
  var CHEV = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
  var TRASH = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6M14 11v6"/></svg>';

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmtDur(s) { return (Number(s) || 0).toFixed(2) + "s"; }
  function fmtTime(s) {
    if (!s) return "—";
    var d = new Date(s);
    try { return isNaN(d) ? esc(s) : d.toLocaleString(LOCALE); } catch (e) { return esc(s); }
  }
  function statusOf(r) { return r.success ? "pass" : (r.errors > 0 ? "error" : "fail"); }
  function statusLabel(kind) { return { pass: t("sPass"), fail: t("sFail"), error: t("sError") }[kind]; }
  function badge(kind, text) {
    return '<span class="badge b-' + kind + '">' + ICONS[kind] + esc(text) + "</span>";
  }

  function luminance(rgb) {
    var m = /rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/.exec(rgb || "");
    if (!m) return null;
    if (m[4] !== undefined && parseFloat(m[4]) === 0) return null;  // transparent
    return (0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]) / 255;
  }
  function parentDoc() { var p = parentWin(); try { return p ? p.document : null; } catch (e) { return null; } }
  function airflowTheme() {
    var pdoc = parentDoc();
    if (!pdoc) return null;
    try {
      var el = pdoc.documentElement, b = pdoc.body;
      var hint = ((el.className || "") + " " + (b ? b.className || "" : "") + " "
        + (el.getAttribute("data-theme") || "") + " " + (el.getAttribute("data-color-mode") || "")
        + " " + (el.style.colorScheme || "")).toLowerCase();
      if (/\bdark\b/.test(hint)) return "dark";
      if (/\blight\b/.test(hint)) return "light";
      var sources = [b, el];
      for (var i = 0; i < sources.length; i++) {
        if (!sources[i]) continue;
        var lum = luminance(getComputedStyle(sources[i]).backgroundColor);
        if (lum != null) return lum < 0.5 ? "dark" : "light";
      }
    } catch (e) {}
    return null;
  }
  function systemTheme() {
    return (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  }
  function applyTheme() {
    document.documentElement.setAttribute("data-theme", airflowTheme() || systemTheme());
    syncParentBg();
  }

  // When embedded, match our page bg to the parent <html> bg, re-read on every theme change.
  var _lastBg = null;
  function syncParentBg() {
    if (window.self === window.top) return;
    try {
      var bg = getComputedStyle(window.top.document.documentElement).backgroundColor;
      if (!bg || bg === "rgba(0, 0, 0, 0)" || bg === "transparent") {
        bg = getComputedStyle(window.top.document.body).backgroundColor;
      }
      if (bg && bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent" && bg !== _lastBg) {
        _lastBg = bg;
        document.documentElement.style.setProperty("--bg", bg);
      }
    } catch (e) { /* cross-origin parent: keep our own --bg */ }
  }

  function syncFromParent() {
    applyTheme();
    var loc = detectLocale();
    if (loc !== LOCALE) { LOCALE = loc; applyI18n(); renderAll(); }
  }
  applyTheme(); applyI18n();
  // The nav icon Airflow shows for us is a plain <img> with a baked stroke colour,
  // so (unlike Airflow's own currentColor icons) it can't turn white when the item
  // is selected -- on the light theme the picked flask blends into the highlight
  // and vanishes. While THIS page is open, our nav item IS the selected one, so
  // whiten our icon in the parent for the duration and restore it on the way out.
  // Targeting our own icon URL avoids guessing Airflow's active-item selector.
  // Same-origin only; best-effort.
  (function activeNavIcon() {
    try {
      var top = window.top;
      if (top === window.self || !top.document
          || top.location.origin !== window.location.origin) return;
      var mount = window.location.pathname.replace(/\/+$/, "");
      var ID = "apx-nav-style";
      var add = function () {
        if (top.document.getElementById(ID)) return;
        var s = top.document.createElement("style");
        s.id = ID;
        s.textContent = 'img[src*="' + mount + '/icon"]'
          + "{filter:brightness(0) invert(1)!important;}";
        (top.document.head || top.document.documentElement).appendChild(s);
      };
      var remove = function () {
        var s = top.document.getElementById(ID);
        if (s && s.parentNode) s.parentNode.removeChild(s);
      };
      add();
      // Removed when Airflow unmounts our iframe on navigating away.
      window.addEventListener("pagehide", remove);
    } catch (e) { /* cross-origin parent: skip */ }
  })();
  (function watchParent() {
    var pdoc = parentDoc();
    if (pdoc && window.MutationObserver) {
      try {
        // Coalesce the parent's frequent mutations into one cross-frame read.
        var pending = null;
        var debounced = function () {
          if (pending) return;
          pending = setTimeout(function () { pending = null; syncFromParent(); }, 60);
        };
        var mo = new MutationObserver(debounced);
        var opts = { attributes: true,
          attributeFilter: ["class", "style", "lang", "data-theme", "data-color-mode"] };
        mo.observe(pdoc.documentElement, opts);
        if (pdoc.body) mo.observe(pdoc.body, opts);
      } catch (e) {}
    }
    if (window.matchMedia) {
      try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme); } catch (e) {}
    }
    window.addEventListener("storage", syncFromParent);
  })();

  var listEl = document.getElementById("list");
  var kpisEl = document.getElementById("kpis");
  var allReports = [];  // everything fetched
  var reports = [];     // the current filtered view
  var sort = { key: "created_at", dir: -1 };

  // Chart status series: [status key, report field, colour].
  var ORDER = [
    ["passed", "passed", "var(--pass)"],
    ["skipped", "skipped", "var(--skip)"],
    ["failed", "failed", "var(--fail)"],
    ["error", "errors", "var(--error)"],
  ];
  var chartSel = { passed: true, skipped: true, failed: true, error: true };
  var CHART_VISIBLE = 30; // bars visible at once; beyond that the strip scrolls (carousel)
  var PAGE_SIZE = 100;    // list rows per page
  var chartScroll = null; // null => snap to newest; else a remembered scrollLeft (px)
  var chartDragged = false;
  var listPage = 0;
  var selectedIds = new Set();   // report ids ticked for bulk delete

  var COLS = [
    { key: "seq", label: "cId", num: true },
    { key: "status", label: "cStatus", get: function (r) { return r.success ? 2 : (r.errors ? 0 : 1); } },
    { key: "dag_id", label: "cDag", cls: "mono" },
    { key: "task_id", label: "cTask", cls: "mono" },
    { key: "run_id", label: "cRun", cls: "mono muted" },
    { key: "try_number", label: "cTry", num: true },
    { key: "total", label: "cTotal", num: true },
    { key: "passed", label: "cPass", num: true, color: "c-pass" },
    { key: "failed", label: "cFail", num: true, color: "c-fail" },
    { key: "errors", label: "cErr", num: true, color: "c-error" },
    { key: "skipped", label: "cSkip", num: true, color: "c-skip" },
    { key: "duration", label: "cDuration", num: true },
    { key: "created_at", label: "cWhen" },
  ];

  function renderKpis() {
    if (!reports.length) { kpisEl.hidden = true; kpisEl.innerHTML = ""; return; }
    var runs = reports.length;
    var ok = reports.filter(function (r) { return r.success; }).length;
    var tests = reports.reduce(function (a, r) { return a + r.total; }, 0);
    var failures = reports.reduce(function (a, r) { return a + r.failed + r.errors; }, 0);
    var cards = [
      { label: t("kRuns"), value: runs },
      { label: t("kPassingRuns"), value: ok + " / " + runs, cls: ok === runs ? "c-pass" : "" },
      { label: t("kTests"), value: tests },
      { label: t("kFailures"), value: failures, cls: failures ? "c-fail" : "c-pass" },
    ];
    kpisEl.hidden = false;
    kpisEl.innerHTML = cards.map(function (c) {
      return '<div class="kpi"><div class="label">' + esc(c.label) + '</div>'
        + '<div class="value ' + (c.cls || "") + '">' + esc(c.value) + "</div></div>";
    }).join("");
  }

  function renderLegend() {
    var leg = document.getElementById("legend");
    leg.innerHTML = ORDER.map(function (o) {
      return '<button type="button" class="' + (chartSel[o[0]] ? "" : "off")
        + '" data-status="' + o[0] + '" aria-pressed="' + !!chartSel[o[0]] + '">'
        + '<i style="background:' + o[2] + '"></i>' + esc(t(o[0])) + "</button>";
    }).join("");
    leg.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        var s = b.getAttribute("data-status");
        chartSel[s] = !chartSel[s];
        renderChart();
      });
    });
  }

  // Own rAF easing instead of scrollBy({behavior:"smooth"}) -- the latter is
  // unsupported in older Safari (and headless), so animate it ourselves.
  function chartScrollBy(el, delta) {
    var max = el.scrollWidth - el.clientWidth;
    var start = el.scrollLeft, target = Math.max(0, Math.min(max, start + delta));
    if (target === start) return;
    var dur = 280, t0 = null, token = (el._anim = (el._anim || 0) + 1);
    function step(ts) {
      if (el._anim !== token) return;          // a newer scroll/drag superseded us
      if (t0 == null) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;  // easeInOutQuad
      el.scrollLeft = start + (target - start) * e;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // Arrows page the strip by ~one viewport; native scroll/drag handle the rest.
  function renderChartNav(barsEl, scrollable) {
    var nav = document.getElementById("chart-nav");
    if (!scrollable) { nav.innerHTML = ""; return; }
    nav.innerHTML =
      '<button type="button" class="nav-btn" id="ch-older" aria-label="' + esc(t("older")) + '">‹</button>'
      + '<button type="button" class="nav-btn" id="ch-newer" aria-label="' + esc(t("newer")) + '">›</button>';
    function page(dir) { chartScrollBy(barsEl, dir * Math.round(barsEl.clientWidth * 0.8)); }
    document.getElementById("ch-older").addEventListener("click", function () { page(-1); });
    document.getElementById("ch-newer").addEventListener("click", function () { page(1); });
    updateChartArrows(barsEl);
  }
  function updateChartArrows(barsEl) {
    var ol = document.getElementById("ch-older"), ne = document.getElementById("ch-newer");
    if (!ol || !ne) return;
    var max = barsEl.scrollWidth - barsEl.clientWidth;
    ol.disabled = barsEl.scrollLeft <= 1;          // older = left; disabled at the oldest end
    ne.disabled = barsEl.scrollLeft >= max - 1;    // newer = right; disabled at the newest end
  }

  // Mouse drag-to-pan. Touch/trackpad use the element's native horizontal scroll.
  // No pointer capture -- it retargets the synthetic click off the bar (so the
  // bar's click handler never fires). The move/up listeners live on document
  // (wired once) so a drag survives the cursor leaving the strip.
  var chartDrag = null;
  function enableChartDrag(el) {
    el.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "touch") return;
      el._anim = (el._anim || 0) + 1;          // cancel any in-flight arrow animation
      chartDrag = { el: el, x: e.clientX, left: el.scrollLeft, moved: 0 };
      el.classList.add("dragging");
    });
  }
  function chartDragMove(e) {
    if (!chartDrag) return;
    var dx = e.clientX - chartDrag.x;
    if (Math.abs(dx) > chartDrag.moved) chartDrag.moved = Math.abs(dx);
    chartDrag.el.scrollLeft = chartDrag.left - dx;
  }
  function chartDragEnd() {
    if (!chartDrag) return;
    chartDrag.el.classList.remove("dragging");
    chartDragged = chartDrag.moved > 5;          // a real drag suppresses the bar click
    setTimeout(function () { chartDragged = false; }, 0);
    chartDrag = null;
  }

  var tipEl = null;
  function tipShow(html, ev) {
    if (!tipEl) {
      tipEl = document.createElement("div");
      tipEl.id = "tip";
      tipEl.setAttribute("role", "tooltip");
      document.body.appendChild(tipEl);
    }
    tipEl.innerHTML = html;
    tipEl.style.display = "block";
    tipMove(ev);
  }
  function tipMove(ev) {
    if (!tipEl) return;
    var pad = 14, w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    var x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = ev.clientY - h - pad;
    tipEl.style.left = Math.max(8, x) + "px";
    tipEl.style.top = Math.max(8, y) + "px";
  }
  function tipHide() { if (tipEl) tipEl.style.display = "none"; }
  function bindTip(el, htmlFn) {
    if (!el) return;
    var timer = null, last = null;
    el.addEventListener("mouseenter", function (ev) {
      last = ev;
      // Skip if a re-render detached the element during the delay (no stale tooltip).
      timer = setTimeout(function () { if (el.isConnected) tipShow(htmlFn(), last); }, 320);
    });
    el.addEventListener("mousemove", function (ev) {
      last = ev;
      if (tipEl && tipEl.style.display === "block") tipMove(ev);
    });
    el.addEventListener("mouseleave", function () {
      clearTimeout(timer);
      tipHide();
    });
  }
  function statDot(varName, label, v) {
    return '<span><i style="background:var(' + varName + ')"></i>' + v + " " + esc(label) + "</span>";
  }
  function barTip(r, num) {
    return '<div class="tt">#' + num + " · " + esc(r.dag_id) + "</div>"
      + '<div class="tm">' + esc(r.task_id) + "</div>"
      + '<div class="tm">' + esc(fmtTime(r.created_at)) + "</div>"
      + '<div class="tr">'
      + statDot("--pass", t("passed"), r.passed)
      + statDot("--fail", t("failed"), r.failed)
      + statDot("--error", t("error"), r.errors)
      + statDot("--skip", t("skipped"), r.skipped)
      + "</div>";
  }

  function renderChart() {
    renderLegend();
    var card = document.getElementById("chart-card");
    // Chronological (oldest -> newest).
    var data = reports.slice().sort(function (a, b) {
      return String(a.created_at || "") < String(b.created_at || "") ? -1 : 1;
    });
    if (data.length < 2) { card.hidden = true; document.getElementById("chart-nav").innerHTML = ""; return; }
    card.hidden = false;

    var win = data;            // every run; the strip scrolls once past CHART_VISIBLE
    var count = win.length;

    // Bars are absolutely positioned at INTEGER left/width inside a fixed-width
    // strip: a flex-centred bar lands on a fractional pixel, so its bright edge
    // anti-aliases into the background (a red "halo"). Integer geometry = crisp.
    var chart = document.getElementById("chart");
    chart.innerHTML = '<div class="chart-bars" role="img" aria-label="' + esc(t("history"))
      + '"><div class="bars-strip"></div></div>';
    var barsEl = chart.querySelector(".chart-bars");
    var strip = chart.querySelector(".bars-strip");
    // Fixed per-run slot: bars fill the width when they fit, else the strip grows
    // past the viewport and scrolls smoothly (one continuous carousel, no pages).
    var vw = barsEl.clientWidth || 600;
    // Up to CHART_VISIBLE bars fill the viewport; beyond that the strip overflows
    // and you scroll/drag through it (a carousel with the same per-bar sizing).
    var slot = vw / Math.min(count, CHART_VISIBLE);
    var stripW = Math.round(slot * count);
    strip.style.width = stripW + "px";
    var bw = Math.max(6, Math.min(22, Math.round(slot * 0.62)));
    var labelEvery = Math.max(1, Math.ceil(34 / slot));  // keep #labels from overlapping
    var html = win.map(function (r, i) {
      // One hard-stop gradient stacked base-up in ORDER => no seams; a toggled-off
      // status keeps its band as the track colour (never a rescale).
      var rtotal = r.total || 0;
      var bands = [], acc = 0;
      ORDER.forEach(function (o) {
        var v = r[o[1]] || 0;
        if (rtotal <= 0 || v <= 0) return;
        bands.push({ o: o, from: acc, to: acc + (v / rtotal) * 100 });
        acc += (v / rtotal) * 100;
      });
      if (bands.length) bands[bands.length - 1].to = 100;  // snap top to 100%
      var stops = bands.map(function (s) {
        var col = chartSel[s.o[0]] ? s.o[2] : "var(--surface-2)";
        return col + " " + s.from.toFixed(3) + "% " + s.to.toFixed(3) + "%";
      });
      var bg = stops.length ? "background:linear-gradient(to top," + stops.join(",") + ");" : "";
      var center = slot * (i + 0.5);
      var left = Math.round(center - bw / 2);
      var bar = '<div class="bar" data-id="' + esc(r.id) + '" style="left:' + left
        + "px;width:" + bw + "px;" + bg + '"></div>';
      // Number every run when there is room; thin them out when dense, newest first.
      var num = ((count - 1 - i) % labelEvery === 0)
        ? '<div class="bnum" style="left:' + Math.round(center - 18) + 'px">#' + r.seq + "</div>"
        : "";
      return bar + num;
    }).join("");
    strip.innerHTML = html;
    strip.querySelectorAll(".bar").forEach(function (bar, i) {
      var r = win[i], id = bar.getAttribute("data-id");
      bar.addEventListener("click", function () { if (!chartDragged) openDetail(id); });
      bindTip(bar, function () { return barTip(r, r.seq); });
    });

    // Start at the newest (right) unless a scroll position is being preserved
    // (e.g. across a legend toggle). Wire arrows, drag, and scroll memory.
    barsEl.scrollLeft = (chartScroll == null) ? barsEl.scrollWidth
      : Math.min(chartScroll, barsEl.scrollWidth);
    renderChartNav(barsEl, stripW > vw + 1);
    barsEl.addEventListener("scroll", function () {
      chartScroll = barsEl.scrollLeft; updateChartArrows(barsEl);
    });
    enableChartDrag(barsEl);
  }

  function sortReports() {
    var col = COLS.filter(function (c) { return c.key === sort.key; })[0] || COLS[0];
    var getv = col.get || function (r) { return r[col.key]; };
    reports.sort(function (a, b) {
      var x = getv(a), y = getv(b);
      if (typeof x === "string") { x = x.toLowerCase(); y = String(y).toLowerCase(); }
      if (x < y) return -1 * sort.dir;
      if (x > y) return 1 * sort.dir;
      return 0;
    });
  }

  function renderRows(rows) {
    return rows.map(function (r) {
      var st = statusOf(r);
      var cells = COLS.map(function (c) {
        if (c.key === "status") return "<td>" + badge(st, statusLabel(st)) + "</td>";
        if (c.key === "duration") return '<td class="num">' + fmtDur(r.duration) + "</td>";
        if (c.key === "created_at") return '<td class="muted">' + fmtTime(r.created_at) + "</td>";
        var v = r[c.key];
        var cls = [c.cls || "", c.num ? "num" : "", c.color || ""].join(" ").trim();
        return "<td" + (cls ? ' class="' + cls + '"' : "") + ">" + esc(v) + "</td>";
      }).join("");
      var del = '<td class="right"><button class="row-del" type="button" data-del="'
        + esc(r.id) + '" data-label="' + esc(r.dag_id + " · " + r.task_id) + '" aria-label="'
        + esc(t("deleteReport")) + '" title="' + esc(t("deleteReport")) + '">' + TRASH + "</button></td>";
      var sel = '<td class="sel-cell"><input type="checkbox" class="sel" data-id="' + esc(r.id)
        + '"' + (selectedIds.has(r.id) ? " checked" : "") + ' aria-label="' + esc(t("selectRow")) + '"></td>';
      return '<tr class="clickable" tabindex="0" data-id="' + esc(r.id) + '">' + sel + cells + del + "</tr>";
    }).join("");
  }

  function arrow(key) {
    if (sort.key !== key) return "";
    return '<span class="arrow">' + (sort.dir === 1 ? "↑" : "↓") + "</span>";
  }

  function renderList() {
    if (!reports.length) {
      listEl.innerHTML = '<div class="state">'
        + esc(allReports.length ? t("noMatch") : t("noReports")) + "</div>";
      updateBulkBar();  // no rows -> drop any stale bulk bar
      return;
    }
    sortReports();
    var pages = Math.ceil(reports.length / PAGE_SIZE);
    listPage = Math.max(0, Math.min(listPage, pages - 1));
    var pageRows = reports.slice(listPage * PAGE_SIZE, listPage * PAGE_SIZE + PAGE_SIZE);

    var head = COLS.map(function (c) {
      var asc = sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none";
      return '<th class="sortable" data-key="' + c.key + '" aria-sort="' + asc + '">'
        + esc(t(c.label)) + arrow(c.key) + "</th>";
    }).join("");
    var pager = pages > 1
      ? '<div class="pager"><button type="button" class="nav-btn" id="pg-prev"'
          + (listPage <= 0 ? " disabled" : "") + ' aria-label="' + esc(t("prevPage")) + '">‹</button>'
        + "<span>" + esc(t("page")) + " " + (listPage + 1) + " / " + pages + "</span>"
        + '<button type="button" class="nav-btn" id="pg-next"'
          + (listPage >= pages - 1 ? " disabled" : "") + ' aria-label="' + esc(t("nextPage")) + '">›</button></div>'
      : "";
    var selAllTh = '<th class="sel-cell"><input type="checkbox" id="sel-all" aria-label="'
      + esc(t("selectAll")) + '"></th>';
    listEl.innerHTML = '<div class="table-wrap"><table><thead><tr>' + selAllTh + head
      + "<th></th></tr></thead><tbody>" + renderRows(pageRows) + "</tbody></table></div>" + pager;

    listEl.querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var k = th.getAttribute("data-key");
        if (sort.key === k) sort.dir *= -1; else { sort.key = k; sort.dir = 1; }
        listPage = 0;
        renderList();
      });
    });
    var pgPrev = document.getElementById("pg-prev"), pgNext = document.getElementById("pg-next");
    if (pgPrev) pgPrev.addEventListener("click", function () { if (listPage > 0) { listPage--; renderList(); } });
    if (pgNext) pgNext.addEventListener("click", function () { if (listPage < pages - 1) { listPage++; renderList(); } });
    listEl.querySelectorAll(".row-del").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation();  // don't open the detail when deleting
        openConfirm([b.getAttribute("data-del")], b.getAttribute("data-label"));
      });
    });
    listEl.querySelectorAll("tr.clickable").forEach(function (tr) {
      var open = function () { openDetail(tr.getAttribute("data-id")); };
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
    });
    listEl.querySelectorAll(".sel").forEach(function (cb) {
      cb.addEventListener("click", function (e) { e.stopPropagation(); });
      cb.addEventListener("change", function () {
        var id = cb.getAttribute("data-id");
        if (cb.checked) selectedIds.add(id); else selectedIds.delete(id);
        syncSelAll(); updateBulkBar();
      });
    });
    var selAll = document.getElementById("sel-all");
    if (selAll) selAll.addEventListener("change", function () {
      listEl.querySelectorAll(".sel").forEach(function (cb) {
        cb.checked = selAll.checked;
        var id = cb.getAttribute("data-id");
        if (selAll.checked) selectedIds.add(id); else selectedIds.delete(id);
      });
      selAll.indeterminate = false;
      updateBulkBar();
    });
    syncSelAll(); updateBulkBar();
  }

  function syncSelAll() {
    var selAll = document.getElementById("sel-all");
    if (!selAll) return;
    var boxes = listEl.querySelectorAll(".sel"), n = 0;
    boxes.forEach(function (cb) { if (cb.checked) n++; });
    selAll.checked = boxes.length > 0 && n === boxes.length;
    selAll.indeterminate = n > 0 && n < boxes.length;
  }

  function updateBulkBar() {
    var bar = document.getElementById("bulk-bar"), n = selectedIds.size;
    if (!n) { bar.hidden = true; bar.innerHTML = ""; return; }
    bar.hidden = false;
    bar.innerHTML = '<span class="bulk-count">' + esc(t("nSelected").replace("{n}", n)) + "</span>"
      + '<span class="bulk-sep"></span>'
      + '<button type="button" class="bulk-del" id="bulk-del">' + TRASH + " "
      + esc(t("deleteSelected")) + "</button>"
      + '<button type="button" class="bulk-close" id="bulk-clear" aria-label="' + esc(t("clearSel"))
      + '"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
      + ' stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>';
    document.getElementById("bulk-clear").addEventListener("click", function () {
      selectedIds.clear();
      listEl.querySelectorAll(".sel").forEach(function (cb) { cb.checked = false; });
      syncSelAll(); updateBulkBar();
    });
    document.getElementById("bulk-del").addEventListener("click", function () {
      var ids = []; selectedIds.forEach(function (id) { ids.push(id); });
      openConfirm(ids, "");
    });
  }

  function renderAll() { renderKpis(); renderChart(); renderList(); if (detail) renderDetail(); }

  function skeleton() {
    var rows = "";
    for (var i = 0; i < 6; i++) {
      rows += '<tr><td colspan="13"><div class="skeleton" style="width:'
        + (60 + (i * 7) % 35) + '%"></div></td></tr>';
    }
    listEl.innerHTML = '<div class="table-wrap"><table><tbody>' + rows + "</tbody></table></div>";
  }

  function load() {
    skeleton();
    kpisEl.hidden = true;
    document.getElementById("chart-card").hidden = true;
    fetch(API + "reports")
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        allReports = d.reports || [];
        populateSuggestions();
        applyFilter();
        // Open a deep-linked report; the param rides the Airflow parent URL when embedded.
        var want = new URLSearchParams(linkLoc().search).get("report");
        if (want && !detail) openDetail(want);
      })
      .catch(function (e) {
        listEl.innerHTML = '<div class="state c-fail">' + esc(t("loadFail") + e.message) + "</div>";
      });
  }

  // Case-insensitive substring filter.
  function matchesIn(haystack, needle) {
    return !needle || String(haystack).toLowerCase().indexOf(needle.toLowerCase()) !== -1;
  }
  // Stable chronological run number (oldest = 1) for the list # column and the
  // chart bar labels -- so bar #5 and row #5 are the same run.
  function assignSeq() {
    reports.slice().sort(function (a, b) {
      return String(a.created_at || "") < String(b.created_at || "") ? -1 : 1;
    }).forEach(function (r, i) { r.seq = i + 1; });
  }
  function applyFilter(keepPage) {
    var dag = document.getElementById("f-dag").value.trim();
    var run = document.getElementById("f-run").value.trim();
    reports = allReports.filter(function (r) {
      return matchesIn(r.dag_id, dag) && matchesIn(r.run_id, run);
    });
    assignSeq();
    // Filter resets to the newest runs / first page; a delete keeps the user's place.
    if (!keepPage) { chartScroll = null; listPage = 0; }
    renderKpis(); renderChart(); renderList();
  }
  function populateSuggestions() {
    var dags = {}, runs = {};
    allReports.forEach(function (r) { dags[r.dag_id] = 1; runs[r.run_id] = 1; });
    function fill(id, keys) {
      document.getElementById(id).innerHTML = Object.keys(keys).sort().map(function (k) {
        return '<option value="' + esc(k) + '"></option>';
      }).join("");
    }
    fill("dags", dags); fill("runs", runs);
  }

  var dlg = document.getElementById("detail");
  var dBody = document.getElementById("d-body");
  var dTitle = document.getElementById("d-title");
  var detail = null, filter = "all", lastFocus = null, currentId = null;

  function outcomeLabel(o) { return t(o) || o; }

  // Success donut: clickable slices filter the case table by status.
  function donut(m) {
    var total = m.total || 0;
    var C = 2 * Math.PI * 50;  // r = 50
    var ring = '<circle cx="60" cy="60" r="50" fill="none" stroke="var(--surface-2)" stroke-width="16"/>';
    var segs = [["passed", "var(--pass)", m.passed], ["skipped", "var(--skip)", m.skipped],
                ["failed", "var(--fail)", m.failed], ["error", "var(--error)", m.errors]];
    var off = 0, parts = "";
    segs.forEach(function (s) {
      var v = s[2] || 0;
      if (total <= 0 || v <= 0) return;
      var len = (v / total) * C;
      var pct = Math.round((v / total) * 100);
      var lit = filter === "all" || filter === s[0];
      parts += '<circle class="dseg" data-status="' + s[0] + '" data-count="' + v
        + '" data-pct="' + pct + '" cx="60" cy="60" r="50" '
        + 'fill="none" stroke="' + s[1] + '" stroke-width="16" stroke-dasharray="'
        + len.toFixed(2) + " " + (C - len).toFixed(2) + '" stroke-dashoffset="'
        + (-off).toFixed(2) + '" opacity="' + (lit ? 1 : 0.3) + '"></circle>';
      off += len;
    });
    var pct = total > 0 ? Math.round((m.passed / total) * 100) : null;
    var center = '<text x="60" y="58" text-anchor="middle" class="donut-pct">'
      + (pct == null ? "—" : pct + "%") + "</text>"
      + '<text x="60" y="76" text-anchor="middle" class="donut-lbl">' + esc(t("success")) + "</text>";
    return '<svg viewBox="0 0 120 120" class="donut" role="img" aria-label="'
      + (pct == null ? "" : pct + "% ") + esc(t("success")) + '">'
      + '<g transform="rotate(-90 60 60)">' + ring + parts + "</g>" + center + "</svg>";
  }

  // Links back to the run's DAG / DAG run / task instance in the Airflow UI.
  function airflowLinks(m) {
    var enc = encodeURIComponent;
    var dag = "/dags/" + enc(m.dag_id);
    var run = dag + "/runs/" + enc(m.run_id);
    var ti = run + "/tasks/" + enc(m.task_id) + (m.map_index >= 0 ? "/mapped/" + m.map_index : "");
    var ext = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';
    function link(href, label) {
      return '<a class="af-link" href="' + esc(href) + '" target="_top" rel="noopener">'
        + ext + esc(label) + "</a>";
    }
    var out = '<div class="af-links">'
      + link(dag, t("afDag")) + link(run, t("afRun")) + link(ti, t("afTask"));
    if (m.has_allure) {
      var dl = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
        + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>';
      out += '<button type="button" class="af-link" data-allure="' + esc(m.id) + '">'
        + dl + esc(t("downloadAllure")) + "</button>";
    }
    return out + "</div>";
  }

  function openInAirflow(href) {
    try {
      var top = window.top;
      if (top && top !== window.self && top.location
          && top.location.origin === window.location.origin) {
        // Same-origin parent: drive its History API and let React Router react.
        top.history.pushState({}, "", href);
        top.dispatchEvent(new PopStateEvent("popstate"));
        try { top.scrollTo(0, 0); } catch (e) {}
        return;
      }
    } catch (e) { /* not embedded, or cross-origin parent */ }
    // Standalone (or unreachable parent): navigate this window.
    window.location.href = href;
  }

  // Download the report's Allure results zip. Airflow's iframe sandbox blocks
  // downloads (no allow-downloads), so trigger the click from the parent doc
  // (same-origin, not sandboxed); standalone uses our own document.
  function downloadAllure(id) {
    var url = API + "reports/" + encodeURIComponent(id) + "/allure.zip";
    try {
      var w = sameOriginTop();
      var doc = w ? w.document : document;
      var a = doc.createElement("a");
      a.href = url; a.download = "allure-results.zip";
      doc.body.appendChild(a); a.click(); doc.body.removeChild(a);
    } catch (e) {
      window.location.href = url;
    }
  }

  function renderDetail() {
    var m = detail;
    var counts = { all: m.cases.length, passed: 0, failed: 0, error: 0, skipped: 0 };
    m.cases.forEach(function (c) { if (counts[c.outcome] != null) counts[c.outcome]++; });
    dTitle.textContent = m.dag_id + " · " + m.task_id + " · " + t("tryWord") + " " + m.try_number;
    // Run number (#N), matching the chart bar and the list ID column.
    var rec = reports.filter(function (x) { return x.id === currentId; })[0];
    document.getElementById("d-seq").textContent = rec && rec.seq ? "#" + rec.seq : "";

    var kpis = [
      [t("kPassed"), m.passed, "c-pass"], [t("kFailed"), m.failed, "c-fail"],
      [t("kErrors"), m.errors, "c-error"], [t("kSkipped"), m.skipped, "c-skip"],
      [t("cDuration"), fmtDur(m.duration), ""],
    ].map(function (k) {
      return '<div class="kpi"><div class="label">' + esc(k[0]) + '</div>'
        + '<div class="value ' + k[2] + '">' + esc(k[1]) + "</div></div>";
    }).join("");

    var pills = ["all", "failed", "error", "skipped", "passed"].map(function (k) {
      return '<button class="pill" type="button" data-f="' + k + '" aria-pressed="'
        + (filter === k) + '">' + esc(outcomeLabel(k)) + " (" + counts[k] + ")</button>";
    }).join("");

    var rows = m.cases.filter(function (c) { return filter === "all" || c.outcome === filter; });
    var body = rows.length ? rows.map(function (c, i) {
      var kind = { passed: "pass", failed: "fail", error: "error", skipped: "skip" }[c.outcome] || "skip";
      var output = (c.message && c.message.trim()) ? c.message : t("noOutput");
      return '<tr class="case clickable" tabindex="0" role="button" aria-expanded="false" data-exp="' + i + '">'
        + "<td>" + badge(kind, outcomeLabel(c.outcome)) + "</td>"
        + '<td><span class="case-node mono">' + esc(c.node_id) + "</span></td>"
        + '<td class="num right">' + fmtDur(c.time) + "</td>"
        + '<td class="right"><span class="chev">' + CHEV + "</span></td></tr>"
        + '<tr class="case-exp" data-row="' + i + '" hidden><td colspan="4">'
        + '<pre class="tb mono">' + esc(output) + "</pre></td></tr>";
    }).join("") : '<tr><td colspan="4"><div class="state">' + esc(t("noCases")) + "</div></td></tr>";

    dBody.innerHTML = '<div class="detail-top">' + donut(m)
      + '<div class="kpis">' + kpis + "</div></div>"
      + airflowLinks(m)
      + '<div class="pills">' + pills + "</div>"
      + '<div class="card table-wrap case-table"><table><thead><tr>'
      + "<th>" + esc(t("hOutcome")) + "</th><th>" + esc(t("hTest"))
      + '</th><th class="right">' + esc(t("hTime")) + "</th><th></th>"
      + "</tr></thead><tbody>" + body + "</tbody></table></div>";

    dBody.querySelectorAll(".pill").forEach(function (p) {
      p.addEventListener("click", function () { filter = p.getAttribute("data-f"); renderDetail(); });
    });
    // Airflow's iframe sandbox drops target="_top"/window.open (no top-navigation), but not
    // the History API on the same-origin parent -- so drive React Router instead. The real
    // <a href> stays so cmd/right-click still offers "open in new tab".
    dBody.querySelectorAll(".af-link[href]").forEach(function (a) {
      a.addEventListener("click", function (ev) {
        ev.preventDefault();
        openInAirflow(a.getAttribute("href"));
      });
    });
    dBody.querySelectorAll("[data-allure]").forEach(function (b) {
      b.addEventListener("click", function () { downloadAllure(b.getAttribute("data-allure")); });
    });
    dBody.querySelectorAll(".dseg").forEach(function (seg) {
      seg.addEventListener("click", function () {
        var s = seg.getAttribute("data-status");
        filter = filter === s ? "all" : s;
        renderDetail();
      });
      bindTip(seg, function () {
        return '<div class="tt">' + esc(outcomeLabel(seg.getAttribute("data-status")))
          + "</div>" + '<div class="tr"><span>' + seg.getAttribute("data-count")
          + " · " + seg.getAttribute("data-pct") + "%</span></div>";
      });
    });
    dBody.querySelectorAll("tr.case").forEach(function (tr) {
      var toggle = function () {
        var i = tr.getAttribute("data-exp");
        var exp = dBody.querySelector('tr.case-exp[data-row="' + i + '"]');
        var open = tr.getAttribute("aria-expanded") === "true";
        tr.setAttribute("aria-expanded", String(!open));
        if (exp) exp.hidden = open;
      };
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      });
    });
  }

  function openDetail(id) {
    filter = "all"; currentId = id;
    lastFocus = document.activeElement;
    document.getElementById("d-copied").hidden = true;
    dBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    dTitle.textContent = t("loading");
    if (typeof dlg.showModal === "function") { if (!dlg.open) dlg.showModal(); }
    else dlg.setAttribute("open", "");
    setReportParam(id);
    fetch(API + "reports/" + encodeURIComponent(id))
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { detail = d; detail.cases = d.cases || []; renderDetail(); })
      .catch(function (e) {
        dBody.innerHTML = '<div class="state c-fail">' + esc(t("reportFail") + e.message) + "</div>";
      });
  }

  // Deep-link rides the Airflow parent URL when embedded (the iframe's bare path
  // isn't shareable), falling back to our own location standalone.
  function sameOriginTop() {
    try {
      if (window.top !== window.self && window.top.location
          && window.top.location.origin === window.location.origin) {
        return window.top;
      }
    } catch (e) { /* cross-origin parent */ }
    return null;
  }
  function linkLoc() { var w = sameOriginTop(); return w ? w.location : window.location; }
  function linkHistory() { var w = sameOriginTop(); return w ? w.history : window.history; }

  function setReportParam(id) {
    try {
      var loc = linkLoc();
      // Preserve other params Airflow keeps on the parent URL.
      var qs = new URLSearchParams(loc.search);
      if (id) qs.set("report", id); else qs.delete("report");
      var s = qs.toString();
      linkHistory().replaceState(null, "", loc.pathname + (s ? "?" + s : ""));
    } catch (e) {}
  }
  function closeDetail() {
    detail = null; currentId = null;
    if (dlg.open) dlg.close(); else dlg.removeAttribute("open");
    setReportParam(null);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  // Close on a backdrop click (like Airflow's modals); ESC closes natively via the
  // "cancel" event. Guarded on mousedown so a text drag that ends outside the box
  // doesn't dismiss it.
  function closeOnBackdrop(d, closeFn) {
    var startedOutside = false;
    var outside = function (e) {
      var r = d.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    d.addEventListener("mousedown", function (e) { startedOutside = e.target === d && outside(e); });
    d.addEventListener("click", function (e) { if (startedOutside && outside(e)) closeFn(); });
  }

  // Copy a deep-link to this report.
  function copyLink() {
    if (!currentId) return;
    var loc = linkLoc();
    var qs = new URLSearchParams(loc.search);
    qs.set("report", currentId);
    var url = loc.origin + loc.pathname + "?" + qs.toString();
    var done = function () {
      var c = document.getElementById("d-copied");
      c.hidden = false;
      setTimeout(function () { c.hidden = true; }, 1800);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done, function () { legacyCopy(url, done); });
    } else { legacyCopy(url, done); }
  }
  function legacyCopy(text, done) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); document.body.removeChild(ta); done();
    } catch (e) { /* clipboard unavailable */ }
  }

  document.getElementById("d-close").addEventListener("click", closeDetail);
  document.getElementById("d-copy").addEventListener("click", copyLink);
  document.getElementById("d-delete").addEventListener("click", function () {
    if (currentId) openConfirm([currentId], dTitle.textContent);
  });
  dlg.addEventListener("cancel", function () { detail = null; currentId = null; setReportParam(null); });
  dlg.addEventListener("close", function () { if (lastFocus && lastFocus.focus) lastFocus.focus(); });
  closeOnBackdrop(dlg, closeDetail);

  var confirmDlg = document.getElementById("confirm");
  var pendingDelete = [];   // ids awaiting confirmation (1 row or N selected)
  function openConfirm(ids, label) {
    pendingDelete = ids.slice();
    var n = pendingDelete.length;
    document.getElementById("c-title").textContent =
      n > 1 ? t("deleteTitleN").replace("{n}", n) : t("deleteTitle");
    document.getElementById("c-name").textContent = label || "";
    if (typeof confirmDlg.showModal === "function") { if (!confirmDlg.open) confirmDlg.showModal(); }
    else confirmDlg.setAttribute("open", "");
  }
  function closeConfirm() {
    pendingDelete = [];
    if (confirmDlg.open) confirmDlg.close(); else confirmDlg.removeAttribute("open");
  }
  function doDelete() {
    var ids = pendingDelete.slice();
    if (!ids.length) return;
    var ok = document.getElementById("c-ok");
    ok.disabled = true; ok.textContent = t("deleting");
    var failed = [];
    Promise.all(ids.map(function (id) {
      // Each DELETE is RBAC-checked server-side, so a forbidden one just fails.
      return fetch(API + "reports/" + encodeURIComponent(id), { method: "DELETE" })
        .then(function (r) {
          if (r.status === 404 || r.ok) {
            allReports = allReports.filter(function (x) { return x.id !== id; });
            selectedIds.delete(id);
            if (currentId === id) closeDetail();
          } else { failed.push(id); }
        })
        .catch(function () { failed.push(id); });
    })).then(function () {
      applyFilter(true);
      if (failed.length) {
        pendingDelete = failed;
        document.getElementById("c-name").textContent =
          t("deleteFailedN").replace("{n}", failed.length);
      } else {
        closeConfirm();
      }
    }).finally(function () { ok.disabled = false; ok.textContent = t("delete"); });
  }
  document.getElementById("c-cancel").addEventListener("click", closeConfirm);
  document.getElementById("c-ok").addEventListener("click", doDelete);
  confirmDlg.addEventListener("cancel", function () { pendingDelete = []; });
  closeOnBackdrop(confirmDlg, closeConfirm);

  document.getElementById("refresh").addEventListener("click", load);
  document.addEventListener("pointermove", chartDragMove);
  document.addEventListener("pointerup", chartDragEnd);
  document.addEventListener("pointercancel", chartDragEnd);
  ["f-dag", "f-run"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", applyFilter);
  });
  // Re-render the chart on resize so bars re-snap to the new pixel grid.
  var _rsTimer;
  window.addEventListener("resize", function () {
    clearTimeout(_rsTimer);
    _rsTimer = setTimeout(function () { if (reports.length) { chartScroll = null; renderChart(); } }, 150);
  });
  load();
})();
</script>
</body>
</html>
"""


def index_html() -> str:
    """Return the single-page viewer HTML."""
    return _INDEX_HTML
