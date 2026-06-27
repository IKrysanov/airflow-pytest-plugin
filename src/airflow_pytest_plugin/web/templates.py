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
    --trend: #0891b2;  /* cyan pass-rate trend line (darker for contrast on white) */
    --thresh: #d97706;  /* amber success-threshold gridline -- distinct from the line */
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
    --trend: #22d3ee;  /* cyan pass-rate trend line (brighter on the navy theme) */
    --thresh: #fbbf24;  /* amber success-threshold gridline */
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
  /* Each filter input + its custom suggestions dropdown live in a positioned wrap;
     the wrap carries the adaptive flex sizing, the input fills it. */
  .field-wrap { position: relative; display: flex; flex: 1 1 150px; min-width: 0; max-width: 200px; }
  .field {
    height: 36px; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 8px; padding: 0 11px; flex: 1 1 auto; min-width: 0; width: 100%;
  }
  #refresh, .menu-wrap { flex: 0 0 auto; }
  .menu-wrap { position: relative; }
  .menu-wrap .caret { width: 12px; height: 12px; opacity: .65; }
  .menu { position: absolute; right: 0; top: calc(100% + 6px); z-index: 30; padding: 5px;
    min-width: 190px; background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; box-shadow: var(--shadow); }
  .menu[hidden] { display: none; }
  .menu-item { display: flex; align-items: center; gap: 9px; width: 100%; border: 0;
    background: none; color: var(--fg); cursor: pointer; font: inherit; font-size: 13px;
    text-align: left; padding: 8px 10px; border-radius: 7px; }
  .menu-item:hover { background: var(--surface-2); }
  .menu-item:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
  .menu-item svg { width: 16px; height: 16px; flex: 0 0 auto; color: var(--muted); }
  .field:focus { outline: 2px solid var(--ring); outline-offset: 1px; border-color: var(--primary); }
  /* Suggestions: a tidy dropdown anchored under the input (replaces the native
     <datalist>, whose popup escapes the iframe with a detached system shadow). */
  .suggest {
    position: absolute; top: calc(100% + 5px); left: 0; right: 0; z-index: 60;
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    box-shadow: var(--shadow); max-height: 260px; overflow-y: auto; padding: 4px;
  }
  .suggest .opt { padding: 7px 9px; border-radius: 6px; cursor: pointer; font-size: 13px;
    color: var(--fg); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .suggest .opt:hover, .suggest .opt.active { background: var(--surface-2); }
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
  /* Allure button: same height as the neighbouring icon buttons (32px), only wider. */
  #d-allure { height: 32px; padding: 0 10px; gap: 6px; font-size: 12.5px; }

  main { padding: 18px 20px 40px; max-width: 1600px; margin: 0 auto; }

  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 18px; }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; box-shadow: var(--shadow); }
  .kpi.clickable { cursor: pointer; transition: background .12s, border-color .12s; }
  .kpi.clickable:hover { background: var(--surface-2); border-color: var(--muted); }
  .kpi.clickable:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .kpi .label { font-size: 12px; color: var(--muted); text-transform: uppercase;
    letter-spacing: .04em; }
  .kpi .value { font-size: 26px; font-weight: 700; margin-top: 4px; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    overflow: hidden; box-shadow: var(--shadow); }
  .chart-card { margin-bottom: 18px; padding: 14px 16px 8px; }
  .chart-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
  /* "Showing N selected · show all" note when ticked runs filter the chart. */
  .chart-filter { display: inline-flex; align-items: center; gap: 8px; font-weight: 500;
    color: var(--primary); }
  .chart-clear { border: 0; background: none; color: var(--primary); cursor: pointer;
    font: inherit; font-weight: 600; text-decoration: underline; padding: 0; }
  .chart-clear:hover { opacity: .8; }
  .chart-clear:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; border-radius: 3px; }
  /* Pass-rate trend: checkbox toggle + the cyan line/dots/threshold overlay. */
  .trend-toggle { display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
    font-weight: 500; white-space: nowrap; color: var(--muted); }
  #chart { position: relative; }
  .trend-svg { position: absolute; left: 0; top: 0; pointer-events: none; overflow: visible; }
  .trend-line { fill: none; stroke: var(--trend); stroke-width: 2;
    stroke-linejoin: round; stroke-linecap: round; }
  .trend-dot { fill: var(--trend); stroke: var(--surface); stroke-width: 1.5;
    pointer-events: auto; cursor: pointer; }
  .trend-thresh { position: absolute; left: 0; right: 0; pointer-events: none;
    border-top: 2px dashed var(--thresh); }
  .trend-thresh span { position: absolute; right: 2px; top: -9px; font-size: 10px;
    font-weight: 700; color: var(--thresh); background: var(--surface); padding: 0 4px;
    border-radius: 3px; box-shadow: 0 0 0 1px var(--thresh); }
  .trend-thresh.label-below span { top: 3px; }  /* high threshold -> label under the line */
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
  /* 6px of headroom up top so a 100%-pass trend dot is never clipped. */
  .chart-bars { position: relative; height: 128px; overflow-x: auto; overflow-y: hidden;
    cursor: grab; touch-action: pan-x; overscroll-behavior-x: contain; scrollbar-width: none;
    user-select: none; -webkit-user-select: none; }
  .chart-bars::-webkit-scrollbar { display: none; }
  .chart-bars.dragging { cursor: grabbing; }
  .chart-bars.dragging .bar { cursor: grabbing; }
  .bars-strip { position: relative; height: 100%; }
  .bar { position: absolute; bottom: 22px; height: 100px; border-radius: 2px;
    background: var(--surface-2); transition: filter .12s, opacity .12s; cursor: pointer; }
  .bar:hover { filter: brightness(1.08); }
  /* With the trend on, bars recede so the line/threshold read clearly; hovering one
     brings it back to full strength. */
  .bars-strip.trend-on .bar { opacity: .26; }
  .bars-strip.trend-on .bar:hover { opacity: 1; filter: brightness(1.08); }
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

  /* Main board: the recent-runs chart and the flaky panel share the row 50/50. */
  .board { display: flex; gap: 16px; align-items: stretch; margin-bottom: 18px; }
  .board > .card { flex: 1 1 0; min-width: 0; margin-bottom: 0; }
  .flaky-card { padding: 14px 16px; display: flex; flex-direction: column; }
  /* Flaky panel controls: a search field + a quarantined-only toggle. */
  .flk-board-ctrls { display: flex; align-items: center; gap: 12px; margin: 2px 0 10px; }
  .flk-board-ctrls .case-q { flex: 1 1 auto; max-width: none; height: 30px; }
  .flk-board-only { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto;
    white-space: nowrap; color: var(--muted); font-size: 12.5px; cursor: pointer; }
  .flaky-scroll { flex: 1 1 auto; min-height: 110px; max-height: 132px; overflow-y: auto;
    overscroll-behavior-y: contain; scrollbar-width: thin; }
  .fb-row { display: flex; align-items: center; gap: 10px; padding: 7px 2px;
    border-bottom: 1px solid var(--border); cursor: pointer; font-size: 12.5px; }
  .fb-row:last-child { border-bottom: 0; }
  .fb-row:hover { background: var(--surface-2); }
  .fb-main { flex: 1 1 auto; min-width: 0; }
  .fb-node { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  /* dag·task line carries the quarantine badge: the text truncates, the badge stays. */
  .fb-sub { display: flex; align-items: center; color: var(--muted); font-size: 11px; }
  .fb-dagtask { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .fb-meta { color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; flex: 0 0 auto; }
  .fb-empty { color: var(--muted); font-size: 12.5px; padding: 16px 2px; }
  @media (max-width: 860px) { .board { flex-direction: column; } }
  /* Unique-tests list: one wrapping column, so a long node id never forces a
     horizontal scrollbar (the dialog body scrolls vertically). */
  .uq-row { padding: 9px 4px; border-bottom: 1px solid var(--border); cursor: pointer;
    font-size: 12.5px; overflow-wrap: anywhere; }
  .uq-row:last-child { border-bottom: 0; }
  .uq-row:hover { background: var(--surface-2); }
  .uq-row:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }

  /* Test-duration histogram inside a run: 10s buckets, drag/scroll carousel. */
  .bench-card { margin: 16px 0 4px; padding: 12px 14px 10px; }
  .bench-scroll { overflow-x: auto; overflow-y: hidden; cursor: grab; touch-action: pan-x;
    overscroll-behavior-x: contain; scrollbar-width: none;
    user-select: none; -webkit-user-select: none; }
  .bench-scroll::-webkit-scrollbar { display: none; }
  .bench-scroll.dragging { cursor: grabbing; }
  .bench-strip { display: flex; align-items: flex-end; width: max-content; }
  .bench-col { flex: 0 0 58px; display: flex; flex-direction: column; align-items: center; }
  .bench-barwrap { height: 92px; width: 100%; display: flex; align-items: flex-end;
    justify-content: center; cursor: default; }
  .bench-bar { width: 26px; border-radius: 3px 3px 0 0; transition: filter .12s; }
  .bench-bar:hover { filter: brightness(1.12); }
  .bench-x { margin-top: 6px; font-size: 10px; color: var(--muted); white-space: nowrap;
    font-variant-numeric: tabular-nums; }

  .detail-top { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
  .detail-top .kpis { flex: 1 1 280px; margin: 0; }
  /* overflow:visible so a lifted slice isn't clipped at the svg's edge. */
  .donut { width: 124px; height: 124px; flex: 0 0 auto; overflow: visible; }
  .donut-pct { font-size: 27px; font-weight: 700; fill: var(--fg); }
  .donut-lbl { font-size: 11px; fill: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
  /* Rounded arc ends; hovering a slice lifts it (scaling a centred circle pushes its arc out). */
  .dseg { cursor: pointer; stroke-linecap: round;
    transition: opacity .12s, transform .12s ease-out;
    transform-box: view-box; transform-origin: 60px 60px; }
  .dseg:hover { opacity: 1; transform: scale(1.07); }
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
  .sel-cell input[type="checkbox"], #case-grp, #flk-qonly, #flk-board-qonly, #trend-toggle {
    appearance: none; -webkit-appearance: none; margin: 0; width: 16px; height: 16px;
    cursor: pointer; vertical-align: middle; background: var(--surface);
    border: 1px solid var(--border); border-radius: 4px; flex: 0 0 auto;
    display: inline-grid; place-content: center; transition: background .12s, border-color .12s; }
  .sel-cell input[type="checkbox"]:hover, #case-grp:hover, #flk-qonly:hover,
  #flk-board-qonly:hover, #trend-toggle:hover { border-color: var(--primary); }
  .sel-cell input[type="checkbox"]:focus-visible, #case-grp:focus-visible, #flk-qonly:focus-visible,
  #flk-board-qonly:focus-visible, #trend-toggle:focus-visible {
    outline: 2px solid var(--ring); outline-offset: 1px; }
  .sel-cell input[type="checkbox"]:checked, #case-grp:checked, #flk-qonly:checked,
  #flk-board-qonly:checked, #trend-toggle:checked, .sel-cell input[type="checkbox"]:indeterminate {
    background: var(--primary); border-color: var(--primary); }
  .sel-cell input[type="checkbox"]:checked::after, #case-grp:checked::after, #flk-qonly:checked::after,
  #flk-board-qonly:checked::after, #trend-toggle:checked::after {
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
    color: var(--fg); max-width: min(980px, 92vw); width: 100%; padding: 0;
    /* Never touch the window edges: cap height and keep a margin all around. */
    max-height: 90vh; margin: auto; box-shadow: 0 20px 60px #0007;
  }
  dialog[open] { display: flex; flex-direction: column; }
  /* Popups opened from inside a run sit inset within it -- narrower/shorter than the
     detail dialog so they never touch its borders. */
  #flaky, #history, #compare { max-width: min(680px, 84vw); max-height: 82vh; }
  dialog::backdrop { background: rgba(0, 0, 0, 0.5); }
  .dlg-head { display: flex; align-items: center; gap: 10px; padding: 16px 20px;
    border-bottom: 1px solid var(--border); flex: 0 0 auto; background: var(--surface);
    border-radius: 14px 14px 0 0; }
  .dlg-head h2 { margin: 0; font-size: 15px; font-weight: 650; overflow-wrap: anywhere; }
  /* Same size + line box as the title so the run number sits on its baseline. */
  .d-seq { color: var(--muted); font-weight: 600; font-size: 15px;
    font-variant-numeric: tabular-nums; flex: 0 0 auto; }
  .d-seq:empty { display: none; }
  /* Body scrolls (both axes) within the capped dialog; head stays put. */
  .dlg-body { padding: 18px 20px 22px; flex: 1 1 auto; min-height: 0; overflow: auto; }
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
  /* border-collapse:separate so the frozen (sticky) outcome column keeps its OWN
     borders -- with collapse, a sticky cell's borders belong to the table and get
     painted over, so the column's row lines vanished and the header doubled up.
     Each cell carries only border-bottom (+ the divider on the first cell), so the
     lines are single and aligned across all columns. */
  .case-table table { width: max-content; min-width: 100%;
    border-collapse: separate; border-spacing: 0; }
  .case.clickable[aria-expanded="true"] { background: var(--surface-2); }
  .case-table thead th:first-child,
  .case-table tr.case > td:first-child { position: sticky; left: 0;
    border-right: 1px solid var(--border); }
  .case-table tr.case > td:first-child { background: var(--surface); z-index: 1; }
  .case-table tr.case.clickable:hover > td:first-child,
  .case-table tr.case[aria-expanded="true"] > td:first-child { background: var(--surface-2); }
  .case-table thead th:first-child { z-index: 3; }
  .chev { display: inline-flex; color: var(--muted); transition: transform .15s; }
  .case[aria-expanded="true"] .chev { transform: rotate(90deg); }
  .case-exp > td { padding: 0 12px 12px; border-bottom: 1px solid var(--border); }
  .tb { margin: 0; padding: 2px 0 6px 12px; border-left: 2px solid var(--border);
    overflow-x: auto; max-width: 100%; font-size: 12.5px; line-height: 1.55;
    white-space: pre; color: var(--fg); }
  .copied { font-size: 12px; color: var(--pass); }
  /* Compare (diff) sections */
  .cmp-sec { margin-bottom: 16px; }
  .cmp-sec h3 { font-size: 13px; font-weight: 650; margin: 0 0 6px;
    display: flex; align-items: center; gap: 7px; }
  .cmp-sec h3 .dot { width: 9px; height: 9px; border-radius: 2px; flex: 0 0 auto; }
  .cmp-list { margin: 0; padding: 0; list-style: none; }
  .cmp-list li { display: flex; gap: 10px; align-items: baseline; justify-content: space-between;
    padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 12.5px; }
  .cmp-list li:last-child { border-bottom: 0; }
  .cmp-list .node { overflow-wrap: anywhere; }
  .cmp-list .chg { color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }
  /* Flaky list + test-history timeline */
  .od { display: inline-block; width: 11px; height: 11px; border-radius: 2px; }
  .ostrip { display: inline-flex; gap: 3px; flex: 0 0 auto; }
  .fk-row, .hist-row { display: flex; align-items: center; gap: 10px; padding: 9px 0;
    border-bottom: 1px solid var(--border); font-size: 12.5px; }
  .fk-row:last-child, .hist-row:last-child { border-bottom: 0; }
  .fk-row .node, .hist-row .when { flex: 1 1 auto; overflow-wrap: anywhere; }
  .hist-row .when { color: var(--muted); }
  .fk-row .fk-meta, .hist-row .dur { color: var(--muted); white-space: nowrap;
    font-variant-numeric: tabular-nums; }
  /* Test-history node header wraps so a long node id never scrolls horizontally. */
  .hist-node { overflow-wrap: anywhere; color: var(--muted); margin-bottom: 8px; }
  /* Flaky-deeper bits: score, trend arrow, quarantine + list badges, modal controls. */
  .flk-score { color: var(--fg); font-variant-numeric: tabular-nums; }
  .flk-trend { font-weight: 700; }
  .flk-trend.up { color: var(--fail); }
  .flk-trend.down { color: var(--pass); }
  .flk-trend.flat { color: var(--muted); }
  /* Quarantine badge: em-sized so it scales to whatever line it sits on, and
     flex:0 0 auto so it's never clipped by a neighbour's ellipsis. */
  .flk-q { flex: 0 0 auto; font-size: 0.82em; font-weight: 700; text-transform: uppercase;
    letter-spacing: .03em; color: #fff; background: var(--fail); border-radius: 4px;
    padding: 0 5px; line-height: 1.6; margin-left: 6px; vertical-align: middle; }
  .flk-ctrls { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    margin: 0 0 12px; font-size: 12.5px; color: var(--muted); }
  .flk-ctrls label { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
  .flk-ctrls select { height: 30px; color: var(--fg); background: var(--surface-2);
    border: 1px solid var(--border); border-radius: 8px; padding: 0 8px; }
  .case-hist { background: none; border: 0; color: var(--primary); cursor: pointer;
    font: inherit; font-size: 12px; padding: 0 0 8px; display: inline-flex; align-items: center; gap: 5px; }
  .case-hist svg { width: 14px; height: 14px; }
  .case-ctrls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 0 0 10px; }
  .case-q { flex: 1 1 220px; min-width: 0; max-width: 340px; height: 32px; color: var(--fg);
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 0 10px; }
  .case-q:focus { outline: 2px solid var(--ring); outline-offset: 1px; border-color: var(--primary); }
  .case-grp-lbl { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px;
    color: var(--muted); cursor: pointer; white-space: nowrap; }
  .case-table tr.grp > td { background: var(--surface-2); font-weight: 600; cursor: pointer;
    user-select: none; position: sticky; left: 0; }
  .case-table tr.grp .chev { transition: transform .15s; }

  @media (max-width: 680px) {
    .header-inner { flex-direction: column; align-items: stretch; gap: 10px; padding: 10px 12px; }
    .controls { width: 100%; flex-wrap: nowrap; }
    .controls .field-wrap { flex: 1 1 0; min-width: 0; max-width: none; }
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
    <span class="field-wrap">
      <input id="f-dag" class="field" data-i18n-ph="filterDag" data-i18n-al="filterDagAl"
             autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" />
      <div class="suggest" id="sg-dag" role="listbox" hidden></div>
    </span>
    <span class="field-wrap">
      <input id="f-task" class="field" data-i18n-ph="filterTask" data-i18n-al="filterTaskAl"
             autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" />
      <div class="suggest" id="sg-task" role="listbox" hidden></div>
    </span>
    <span class="field-wrap">
      <input id="f-run" class="field" data-i18n-ph="filterRun" data-i18n-al="filterRunAl"
             autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" />
      <div class="suggest" id="sg-run" role="listbox" hidden></div>
    </span>
    <span class="menu-wrap">
      <button id="links-btn" class="btn" type="button" data-i18n-al="linksAl"
              aria-haspopup="true" aria-expanded="false">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
        <svg class="caret" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m6 9 6 6 6-6"/>
        </svg>
      </button>
      <div class="menu" id="links-menu" role="menu" hidden>
        <button class="menu-item" type="button" role="menuitem"
                data-href="https://github.com/IKrysanov/airflow-pytest-plugin">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17 5 18 5.3 18 5.3c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg>
          <span data-i18n="ghItem">GitHub</span>
        </button>
        <button class="menu-item" type="button" role="menuitem" data-api="docs">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
          <span data-i18n="apiDocs">API docs</span>
        </button>
      </div>
    </span>
    <button id="refresh" class="btn primary" type="button">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/>
      </svg>
      <span data-i18n="refresh">Refresh</span>
    </button>
  </div>
 </div>
</header>

<main>
  <div class="kpis" id="kpis" hidden></div>
  <div class="board" id="board" hidden>
    <div class="card chart-card" id="chart-card" hidden>
      <div class="chart-head">
        <span data-i18n="history">Recent runs</span>
        <span class="chart-filter" id="chart-filter" hidden></span>
        <span class="legend" id="legend"></span>
        <span style="flex:1"></span>
        <label class="trend-toggle"><input type="checkbox" id="trend-toggle" />
          <span data-i18n="trendToggle">Pass-rate trend</span></label>
        <span class="chart-nav" id="chart-nav"></span>
      </div>
      <div id="chart"></div>
    </div>
    <div class="card flaky-card" id="flaky-card">
      <div class="chart-head">
        <span data-i18n="flakyTitle">Flaky tests</span>
        <span style="flex:1"></span>
        <span class="muted" id="flaky-count"></span>
      </div>
      <div class="flk-board-ctrls">
        <input id="flk-board-q" class="case-q" type="text" data-i18n-ph="flkSearch"
          data-i18n-al="flkSearch" placeholder="filter flaky tests…" />
        <label class="flk-board-only"><input type="checkbox" id="flk-board-qonly" />
          <span data-i18n="flkQuarantinedOnly">Quarantined only</span></label>
      </div>
      <div class="flaky-scroll" id="flaky-list"></div>
    </div>
  </div>
  <div class="card"><div id="list"></div></div>
</main>

<dialog id="detail" aria-labelledby="d-title">
  <div class="dlg-head">
    <span id="d-seq" class="d-seq"></span>
    <h2 id="d-title">Report</h2>
    <span class="grow" style="flex:1"></span>
    <span id="d-copied" class="copied" hidden data-i18n="copied">Copied</span>
    <button id="d-allure" class="btn" type="button" hidden data-i18n-al="downloadAllure">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>
      </svg>
      <span data-i18n="downloadAllure">Allure results</span>
    </button>
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

<dialog id="failures" aria-labelledby="fl-title">
  <div class="dlg-head">
    <h2 id="fl-title" data-i18n="failuresTitle">Failed tests</h2>
    <span class="grow" style="flex:1"></span>
    <button id="fl-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="fl-body"></div>
</dialog>

<dialog id="unique" aria-labelledby="uq-title">
  <div class="dlg-head">
    <h2 id="uq-title" data-i18n="uniqueTitle">Unique tests</h2>
    <span class="grow" style="flex:1"></span>
    <button id="uq-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="uq-body"></div>
</dialog>

<dialog id="compare" aria-labelledby="cmp-title">
  <div class="dlg-head">
    <h2 id="cmp-title" data-i18n="compareTitle">Compare</h2>
    <span class="grow" style="flex:1"></span>
    <button id="cmp-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="cmp-body"></div>
</dialog>

<dialog id="flaky" aria-labelledby="fk-title">
  <div class="dlg-head">
    <h2 id="fk-title" data-i18n="flakyTitle">Flaky tests</h2>
    <span class="grow" style="flex:1"></span>
    <button id="fk-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="fk-body"></div>
</dialog>

<dialog id="history" aria-labelledby="hist-title">
  <div class="dlg-head">
    <h2 id="hist-title" data-i18n="historyTitle">Test history</h2>
    <span class="grow" style="flex:1"></span>
    <button id="hist-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="hist-body"></div>
</dialog>

<div id="bulk-bar" class="bulk-bar" hidden></div>

<script>
(function () {
  // API base derived from the current path so it works under any mount prefix / iframe.
  var API = location.pathname.replace(/\/+$/, "") + "/api/";

  var I18N = {
    en: {
      title: "Pytest Reports", brand: "Pytest Reports", refresh: "Refresh",
      filterDag: "filter dag_id", filterTask: "filter task_id", filterRun: "filter run_id",
      filterDagAl: "Filter by dag_id", filterTaskAl: "Filter by task_id", filterRunAl: "Filter by run_id",
      history: "Recent runs", copyLink: "Copy link", copied: "Copied",
      chartSelected: "showing {n} selected", chartShowAll: "show all",
      trendToggle: "Pass-rate trend", passRate: "pass rate",
      closeReport: "Close report", ofWord: "of", testsWord: "tests",
      apiDocs: "API docs", linksAl: "Links & documentation", ghItem: "GitHub",
      benchTitle: "Test durations (10s buckets)", uniqueTitle: "Unique tests",
      cId: "ID", cStatus: "Status", cDag: "DAG", cTask: "Task", cRun: "Run", cTry: "Try",
      cTotal: "Total", cPass: "Pass", cFail: "Fail", cErr: "Err", cSkip: "Skip",
      cDuration: "Duration", cWhen: "When",
      kRuns: "Runs", kPassingRuns: "Passing runs", kTests: "Unique tests", kFailures: "Failures",
      kPassed: "Passed", kFailed: "Failed", kErrors: "Errors", kSkipped: "Skipped",
      sPass: "PASS", sFail: "FAIL", sError: "ERROR", success: "success",
      passed: "passed", failed: "failed", error: "error", skipped: "skipped", all: "all",
      hOutcome: "Outcome", hTest: "Test", hTime: "Time",
      afDag: "DAG", afRun: "Run", afTask: "Task", downloadAllure: "Allure results",
      loading: "Loading…", noOutput: "No output captured.",
      noMatch: "No reports match the current filter.",
      noReports: "No reports found yet. Run a PytestOperator task with ArchivingResultParser to populate this view.",
      noCases: "No matching cases.", tryWord: "try",
      failuresTitle: "Failed tests", noFailures: "No failed tests.",
      compareTitle: "Compare", comparePrev: "Compare to previous",
      comparePrevAl: "Compare to the previous run", compareFail: "Failed to compare: ",
      compareNoChange: "No differences from the previous run.",
      cmp_newly_failed: "Newly failed", cmp_fixed: "Fixed", cmp_still_failing: "Still failing",
      cmp_added: "Added", cmp_removed: "Removed",
      flakyTitle: "Flaky tests", flakyBtn: "Flaky tests",
      flakyBtnAl: "Flaky tests in recent runs", flakyFail: "Failed to load flaky tests: ",
      noFlaky: "No flaky tests in the recent runs.", flkFailed: "failed",
      flkSearch: "filter flaky tests…", flkNoMatch: "No flaky tests match the filter.",
      flkWindow: "Analysis window:", flkWinOpt: "last {n} runs",
      flkWindowTip: "How many recent runs of this dag·task to scan for flakiness",
      flkQuarantinedOnly: "Quarantined only",
      flkQuarantine: "quarantine", flkQuarantineTip: "Flaky enough to quarantine",
      flkScoreTip: "Flakiness: how often the result flips between pass and fail",
      flkTrendUp: "Flaking more lately", flkTrendDown: "Calming down",
      flkTrendFlat: "Steady trend",
      historyTitle: "Test history", historyBtn: "History",
      historyFail: "Failed to load history: ", noHistory: "No history for this test.",
      histDidntRun: "did not run",
      caseSearch: "filter tests…", caseGroup: "Group by module",
      failCapped: "Showing the first {n} failures.",
      loadFail: "Failed to load reports: ", reportFail: "Failed to load report: ",
      failuresFail: "Failed to load failures: ",
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
      filterDag: "фильтр dag_id", filterTask: "фильтр task_id", filterRun: "фильтр run_id",
      filterDagAl: "Фильтр по dag_id", filterTaskAl: "Фильтр по task_id", filterRunAl: "Фильтр по run_id",
      history: "Последние прогоны", copyLink: "Копировать ссылку", copied: "Скопировано",
      chartSelected: "показаны выбранные: {n}", chartShowAll: "показать все",
      trendToggle: "Тренд прохождения", passRate: "доля прохождения",
      closeReport: "Закрыть отчёт", ofWord: "из", testsWord: "тестов",
      apiDocs: "Документация API", linksAl: "Ссылки и документация", ghItem: "GitHub",
      benchTitle: "Время выполнения тестов (по 10с)", uniqueTitle: "Уникальные тесты",
      cId: "ID", cStatus: "Статус", cDag: "DAG", cTask: "Задача", cRun: "Запуск", cTry: "Попытка",
      cTotal: "Всего", cPass: "Усп", cFail: "Пров", cErr: "Ошиб", cSkip: "Проп",
      cDuration: "Время", cWhen: "Когда",
      kRuns: "Прогонов", kPassingRuns: "Успешных прогонов", kTests: "Уникальные тесты", kFailures: "Падений",
      kPassed: "Пройдено", kFailed: "Провалено", kErrors: "Ошибки", kSkipped: "Пропущено",
      sPass: "OK", sFail: "СБОЙ", sError: "ОШИБКА", success: "успех",
      passed: "пройден", failed: "провален", error: "ошибка", skipped: "пропущен", all: "все",
      hOutcome: "Итог", hTest: "Тест", hTime: "Время",
      afDag: "DAG", afRun: "Запуск", afTask: "Задача", downloadAllure: "Allure-отчёт",
      loading: "Загрузка…", noOutput: "Вывод не захвачен.",
      noMatch: "Нет отчётов под текущий фильтр.",
      noReports: "Отчётов пока нет. Запусти задачу PytestOperator с ArchivingResultParser, чтобы они появились здесь.",
      noCases: "Нет подходящих тестов.", tryWord: "попытка",
      failuresTitle: "Проваленные тесты", noFailures: "Проваленных тестов нет.",
      compareTitle: "Сравнение", comparePrev: "Сравнить с предыдущим",
      comparePrevAl: "Сравнить с предыдущим прогоном", compareFail: "Не удалось сравнить: ",
      compareNoChange: "Отличий от предыдущего прогона нет.",
      cmp_newly_failed: "Новые падения", cmp_fixed: "Починены", cmp_still_failing: "Всё ещё падают",
      cmp_added: "Добавлены", cmp_removed: "Удалены",
      flakyTitle: "Нестабильные тесты", flakyBtn: "Нестабильные",
      flakyBtnAl: "Нестабильные тесты за последние прогоны", flakyFail: "Не удалось загрузить: ",
      noFlaky: "Нестабильных тестов за последние прогоны нет.", flkFailed: "падений",
      flkSearch: "поиск нестабильных тестов…",
      flkNoMatch: "Под фильтр не попал ни один нестабильный тест.",
      flkWindow: "Окно анализа:", flkWinOpt: "последние {n} прогонов",
      flkWindowTip: "Сколько последних прогонов этого dag·task сканировать на нестабильность",
      flkQuarantinedOnly: "Только карантин",
      flkQuarantine: "карантин", flkQuarantineTip: "Достаточно нестабилен для карантина",
      flkScoreTip: "Нестабильность: как часто результат скачет между pass и fail",
      flkTrendUp: "Стал чаще флакать", flkTrendDown: "Стабилизируется",
      flkTrendFlat: "Тренд ровный",
      historyTitle: "История теста", historyBtn: "История",
      historyFail: "Не удалось загрузить историю: ", noHistory: "Истории по этому тесту нет.",
      histDidntRun: "не запускался",
      caseSearch: "фильтр тестов…", caseGroup: "Группировать по модулю",
      failCapped: "Показаны первые {n} падений.",
      loadFail: "Не удалось загрузить отчёты: ", reportFail: "Не удалось загрузить отчёт: ",
      failuresFail: "Не удалось загрузить падения: ",
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
  var passTrend = false;        // overlay the pass-rate trend line (checkbox-toggled)
  var successThreshold = 0.85;  // echoed by /api/reports; drives the trend's threshold line
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

  // Distinct test count, fetched from the backend (the list summaries have only totals);
  // null until the first response. Refreshed (debounced) whenever the filter changes.
  var uniqueTests = null, uniqueTestsList = [], uniqTimer = null, uniqSeq = 0;
  function uniqueQuery(extra) {
    var q = new URLSearchParams();
    var dag = document.getElementById("f-dag").value.trim();
    var task = document.getElementById("f-task").value.trim();
    var run = document.getElementById("f-run").value.trim();
    if (dag) q.set("dag_id", dag);
    if (task) q.set("task_id", task);
    if (run) q.set("run_id", run);
    if (extra) q.set(extra, "1");
    return q.toString();
  }
  function refreshUniqueTests() {
    clearTimeout(uniqTimer);
    uniqTimer = setTimeout(function () {
      var my = ++uniqSeq;  // ignore a stale response landing after a newer filter
      fetch(API + "unique-tests?" + uniqueQuery())
        .then(function (r) { return r.ok ? r.json() : { count: null }; })
        .then(function (d) { if (my === uniqSeq) { uniqueTests = d.count; renderKpis(); } })
        .catch(function () {});
      if (uniqueDlg.open) loadUniqueList();  // keep an open list in sync with the filter
    }, 250);
  }
  function renderKpis() {
    if (!reports.length) { kpisEl.hidden = true; kpisEl.innerHTML = ""; return; }
    var runs = reports.length;
    var ok = reports.filter(function (r) { return r.success; }).length;
    var failures = reports.reduce(function (a, r) { return a + r.failed + r.errors; }, 0);
    var cards = [
      { label: t("kRuns"), value: runs },
      { label: t("kPassingRuns"), value: ok + " / " + runs, cls: ok === runs ? "c-pass" : "" },
      { label: t("kTests"), value: uniqueTests == null ? "…" : uniqueTests,
        id: "kpi-unique", click: uniqueTests > 0 },
      { label: t("kFailures"), value: failures, cls: failures ? "c-fail" : "c-pass",
        id: "kpi-failures", click: failures > 0 },
    ];
    kpisEl.hidden = false;
    kpisEl.innerHTML = cards.map(function (c) {
      var attrs = (c.id ? ' id="' + c.id + '"' : "")
        + (c.click ? ' role="button" tabindex="0"' : "");
      return '<div class="kpi' + (c.click ? " clickable" : "") + '"' + attrs
        + '><div class="label">' + esc(c.label) + '</div>'
        + '<div class="value ' + (c.cls || "") + '">' + esc(c.value) + "</div></div>";
    }).join("");
    var fk = document.getElementById("kpi-failures");
    if (fk && failures > 0) {
      fk.addEventListener("click", openFailures);
      fk.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openFailures(); }
      });
    }
    var uq = document.getElementById("kpi-unique");
    if (uq && uniqueTests > 0) {
      uq.addEventListener("click", openUnique);
      uq.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openUnique(); }
      });
    }
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
    }
    // A modal <dialog> renders in the top layer, above any z-index -- so a tooltip
    // for a chart inside it must live in that dialog, or it's painted behind it.
    var dlgs = document.querySelectorAll("dialog[open]");
    var host = dlgs.length ? dlgs[dlgs.length - 1] : document.body;
    if (tipEl.parentNode !== host) host.appendChild(tipEl);
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
    // Ticked runs in the list filter the chart to their bars only (empty = all),
    // so you can pick a few runs and read just their trend.
    var selActive = selectedIds.size > 0;
    var data = reports.slice().filter(function (r) {
      return !selActive || selectedIds.has(r.id);
    }).sort(function (a, b) {
      return String(a.created_at || "") < String(b.created_at || "") ? -1 : 1;
    });
    renderChartFilterNote(selActive, data.length);
    // A real trend needs >=2 bars; but when the user has picked runs, honour even one.
    if (data.length < (selActive ? 1 : 2)) {
      card.hidden = true; document.getElementById("chart-nav").innerHTML = ""; return;
    }
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
    renderTrend(chart, strip, win, slot, stripW);

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

  // Pass-rate trend overlay: a cyan line through each bar's green-top (passed/total),
  // dots with an exact-% tooltip, and a dashed threshold gridline. Bars are 100%-
  // normalised, so the green top IS the pass rate. Only drawn when the checkbox is on.
  function renderTrend(chart, strip, win, slot, stripW) {
    if (!passTrend) return;
    strip.classList.add("trend-on");  // dim the bars so the line stands out
    // Map a pass rate to a y inside the bar's pixel box: the bar fills the bottom
    // 100px (above a 22px label strip), leaving headroom up top for the 100% dot.
    var BAR_BOTTOM = 22, BAR_H = 100;
    var barTop = (strip.clientHeight || 128) - BAR_BOTTOM - BAR_H;  // = top headroom
    var yOf = function (rate) { return barTop + BAR_H * (1 - rate); };
    var pts = [];
    win.forEach(function (r, i) {
      var tot = r.total || 0;
      if (tot <= 0) return;  // no tests -> no green top to plot
      var rate = (r.passed || 0) / tot;
      pts.push({ x: slot * (i + 0.5), y: yOf(rate), r: r, rate: rate });
    });
    var poly = pts.map(function (p) { return p.x.toFixed(1) + "," + p.y.toFixed(1); }).join(" ");
    var dots = pts.map(function (p) {
      return '<circle class="trend-dot" cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1)
        + '" r="3.2" data-id="' + esc(p.r.id) + '"></circle>';
    }).join("");
    var line = pts.length > 1
      ? '<polyline class="trend-line" points="' + esc(poly) + '"></polyline>' : "";
    strip.insertAdjacentHTML("beforeend",
      '<svg class="trend-svg" width="' + stripW + '" height="' + (strip.clientHeight || 128)
      + '" aria-hidden="true">' + line + dots + "</svg>");
    strip.querySelectorAll(".trend-dot").forEach(function (dot, i) {
      var p = pts[i];
      dot.addEventListener("click", function () { if (!chartDragged) openDetail(p.r.id); });
      bindTip(dot, function () {
        return "<b>#" + p.r.seq + "</b> " + esc(t("passRate")) + ": "
          + Math.round(p.rate * 100) + "% (" + (p.r.passed || 0) + "/" + (p.r.total || 0) + ")";
      });
    });
    // Dashed threshold gridline, pinned (lives in #chart, outside the scrolling strip).
    var thy = yOf(successThreshold);
    var th = document.createElement("div");
    // Near the top (a high threshold) the label flips below the line so it isn't clipped.
    th.className = "trend-thresh" + (thy < 14 ? " label-below" : "");
    th.style.top = thy.toFixed(1) + "px";
    th.innerHTML = "<span>" + Math.round(successThreshold * 100) + "%</span>";
    chart.appendChild(th);
  }

  function renderChartFilterNote(active, shown) {
    var note = document.getElementById("chart-filter");
    if (!note) return;
    if (!active) { note.hidden = true; note.innerHTML = ""; return; }
    note.hidden = false;
    note.innerHTML = esc(t("chartSelected").replace("{n}", shown))
      + ' <button type="button" class="chart-clear" id="chart-clear">'
      + esc(t("chartShowAll")) + "</button>";
    var clr = document.getElementById("chart-clear");
    if (clr) clr.addEventListener("click", clearSelection);
  }

  function clearSelection() {
    selectedIds.clear();
    listEl.querySelectorAll(".sel").forEach(function (cb) { cb.checked = false; });
    syncSelAll(); updateBulkBar(); renderChart();
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
        syncSelAll(); updateBulkBar(); renderChart();  // chart follows the selection
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
      updateBulkBar(); renderChart();
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
    document.getElementById("bulk-clear").addEventListener("click", clearSelection);
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
        if (typeof d.success_threshold === "number") successThreshold = d.success_threshold;
        populateSuggestions();
        applyFilter();
        loadFlaky();
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
    var task = document.getElementById("f-task").value.trim();
    var run = document.getElementById("f-run").value.trim();
    reports = allReports.filter(function (r) {
      return matchesIn(r.dag_id, dag) && matchesIn(r.task_id, task) && matchesIn(r.run_id, run);
    });
    assignSeq();
    // Filter resets to the newest runs / first page; a delete keeps the user's place.
    if (!keepPage) { chartScroll = null; listPage = 0; }
    document.getElementById("board").hidden = allReports.length === 0;
    renderKpis(); renderChart(); renderList(); renderFlakyBoard();
    refreshUniqueTests();
  }
  // Flaky panel on the main board: global flaky tests, filtered client-side by the
  // dag/task search; a row opens that test's history.
  var allFlaky = [];
  function renderFlakyBoard() {
    var box = document.getElementById("flaky-list");
    if (!box) return;
    var dag = document.getElementById("f-dag").value.trim().toLowerCase();
    var task = document.getElementById("f-task").value.trim().toLowerCase();
    var qEl = document.getElementById("flk-board-q");
    var q = qEl ? qEl.value.trim().toLowerCase() : "";
    var qOnlyEl = document.getElementById("flk-board-qonly");
    var qOnly = !!(qOnlyEl && qOnlyEl.checked);
    var rows = allFlaky.filter(function (f) {
      if (dag && f.dag_id.toLowerCase().indexOf(dag) === -1) return false;
      if (task && f.task_id.toLowerCase().indexOf(task) === -1) return false;
      if (qOnly && !f.quarantined) return false;
      if (q && (f.node_id + " " + f.dag_id + " " + f.task_id).toLowerCase().indexOf(q) === -1) {
        return false;
      }
      return true;
    });
    document.getElementById("flaky-count").textContent = rows.length ? String(rows.length) : "";
    if (!rows.length) {
      // Distinguish "nothing flaky" from "filtered everything out".
      var msg = allFlaky.length ? "flkNoMatch" : "noFlaky";
      box.innerHTML = '<div class="fb-empty">' + esc(t(msg)) + "</div>";
      return;
    }
    box.innerHTML = rows.map(function (f) {
      return '<div class="fb-row" data-dag="' + esc(f.dag_id) + '" data-task="' + esc(f.task_id)
        + '" data-node="' + esc(f.node_id) + '"><span class="ostrip">'
        + (f.recent || []).map(outcomeDot).join("") + "</span>"
        + '<span class="fb-main"><span class="fb-node mono">' + esc(f.node_id) + "</span>"
        + '<span class="fb-sub"><span class="fb-dagtask">' + esc(f.dag_id + " · " + f.task_id)
        + "</span>" + quarantineBadge(f) + "</span></span>"
        + '<span class="fb-meta">' + flakyMeta(f) + "</span></div>";
    }).join("");
    box.querySelectorAll(".fb-row").forEach(function (row) {
      row.addEventListener("click", function () {
        openHistory(row.getAttribute("data-dag"), row.getAttribute("data-task"),
          row.getAttribute("data-node"));
      });
    });
  }
  function loadFlaky() {
    fetch(API + "flaky")
      .then(function (r) { return r.ok ? r.json() : { flaky: [] }; })
      .then(function (d) { allFlaky = d.flaky || []; renderFlakyBoard(); })
      .catch(function () { allFlaky = []; renderFlakyBoard(); });
  }
  var suggestVals = { dag_id: [], task_id: [], run_id: [] };
  function populateSuggestions() {
    var d = {}, ta = {}, r = {};
    allReports.forEach(function (x) { d[x.dag_id] = 1; ta[x.task_id] = 1; r[x.run_id] = 1; });
    suggestVals = {
      dag_id: Object.keys(d).sort(), task_id: Object.keys(ta).sort(), run_id: Object.keys(r).sort(),
    };
  }
  // Tidy autocomplete that drops neatly under the input. The native <datalist>
  // popup renders outside the sandboxed iframe with a detached system shadow.
  function bindSuggest(inputId, boxId, field) {
    var input = document.getElementById(inputId), box = document.getElementById(boxId);
    var active = -1;
    function opts() { return [].slice.call(box.querySelectorAll(".opt")); }
    function close() {
      box.hidden = true; box.innerHTML = ""; active = -1;
      input.setAttribute("aria-expanded", "false");
    }
    function render() {
      var q = input.value.trim().toLowerCase();
      var matches = (suggestVals[field] || []).filter(function (v) {
        var lv = v.toLowerCase(); return lv.indexOf(q) !== -1 && lv !== q;
      }).slice(0, 50);
      if (!matches.length) { close(); return; }
      box.innerHTML = matches.map(function (v) {
        return '<div class="opt" role="option">' + esc(v) + "</div>";
      }).join("");
      box.hidden = false; active = -1; input.setAttribute("aria-expanded", "true");
      box.querySelectorAll(".opt").forEach(function (o) {
        o.addEventListener("mousedown", function (e) {   // mousedown beats the input's blur
          e.preventDefault();
          input.value = o.textContent; close(); applyFilter();
        });
      });
    }
    input.addEventListener("input", render);
    input.addEventListener("focus", render);
    input.addEventListener("blur", function () { setTimeout(close, 120); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { close(); return; }
      var o = opts();
      if (e.key === "ArrowDown") { active = Math.min(active + 1, o.length - 1); }
      else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); }
      else if (e.key === "Enter") {
        if (active >= 0 && o[active]) {
          e.preventDefault(); input.value = o[active].textContent; close(); applyFilter();
        }
        return;
      } else { return; }
      e.preventDefault();
      o.forEach(function (x, i) { x.classList.toggle("active", i === active); });
      if (o[active]) o[active].scrollIntoView({ block: "nearest" });
    });
  }

  var dlg = document.getElementById("detail");
  var dBody = document.getElementById("d-body");
  var dTitle = document.getElementById("d-title");
  var detail = null, filter = "all", lastFocus = null, currentId = null;

  function outcomeLabel(o) { return t(o) || o; }

  // Success donut: clickable slices filter the case table by status.
  function donut(m) {
    var total = m.total || 0;
    var SW = 12, R = 50;       // thinner ring than before; r = 50
    var C = 2 * Math.PI * R;
    var ring = '<circle cx="60" cy="60" r="50" fill="none" stroke="var(--surface-2)" stroke-width="' + SW + '"/>';
    var segs = [["passed", "var(--pass)", m.passed], ["skipped", "var(--skip)", m.skipped],
                ["failed", "var(--fail)", m.failed], ["error", "var(--error)", m.errors]];
    // Gap between slices, > the round cap diameter so the caps never touch (single slice = no gap).
    var nSeg = segs.filter(function (s) { return (s[2] || 0) > 0; }).length;
    var GAP = nSeg > 1 ? SW + 5 : 0;
    var off = 0, parts = "";
    segs.forEach(function (s) {
      var v = s[2] || 0;
      if (total <= 0 || v <= 0) return;
      var len = (v / total) * C;
      var pct = Math.round((v / total) * 100);
      var lit = filter === "all" || filter === s[0];
      // Inset each slice by half the gap on both sides; round caps then sit clear of neighbours.
      var drawn = Math.max(len - GAP, 0.1);
      parts += '<circle class="dseg" data-status="' + s[0] + '" data-count="' + v
        + '" data-pct="' + pct + '" cx="60" cy="60" r="50" '
        + 'fill="none" stroke="' + s[1] + '" stroke-width="' + SW + '" stroke-dasharray="'
        + drawn.toFixed(2) + " " + (C - drawn).toFixed(2) + '" stroke-dashoffset="'
        + (-(off + GAP / 2)).toFixed(2) + '" opacity="' + (lit ? 1 : 0.3) + '"></circle>';
      off += len;
    });
    var pct = total > 0 ? Math.round((m.passed / total) * 100) : null;
    var ofN = esc(t("ofWord")) + " " + total;
    var center = '<text x="60" y="58" text-anchor="middle" class="donut-pct">'
      + (pct == null ? "—" : pct + "%") + "</text>"
      + '<text x="60" y="76" text-anchor="middle" class="donut-lbl">' + ofN + "</text>";
    return '<svg viewBox="0 0 120 120" class="donut" role="img" aria-label="'
      + (pct == null ? "" : pct + "% — ") + total + " " + esc(t("testsWord")) + '">'
      + '<g transform="rotate(-90 60 60)">' + ring + parts + "</g>" + center + "</svg>";
  }

  // Links back to the run's DAG / DAG run / task instance in the Airflow UI.
  function airflowLinks(m, prev) {
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
    if (prev) {
      var cmp = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
        + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + '<path d="M7 4 3 8l4 4M3 8h13M17 20l4-4-4-4M21 16H8"/></svg>';
      out += '<button type="button" class="af-link" id="cmp-prev" data-i18n-al="comparePrevAl">'
        + cmp + esc(t("comparePrev")) + "</button>";
    }
    var zap = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
      + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/></svg>';
    out += '<button type="button" class="af-link" id="flk-btn" data-i18n-al="flakyBtnAl">'
      + zap + esc(t("flakyBtn")) + "</button>";
    return out + "</div>";
  }
  function outcomeDot(o) {
    var col = { passed: "--pass", failed: "--fail", error: "--error", skipped: "--skip" }[o] || "--muted";
    return '<span class="od" style="background:var(' + col + ')" title="'
      + esc(o ? outcomeLabel(o) : t("histDidntRun")) + '"></span>';
  }
  // Flaky-deeper renderers, shared by the board and the detail modal.
  function trendArrow(tr) {
    var sym = { up: "↑", down: "↓", flat: "→" };
    var key = { up: "flkTrendUp", down: "flkTrendDown", flat: "flkTrendFlat" };
    var cls = tr === "up" ? "up" : tr === "down" ? "down" : "flat";
    return '<span class="flk-trend ' + cls + '" title="' + esc(t(key[tr] || "flkTrendFlat"))
      + '">' + (sym[tr] || "→") + "</span>";
  }
  function flakyMeta(f) {
    // flakiness score (flip rate, explained on hover) + trend + fail ratio
    return '<span class="flk-score" title="' + esc(t("flkScoreTip")) + '">'
      + Math.round((f.score || 0) * 100) + "%</span> " + trendArrow(f.trend)
      + " · " + f.fails + "/" + f.runs + " " + esc(t("flkFailed"));
  }
  function quarantineBadge(f) {
    return f.quarantined
      ? '<span class="flk-q" title="' + esc(t("flkQuarantineTip")) + '">' + esc(t("flkQuarantine")) + "</span>"
      : "";
  }
  // The most-recent earlier run of the same dag·task (for "compare to previous").
  function previousRun(rec) {
    if (!rec) return null;
    var sib = allReports.filter(function (x) {
      return x.dag_id === rec.dag_id && x.task_id === rec.task_id
        && String(x.created_at || "") < String(rec.created_at || "");
    });
    sib.sort(function (a, b) { return String(a.created_at || "") < String(b.created_at || "") ? 1 : -1; });
    return sib[0] || null;
  }

  function openInAirflow(href) {
    closeDetail();        // dismiss the modal...
    setParentDim(false);  // ...and drop its full-screen dim now (don't wait for the close event)
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

  // Case-table state (reset per opened report).
  var caseQuery = "", caseGroup = false, caseCollapsed = {};
  var HIST_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + '<path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/><path d="M12 7v5l3 2"/></svg>';
  function caseModule(node) {
    var i = node.lastIndexOf("::");
    return i > 0 ? node.slice(0, i) : node;
  }
  function caseRowHtml(c, i) {
    var kind = { passed: "pass", failed: "fail", error: "error", skipped: "skip" }[c.outcome] || "skip";
    var output = (c.message && c.message.trim()) ? c.message : t("noOutput");
    return '<tr class="case clickable" tabindex="0" role="button" aria-expanded="false" data-exp="' + i + '">'
      + "<td>" + badge(kind, outcomeLabel(c.outcome)) + "</td>"
      + '<td><span class="case-node mono">' + esc(c.node_id) + "</span></td>"
      + '<td class="num right">' + fmtDur(c.time) + "</td>"
      + '<td class="right"><span class="chev">' + CHEV + "</span></td></tr>"
      + '<tr class="case-exp" data-row="' + i + '" hidden><td colspan="4">'
      + '<button class="case-hist" type="button" data-hist="' + esc(c.node_id) + '">'
      + HIST_ICON + esc(t("historyBtn")) + "</button>"
      + '<pre class="tb mono">' + esc(output) + "</pre></td></tr>";
  }
  function setOutcomeFilter(k) {
    filter = k;
    dBody.querySelectorAll(".pill").forEach(function (p) {
      p.setAttribute("aria-pressed", String(p.getAttribute("data-f") === k));
    });
    // Re-light the donut to match (the table re-fills, but the donut isn't redrawn);
    // use the `opacity` attribute, not inline style, so the :hover rule still wins.
    dBody.querySelectorAll(".dseg").forEach(function (seg) {
      var s = seg.getAttribute("data-status");
      seg.setAttribute("opacity", k === "all" || k === s ? "1" : "0.3");
    });
    fillCases();
  }
  function fillCases() {
    var tb = dBody.querySelector(".case-table tbody");
    if (!tb || !detail) return;
    var q = caseQuery.trim().toLowerCase();
    var sel = [];
    detail.cases.forEach(function (c, idx) {
      if ((filter === "all" || c.outcome === filter)
          && (!q || c.node_id.toLowerCase().indexOf(q) !== -1)) sel.push({ c: c, i: idx });
    });
    if (!sel.length) {
      tb.innerHTML = '<tr><td colspan="4"><div class="state">' + esc(t("noCases")) + "</div></td></tr>";
      return;
    }
    if (caseGroup) {
      var groups = {};
      sel.forEach(function (o) {
        var mod = caseModule(o.c.node_id);
        (groups[mod] = groups[mod] || []).push(o);
      });
      tb.innerHTML = Object.keys(groups).sort().map(function (mod) {
        var coll = !!caseCollapsed[mod];
        var rot = coll ? "" : ' style="transform:rotate(90deg)"';
        var hd = '<tr class="grp" data-mod="' + esc(mod) + '"><td colspan="4">'
          + '<span class="chev"' + rot + ">" + CHEV + "</span> "
          + '<span class="mono">' + esc(mod) + '</span> <span class="muted">('
          + groups[mod].length + ")</span></td></tr>";
        return hd + (coll ? "" : groups[mod].map(function (o) { return caseRowHtml(o.c, o.i); }).join(""));
      }).join("");
    } else {
      tb.innerHTML = sel.map(function (o) { return caseRowHtml(o.c, o.i); }).join("");
    }
    wireCaseRows();
  }
  function wireCaseRows() {
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
    dBody.querySelectorAll(".case-hist").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        openHistory(detail.dag_id, detail.task_id, b.getAttribute("data-hist"));
      });
    });
    dBody.querySelectorAll("tr.grp").forEach(function (tr) {
      tr.addEventListener("click", function () {
        var mod = tr.getAttribute("data-mod");
        caseCollapsed[mod] = !caseCollapsed[mod];
        fillCases();
      });
    });
  }

  // Histogram of this run's test durations in 10s buckets; a drag/scroll carousel.
  function fillBench() {
    var box = document.getElementById("bench");
    if (!box || !detail) return;
    var BIN = 10, BAR = 86;
    var cases = detail.cases || [];
    var maxT = 0;
    cases.forEach(function (c) { var tm = +c.time || 0; if (tm > maxT) maxT = tm; });
    var nBins = Math.min(120, Math.max(1, Math.ceil((maxT + 1e-6) / BIN)));
    var bins = [];
    for (var i = 0; i < nBins; i++) bins.push(0);
    cases.forEach(function (c) {
      var b = Math.floor((+c.time || 0) / BIN);
      bins[b < 0 ? 0 : b >= nBins ? nBins - 1 : b]++;
    });
    var maxCount = Math.max.apply(null, bins.concat([1]));
    box.innerHTML = '<div class="bench-strip">' + bins.map(function (cnt, i) {
      var range = i * BIN + "–" + (i * BIN + BIN) + "s";
      var h = cnt ? Math.max(6, Math.round((cnt / maxCount) * BAR)) : 3;
      var col = cnt ? "var(--primary)" : "var(--surface-2)";
      // The whole column height is the hover target so every bucket (even empty) reacts.
      return '<div class="bench-col"><div class="bench-barwrap" data-range="' + esc(range)
        + '" data-cnt="' + cnt + '"><div class="bench-bar" style="height:' + h
        + "px;background:" + col + '"></div></div>'
        + '<div class="bench-x">' + esc(range) + "</div></div>";
    }).join("") + "</div>";
    // Same tooltip style as the runs chart (#tip + a coloured stat dot) -- Airflow canon.
    box.querySelectorAll(".bench-barwrap").forEach(function (w) {
      bindTip(w, function () {
        return '<div class="tt">' + esc(w.getAttribute("data-range")) + "</div>"
          + '<div class="tr">' + statDot("--primary", t("testsWord"), w.getAttribute("data-cnt")) + "</div>";
      });
    });
    enableChartDrag(box);
  }

  function renderDetail() {
    var m = detail;
    var counts = { all: m.cases.length, passed: 0, failed: 0, error: 0, skipped: 0 };
    m.cases.forEach(function (c) { if (counts[c.outcome] != null) counts[c.outcome]++; });
    dTitle.textContent = m.dag_id + " · " + m.task_id + " · " + t("tryWord") + " " + m.try_number;
    // Run number (#N), matching the chart bar and the list ID column.
    var rec = reports.filter(function (x) { return x.id === currentId; })[0];
    var prev = previousRun(rec);
    document.getElementById("d-seq").textContent = rec && rec.seq ? "#" + rec.seq : "";
    document.getElementById("d-allure").hidden = !m.has_allure;

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

    dBody.innerHTML = '<div class="detail-top">' + donut(m)
      + '<div class="kpis">' + kpis + "</div></div>"
      + airflowLinks(m, prev)
      + '<div class="card bench-card"><div class="chart-head"><span>' + esc(t("benchTitle"))
      + '</span></div><div class="bench-scroll" id="bench"></div></div>'
      + '<div class="pills">' + pills + "</div>"
      + '<div class="case-ctrls"><input id="case-q" class="case-q" type="text" placeholder="'
      + esc(t("caseSearch")) + '" autocomplete="off">'
      + '<label class="case-grp-lbl"><input type="checkbox" id="case-grp"> '
      + esc(t("caseGroup")) + "</label></div>"
      + '<div class="card table-wrap case-table"><table><thead><tr>'
      + "<th>" + esc(t("hOutcome")) + "</th><th>" + esc(t("hTest"))
      + '</th><th class="right">' + esc(t("hTime")) + "</th><th></th>"
      + "</tr></thead><tbody></tbody></table></div>";

    dBody.querySelectorAll(".pill").forEach(function (p) {
      p.addEventListener("click", function () { setOutcomeFilter(p.getAttribute("data-f")); });
    });
    // Airflow's iframe sandbox drops target="_top"/window.open (no top-navigation), but not
    // the History API on the same-origin parent -- so drive React Router. The real <a href>
    // stays so cmd/right-click still offers "open in new tab".
    dBody.querySelectorAll(".af-link[href]").forEach(function (a) {
      a.addEventListener("click", function (ev) { ev.preventDefault(); openInAirflow(a.getAttribute("href")); });
    });
    var cmpBtn = document.getElementById("cmp-prev");
    if (cmpBtn && prev && rec) cmpBtn.addEventListener("click", function () { openCompare(prev, rec); });
    var flkBtn = document.getElementById("flk-btn");
    if (flkBtn) flkBtn.addEventListener("click", function () { openFlaky(m.dag_id, m.task_id); });
    dBody.querySelectorAll(".dseg").forEach(function (seg) {
      seg.addEventListener("click", function () {
        var s = seg.getAttribute("data-status");
        setOutcomeFilter(filter === s ? "all" : s);
      });
      bindTip(seg, function () {
        return '<div class="tt">' + esc(outcomeLabel(seg.getAttribute("data-status")))
          + "</div>" + '<div class="tr"><span>' + seg.getAttribute("data-count")
          + " · " + seg.getAttribute("data-pct") + "%</span></div>";
      });
    });
    var qi = document.getElementById("case-q");
    qi.value = caseQuery;
    qi.addEventListener("input", function () { caseQuery = qi.value; fillCases(); });
    var grp = document.getElementById("case-grp");
    grp.checked = caseGroup;
    grp.addEventListener("change", function () { caseGroup = grp.checked; fillCases(); });
    fillBench();
    fillCases();
  }

  function openDetail(id) {
    filter = "all"; currentId = id;
    caseQuery = ""; caseGroup = false; caseCollapsed = {};
    lastFocus = document.activeElement;
    document.getElementById("d-copied").hidden = true;
    dBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    dTitle.textContent = t("loading");
    if (typeof dlg.showModal === "function") { if (!dlg.open) dlg.showModal(); }
    else dlg.setAttribute("open", "");
    updateParentDim();
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

  // Dim the WHOLE Airflow window (nav included) behind a modal, like Airflow's
  // own dialogs. Our <dialog> ::backdrop only covers the iframe, so when embedded
  // we drop a full-screen overlay into the parent and lift our iframe above it --
  // the iframe's own ::backdrop still dims the page around the dialog, so the dim
  // is seamless across both. Standalone needs nothing (::backdrop is the window).
  function setParentDim(on) {
    var fe = window.frameElement;        // our iframe in the parent (same-origin only)
    if (!fe) return;
    try {
      var pdoc = fe.ownerDocument, ID = "apx-modal-dim";
      var ov = pdoc.getElementById(ID);
      if (on) {
        if (!ov) {
          ov = pdoc.createElement("div");
          ov.id = ID;
          ov.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:2147483646;";
          (pdoc.body || pdoc.documentElement).appendChild(ov);
        }
        fe.style.position = "relative";
        fe.style.zIndex = "2147483647";
      } else {
        if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
        fe.style.zIndex = "";
        fe.style.position = "";
      }
    } catch (e) { /* cross-origin parent: skip */ }
  }
  function updateParentDim() {
    setParentDim((dlg && dlg.open) || (confirmDlg && confirmDlg.open)
      || (failuresDlg && failuresDlg.open) || (compareDlg && compareDlg.open)
      || (flakyDlg && flakyDlg.open) || (historyDlg && historyDlg.open)
      || (uniqueDlg && uniqueDlg.open));
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
  document.getElementById("d-allure").addEventListener("click", function () {
    if (currentId) downloadAllure(currentId);
  });
  document.getElementById("d-delete").addEventListener("click", function () {
    if (currentId) openConfirm([currentId], dTitle.textContent);
  });
  dlg.addEventListener("cancel", function () { detail = null; currentId = null; setReportParam(null); });
  dlg.addEventListener("close", function () {
    updateParentDim();
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  });
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
    updateParentDim();
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
  confirmDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(confirmDlg, closeConfirm);

  // Failed-tests modal: clicking the FAILURES KPI lists every failed/errored case
  // across the visible runs, paginated client-side at FAIL_PAGE per page.
  var failuresDlg = document.getElementById("failures");
  var flBody = document.getElementById("fl-body");
  var FAIL_PAGE = 100;
  var failuresData = [], failPage = 0, failCapped = false;

  function filterQuery() {
    var q = new URLSearchParams();
    var dag = document.getElementById("f-dag").value.trim();
    var task = document.getElementById("f-task").value.trim();
    var run = document.getElementById("f-run").value.trim();
    if (dag) q.set("dag_id", dag);
    if (task) q.set("task_id", task);
    if (run) q.set("run_id", run);
    var s = q.toString();
    return s ? "?" + s : "";
  }
  function openFailures() {
    if (typeof failuresDlg.showModal === "function") { if (!failuresDlg.open) failuresDlg.showModal(); }
    else failuresDlg.setAttribute("open", "");
    updateParentDim();
    flBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    fetch(API + "failures" + filterQuery())
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        failuresData = d.failures || []; failCapped = !!d.capped; failPage = 0; renderFailures();
      })
      .catch(function (e) {
        flBody.innerHTML = '<div class="state c-fail">' + esc(t("failuresFail") + e.message) + "</div>";
      });
  }
  function closeFailures() {
    if (failuresDlg.open) failuresDlg.close(); else failuresDlg.removeAttribute("open");
  }
  function renderFailures() {
    if (!failuresData.length) {
      flBody.innerHTML = '<div class="state">' + esc(t("noFailures")) + "</div>";
      return;
    }
    var pages = Math.ceil(failuresData.length / FAIL_PAGE);
    failPage = Math.max(0, Math.min(failPage, pages - 1));
    var slice = failuresData.slice(failPage * FAIL_PAGE, failPage * FAIL_PAGE + FAIL_PAGE);
    var rows = slice.map(function (f) {
      var kind = f.outcome === "error" ? "error" : "fail";
      var rec = reports.filter(function (x) { return x.id === f.id; })[0];
      var run = esc(f.dag_id) + " · " + esc(f.task_id) + (rec && rec.seq ? " · #" + rec.seq : "");
      return '<tr class="case clickable" tabindex="0" data-id="' + esc(f.id)
        + '" data-outcome="' + esc(f.outcome) + '">'
        + "<td>" + badge(kind, outcomeLabel(f.outcome)) + "</td>"
        + '<td><span class="case-node mono">' + esc(f.node_id) + "</span></td>"
        + '<td class="muted">' + run + "</td></tr>";
    }).join("");
    var cap = failCapped
      ? '<div class="state muted">' + esc(t("failCapped").replace("{n}", failuresData.length)) + "</div>" : "";
    var pager = pages > 1
      ? '<div class="pager"><button type="button" class="nav-btn" id="fl-prev"'
          + (failPage <= 0 ? " disabled" : "") + ' aria-label="' + esc(t("prevPage")) + '">‹</button>'
        + "<span>" + esc(t("page")) + " " + (failPage + 1) + " / " + pages + "</span>"
        + '<button type="button" class="nav-btn" id="fl-next"'
          + (failPage >= pages - 1 ? " disabled" : "") + ' aria-label="' + esc(t("nextPage")) + '">›</button></div>'
      : "";
    flBody.innerHTML = '<div class="card table-wrap case-table"><table><thead><tr>'
      + "<th>" + esc(t("hOutcome")) + "</th><th>" + esc(t("hTest")) + "</th><th>"
      + esc(t("cRun")) + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>" + cap + pager;
    flBody.querySelectorAll(".case").forEach(function (tr) {
      var open = function () {
        openDetail(tr.getAttribute("data-id"));      // resets filter to "all"...
        filter = tr.getAttribute("data-outcome");    // ...then land on the failing cases
        closeFailures();
      };
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
    });
    var p = document.getElementById("fl-prev"), n = document.getElementById("fl-next");
    if (p) p.addEventListener("click", function () { if (failPage > 0) { failPage--; renderFailures(); } });
    if (n) n.addEventListener("click", function () { if (failPage < pages - 1) { failPage++; renderFailures(); } });
  }
  document.getElementById("fl-close").addEventListener("click", closeFailures);
  failuresDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(failuresDlg, closeFailures);

  // Unique-tests list (opened from the KPI): client-side search + pagination. The
  // search input lives in a fixed shell so a re-render never steals its focus.
  var uniqueDlg = document.getElementById("unique");
  var uqBody = document.getElementById("uq-body");
  var UQ_PAGE = 100, uqPage = 0, uqQuery = "", uqCapped = false;
  var uqListSeq = 0;
  function openUnique() {
    uqPage = 0; uqQuery = "";
    if (typeof uniqueDlg.showModal === "function") { if (!uniqueDlg.open) uniqueDlg.showModal(); }
    else uniqueDlg.setAttribute("open", "");
    updateParentDim();
    uqBody.innerHTML = '<input id="uq-q" class="case-q" type="text" placeholder="'
      + esc(t("caseSearch")) + '" autocomplete="off" style="margin-bottom:12px">'
      + '<div id="uq-list"></div><div id="uq-pager"></div>';
    var qi = document.getElementById("uq-q");
    qi.addEventListener("input", function () { uqQuery = qi.value; uqPage = 0; fillUnique(); });
    loadUniqueList();
    qi.focus();
  }
  function loadUniqueList() {
    var listEl = document.getElementById("uq-list");
    if (listEl) {
      listEl.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    }
    var my = ++uqListSeq;
    fetch(API + "unique-tests?" + uniqueQuery("full"))
      .then(function (r) { return r.ok ? r.json() : { tests: [] }; })
      .then(function (d) {
        if (my !== uqListSeq || !uniqueDlg.open) return;
        uniqueTestsList = d.tests || []; uqCapped = !!d.capped; fillUnique();
      })
      .catch(function () {
        if (my === uqListSeq && uniqueDlg.open) { uniqueTestsList = []; fillUnique(); }
      });
  }
  function closeUnique() {
    if (uniqueDlg.open) uniqueDlg.close(); else uniqueDlg.removeAttribute("open");
  }
  function fillUnique() {
    var listEl = document.getElementById("uq-list");
    if (!listEl) return;
    var q = uqQuery.trim().toLowerCase();
    var rows = uniqueTestsList.filter(function (x) {
      return !q || x.node_id.toLowerCase().indexOf(q) !== -1;
    });
    var pages = Math.max(1, Math.ceil(rows.length / UQ_PAGE));
    uqPage = Math.max(0, Math.min(uqPage, pages - 1));
    var slice = rows.slice(uqPage * UQ_PAGE, uqPage * UQ_PAGE + UQ_PAGE);
    listEl.innerHTML = slice.length
      ? slice.map(function (x) {
          return '<div class="uq-row" tabindex="0" role="button" data-dag="' + esc(x.dag_id)
            + '" data-task="' + esc(x.task_id) + '" data-node="' + esc(x.node_id) + '">'
            + '<span class="mono">' + esc(x.node_id) + "</span></div>";
        }).join("")
      : '<div class="state">' + esc(t("noCases")) + "</div>";
    listEl.querySelectorAll(".uq-row").forEach(function (row) {
      var open = function () {
        openHistory(row.getAttribute("data-dag"), row.getAttribute("data-task"),
          row.getAttribute("data-node"));
      };
      row.addEventListener("click", open);
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
    });
    var cnt = (uqCapped ? "≥" : "") + rows.length + " " + esc(t("testsWord"));
    document.getElementById("uq-pager").innerHTML = pages > 1
      ? '<div class="pager"><button type="button" class="nav-btn" id="uq-prev"'
          + (uqPage <= 0 ? " disabled" : "") + ' aria-label="' + esc(t("prevPage")) + '">‹</button>'
        + "<span>" + esc(t("page")) + " " + (uqPage + 1) + " / " + pages + " · " + cnt + "</span>"
        + '<button type="button" class="nav-btn" id="uq-next"'
          + (uqPage >= pages - 1 ? " disabled" : "") + ' aria-label="' + esc(t("nextPage")) + '">›</button></div>'
      : '<div class="pager"><span>' + cnt + "</span></div>";
    var p = document.getElementById("uq-prev"), n = document.getElementById("uq-next");
    if (p) p.addEventListener("click", function () { if (uqPage > 0) { uqPage--; fillUnique(); } });
    if (n) n.addEventListener("click", function () { if (uqPage < pages - 1) { uqPage++; fillUnique(); } });
  }
  document.getElementById("uq-close").addEventListener("click", closeUnique);
  uniqueDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(uniqueDlg, closeUnique);

  // Compare modal: per-test diff vs the previous run of the same dag·task.
  var compareDlg = document.getElementById("compare");
  var cmpBody = document.getElementById("cmp-body");
  var CMP_SECS = [
    ["newly_failed", "--fail"], ["fixed", "--pass"], ["still_failing", "--error"],
    ["added", "--skip"], ["removed", "--muted"],
  ];
  function openCompare(baseRec, headRec) {
    if (typeof compareDlg.showModal === "function") { if (!compareDlg.open) compareDlg.showModal(); }
    else compareDlg.setAttribute("open", "");
    updateParentDim();
    document.getElementById("cmp-title").textContent =
      t("compareTitle") + " · #" + (baseRec.seq || "?") + " → #" + (headRec.seq || "?");
    cmpBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    fetch(API + "compare?base=" + encodeURIComponent(baseRec.id)
      + "&head=" + encodeURIComponent(headRec.id))
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(renderCompare)
      .catch(function (e) {
        cmpBody.innerHTML = '<div class="state c-fail">' + esc(t("compareFail") + e.message) + "</div>";
      });
  }
  function closeCompare() {
    if (compareDlg.open) compareDlg.close(); else compareDlg.removeAttribute("open");
  }
  function renderCompare(d) {
    var any = CMP_SECS.some(function (s) { return (d[s[0]] || []).length; });
    if (!any) { cmpBody.innerHTML = '<div class="state">' + esc(t("compareNoChange")) + "</div>"; return; }
    cmpBody.innerHTML = CMP_SECS.map(function (s) {
      var rows = d[s[0]] || [];
      if (!rows.length) return "";
      var items = rows.map(function (r) {
        var chg = r.base && r.head
          ? esc(outcomeLabel(r.base)) + " → " + esc(outcomeLabel(r.head))
          : esc(outcomeLabel(r.outcome || ""));
        return '<li><span class="node mono">' + esc(r.node_id)
          + '</span><span class="chg">' + chg + "</span></li>";
      }).join("");
      return '<div class="cmp-sec"><h3><span class="dot" style="background:var(' + s[1] + ')"></span>'
        + esc(t("cmp_" + s[0])) + " (" + rows.length + ')</h3><ul class="cmp-list">' + items + "</ul></div>";
    }).join("");
  }
  document.getElementById("cmp-close").addEventListener("click", closeCompare);
  compareDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(compareDlg, closeCompare);

  // Flaky tests for one dag·task: score/trend/quarantine, a window selector, and a
  // quarantined-only filter. The controls live in a fixed shell; only the list re-renders.
  var flakyDlg = document.getElementById("flaky");
  var fkBody = document.getElementById("fk-body");
  var FLK_WINDOWS = [10, 30, 50, 100, 200];
  var fkState = { dag: null, task: null, window: 30, qOnly: false, rows: [] };
  function openFlaky(dag, task) {
    fkState.dag = dag; fkState.task = task; fkState.window = 30; fkState.qOnly = false;
    if (typeof flakyDlg.showModal === "function") { if (!flakyDlg.open) flakyDlg.showModal(); }
    else flakyDlg.setAttribute("open", "");
    updateParentDim();
    fkBody.innerHTML = '<div class="flk-ctrls"><label title="' + esc(t("flkWindowTip")) + '">'
      + esc(t("flkWindow")) + ' <select id="flk-win">'
      + FLK_WINDOWS.map(function (w) {
          return '<option value="' + w + '"' + (w === fkState.window ? " selected" : "") + ">"
            + esc(t("flkWinOpt").replace("{n}", w)) + "</option>";
        }).join("")
      + "</select></label><label><input type=\"checkbox\" id=\"flk-qonly\"> "
      + esc(t("flkQuarantinedOnly")) + "</label></div><div id=\"flk-list\"></div>";
    document.getElementById("flk-win").addEventListener("change", function () {
      fkState.window = +this.value; loadFlakyModal();
    });
    document.getElementById("flk-qonly").addEventListener("change", function () {
      fkState.qOnly = this.checked; fillFlakyRows();
    });
    loadFlakyModal();
  }
  function loadFlakyModal() {
    var listEl = document.getElementById("flk-list");
    if (listEl) {
      listEl.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    }
    var q = new URLSearchParams({
      dag_id: fkState.dag, task_id: fkState.task, window: String(fkState.window),
    });
    fetch(API + "flaky?" + q.toString())
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { fkState.rows = d.flaky || []; fillFlakyRows(); })
      .catch(function (e) {
        var el = document.getElementById("flk-list");
        if (el) el.innerHTML = '<div class="state c-fail">' + esc(t("flakyFail") + e.message) + "</div>";
      });
  }
  function fillFlakyRows() {
    var listEl = document.getElementById("flk-list");
    if (!listEl) return;
    var rows = fkState.qOnly
      ? fkState.rows.filter(function (f) { return f.quarantined; })
      : fkState.rows;
    if (!rows.length) {
      listEl.innerHTML = '<div class="state">' + esc(t("noFlaky")) + "</div>";
      return;
    }
    listEl.innerHTML = rows.map(function (f) {
      return '<div class="fk-row"><span class="ostrip">'
        + (f.recent || []).map(outcomeDot).join("") + "</span>"
        + '<span class="node mono">' + esc(f.node_id) + quarantineBadge(f) + "</span>"
        + '<span class="fk-meta">' + flakyMeta(f) + "</span></div>";
    }).join("");
  }
  function closeFlaky() { if (flakyDlg.open) flakyDlg.close(); else flakyDlg.removeAttribute("open"); }
  document.getElementById("fk-close").addEventListener("click", closeFlaky);
  flakyDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(flakyDlg, closeFlaky);

  // Test history: one test's outcome + duration across the runs of its dag·task.
  var historyDlg = document.getElementById("history");
  var histBody = document.getElementById("hist-body");
  function openHistory(dag, task, node) {
    if (typeof historyDlg.showModal === "function") { if (!historyDlg.open) historyDlg.showModal(); }
    else historyDlg.setAttribute("open", "");
    updateParentDim();
    histBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    var q = new URLSearchParams({ dag_id: dag, task_id: task, node_id: node });
    fetch(API + "test-history?" + q.toString())
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(renderHistory)
      .catch(function (e) {
        histBody.innerHTML = '<div class="state c-fail">' + esc(t("historyFail") + e.message) + "</div>";
      });
  }
  function closeHistory() { if (historyDlg.open) historyDlg.close(); else historyDlg.removeAttribute("open"); }
  function renderHistory(d) {
    var rows = d.history || [];
    var head = '<div class="hist-node mono">' + esc(d.node_id) + "</div>";
    if (!rows.length) { histBody.innerHTML = head + '<div class="state">' + esc(t("noHistory")) + "</div>"; return; }
    histBody.innerHTML = head + rows.map(function (h) {
      var label = h.outcome ? outcomeLabel(h.outcome) : t("histDidntRun");
      var dur = h.duration != null ? fmtDur(h.duration) : "";
      return '<div class="hist-row">' + outcomeDot(h.outcome)
        + '<span class="when">' + esc(label) + " · " + esc(fmtTime(h.created_at)) + "</span>"
        + '<span class="dur">' + esc(dur) + "</span></div>";
    }).join("");
  }
  document.getElementById("hist-close").addEventListener("click", closeHistory);
  historyDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(historyDlg, closeHistory);

  document.getElementById("refresh").addEventListener("click", load);
  // Links menu: GitHub + the FastAPI docs. Airflow's iframe sandbox blocks _blank
  // from inside, so open the tab from the same-origin parent; standalone uses ours.
  var linksBtn = document.getElementById("links-btn");
  var linksMenu = document.getElementById("links-menu");
  function closeLinksMenu() {
    linksMenu.hidden = true;
    linksBtn.setAttribute("aria-expanded", "false");
  }
  linksBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    var willOpen = linksMenu.hidden;
    linksMenu.hidden = !willOpen;
    linksBtn.setAttribute("aria-expanded", String(willOpen));
  });
  linksMenu.querySelectorAll(".menu-item").forEach(function (item) {
    item.addEventListener("click", function () {
      var href = item.getAttribute("data-href") || API + item.getAttribute("data-api");
      (sameOriginTop() || window).open(href, "_blank", "noopener");
      closeLinksMenu();
    });
  });
  document.addEventListener("click", function (e) {
    if (!linksMenu.hidden && !linksBtn.contains(e.target) && !linksMenu.contains(e.target)) {
      closeLinksMenu();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !linksMenu.hidden) closeLinksMenu();
  });
  document.addEventListener("pointermove", chartDragMove);
  document.addEventListener("pointerup", chartDragEnd);
  document.addEventListener("pointercancel", chartDragEnd);
  ["f-dag", "f-task", "f-run"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", applyFilter);
  });
  // Flaky-panel search + quarantined-only filter: client-side, re-render in place.
  var flkBoardQ = document.getElementById("flk-board-q");
  if (flkBoardQ) flkBoardQ.addEventListener("input", renderFlakyBoard);
  var flkBoardQOnly = document.getElementById("flk-board-qonly");
  if (flkBoardQOnly) flkBoardQOnly.addEventListener("change", renderFlakyBoard);
  var trendToggle = document.getElementById("trend-toggle");
  if (trendToggle) trendToggle.addEventListener("change", function () {
    passTrend = this.checked; renderChart();
  });
  bindSuggest("f-dag", "sg-dag", "dag_id");
  bindSuggest("f-task", "sg-task", "task_id");
  bindSuggest("f-run", "sg-run", "run_id");
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
