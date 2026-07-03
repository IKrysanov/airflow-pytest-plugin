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
    --surface-glass: #ffffffc7;  /* translucent surface so a chip doesn't fully hide data */
    --fg: #18181b; --muted: #52525b; --border: #e4e4e7;
    --primary: #017cee; --on-primary: #ffffff; --ring: #017cee40;
    --pass: #008000; --fail: #ff0000; --skip: #ff69b4; --error: #9370db;
    --pass-bg: #0080001a; --fail-bg: #ff00001a; --skip-bg: #ff69b41f; --error-bg: #9370db1f;
    --warn: #a16207; --warn-bg: #fef08a;  /* amber "flaky" warning chip (readable on yellow) */
    --trend: #0891b2;  /* cyan pass-rate trend line (darker for contrast on white) */
    --thresh: #d97706;  /* amber success-threshold (label text -- must stay readable) */
    --thresh-soft: #d9770659;  /* muted amber for the gridline so it recedes behind data */
    --shadow: 0 1px 2px #0000000d, 0 1px 3px #00000014;
    /* Tooltip inverts the page: dark bubble on the light theme. */
    --tip-bg: #18181b; --tip-fg: #fafafa; --tip-border: #3f3f46;
  }
  html[data-theme="dark"] {
    --bg: #07121e; --surface: #1c2a3a; --surface-2: #243651;
    --surface-glass: #1c2a3ac7;  /* translucent surface so a chip doesn't fully hide data */
    --fg: #e6edf3; --muted: #94a3b8; --border: #2c4262;
    --primary: #4ba3f5; --on-primary: #07121e; --ring: #017cee66;
    --pass: #2ecc71; --fail: #ff6b6b; --skip: #ff8ecb; --error: #b39ddb;
    --pass-bg: #2ecc711f; --fail-bg: #ff6b6b1f; --skip-bg: #ff8ecb1f; --error-bg: #b39ddb1f;
    --warn: #fcd34d; --warn-bg: #fcd34d2e;  /* amber "flaky" warning chip on the dark theme */
    --trend: #22d3ee;  /* cyan pass-rate trend line (brighter on the navy theme) */
    --thresh: #fbbf24;  /* amber success-threshold (label text -- must stay readable) */
    --thresh-soft: #fbbf2459;  /* muted amber for the gridline so it recedes behind data */
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
  /* "all" chip: marks a KPI that counts every run in view, ignoring a group selection. */
  .kpi-all { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 999px;
    background: var(--surface-2); border: 1px solid var(--border); color: var(--muted);
    font-size: 9.5px; font-weight: 700; letter-spacing: .04em; vertical-align: middle; }
  .kpi .value { font-size: 26px; font-weight: 700; margin-top: 4px; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    overflow: hidden; box-shadow: var(--shadow); }
  .chart-card { margin-bottom: 18px; padding: 14px 16px 8px; }
  .chart-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
  /* Runs chart header in two fixed rows so controls don't reflow/jump on resize:
     row 1 = title + legend (+reset); row 2 = trend toggle (left) + carousel arrows (right). */
  .chart-head-stack { flex-direction: column; align-items: stretch; gap: 8px; }
  .chart-head-stack .chart-head-row { display: flex; align-items: center; gap: 12px;
    flex-wrap: wrap; min-width: 0; }
  /* Right cluster (window range + carousel arrows) hugs the right edge, and drops to
     its own line on narrow widths instead of overflowing -- fully adaptive. */
  .chart-meta-right { margin-left: auto; display: inline-flex; align-items: center;
    gap: 8px; min-width: 0; }
  /* Visible-window range "#48-#76 / 76" and average pass rate "avg 92%": quiet,
     tabular figures so the numbers don't jiggle while scrolling. */
  .chart-range, .chart-avg { font-size: 12px; font-weight: 500; color: var(--muted);
    white-space: nowrap; font-variant-numeric: tabular-nums; }
  .chart-range b { color: var(--fg); font-weight: 600; }
  .chart-avg b { color: var(--fg); font-weight: 700; }
  .chart-avg.below b { color: var(--fail); }  /* window dips under the success threshold */
  /* "Showing N selected · show all" note when ticked runs filter the chart. */
  .chart-filter { display: inline-flex; align-items: center; gap: 8px; font-weight: 500;
    color: var(--primary); }
  .chart-clear { border: 0; background: none; color: var(--primary); cursor: pointer;
    font: inherit; font-weight: 600; text-decoration: underline; padding: 0; }
  .chart-clear:hover { opacity: .8; }
  .chart-clear:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; border-radius: 3px; }
  /* "scoped to the selected group(s)" chip on the flaky panel -- mirrors the chart's
     selection so picking a group filters BOTH the chart and the flaky list. */
  .flk-scope { font-size: 11px; font-weight: 600; color: var(--primary);
    background: var(--ring); padding: 1px 8px; border-radius: 999px; }
  /* Pass-rate trend: checkbox toggle + the cyan line/dots/threshold overlay. */
  .trend-toggle { display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
    font-weight: 500; white-space: nowrap; color: var(--muted); }
  #chart { position: relative; }
  .trend-svg { position: absolute; left: 0; top: 0; pointer-events: none; overflow: visible; }
  .trend-line { fill: none; stroke: var(--trend); stroke-width: 2;
    stroke-linejoin: round; stroke-linecap: round; }
  .trend-dot { fill: var(--trend); stroke: var(--surface); stroke-width: 1.5;
    pointer-events: auto; cursor: pointer; }
  /* Stretches of the pass-rate line below the success threshold turn red (signal). */
  .trend-line.trend-danger { stroke: var(--fail); }
  .trend-dot.trend-dot-bad { fill: var(--fail); }
  /* A quiet reference line: thin, muted amber so it sits behind the bars + trend line
     (the data), not over them. The small % chip stays readable in full amber. */
  .trend-thresh { position: absolute; left: 0; right: 0; pointer-events: none;
    border-top: 1px dashed var(--thresh-soft); }
  /* Glass chip: translucent + blurred so it never fully hides a trend dot behind it,
     yet the % text stays crisp (only the backdrop is blurred). pointer-events:none on
     the parent already lets dot clicks pass through. */
  .trend-thresh span { position: absolute; right: 2px; top: -9px; font-size: 10px;
    font-weight: 600; color: var(--thresh); background: var(--surface-glass);
    -webkit-backdrop-filter: blur(2px); backdrop-filter: blur(2px); padding: 0 5px;
    border-radius: 4px; box-shadow: 0 0 0 1px var(--thresh-soft); }
  .trend-thresh.label-below span { top: 3px; }  /* high threshold -> label under the line */
  .legend { display: inline-flex; gap: 6px; flex-wrap: wrap; }
  .legend button { display: inline-flex; align-items: center; gap: 5px; border: 0;
    background: none; color: var(--fg); cursor: pointer; font: inherit; font-weight: 500;
    padding: 3px 7px; border-radius: 999px; transition: opacity .12s, background .12s; }
  .legend button:hover { background: var(--surface-2); }
  .legend button:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .legend button.off { opacity: .4; text-decoration: line-through; }
  .legend .leg-reset { color: var(--primary); font-size: 12px; }
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
    background: var(--surface-2); transition: opacity .12s; cursor: pointer; }
  /* Hover = an even outline ring, NOT a brightness/colour change: sweeping across many narrow
     bars must not make their fill colours flicker/"jump". An INTEGER 2px spread keeps the ring
     the same crisp thickness on every edge (a fractional px anti-aliases unevenly). */
  .bar:hover { box-shadow: 0 0 0 2px var(--fg); }
  /* With the trend on, bars recede so the line/threshold read clearly; hovering one
     brings it back to full strength. */
  .bars-strip.trend-on .bar { opacity: .26; }
  .bars-strip.trend-on .bar:hover { opacity: 1; }
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
  /* Tooltip text stays single-line (ellipsised) so the tooltip is a FIXED height as the
     cursor sweeps bars -- wrapping made the status dots jump up/down between bars. */
  #tip .tt, #tip .tm { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #tip .tt { font-weight: 650; font-size: 13px; }
  #tip .tm { opacity: .72; }
  /* The heatmap tooltip alone wraps its long node_id line (full id is the point there). */
  #tip .tm.wrap { white-space: normal; overflow: visible; overflow-wrap: anywhere; text-overflow: clip; }
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
  /* Fill the card (which stretches to the radar's height next to it) and scroll INSIDE it, so
     the flaky list runs to the very bottom of the panel instead of stopping at a fixed cap.
     min-height:0 lets the flex child shrink so overflow scrolls; capped only when stacked. */
  .flaky-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto;
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
  /* Reliability radar (pentagon): the 3rd main-board dashboard. Its own row UNDER the
     full-width chart, sharing that row 50/50 with the flaky panel (both are .board > .card).
     The SVG has a wide viewBox and scales to the card, so labels never spill on small screens. */
  .pentagon-card { padding: 14px 16px; display: flex; flex-direction: column; }
  /* Both cards on this row share a fixed height (driven by the radar's size) so the flaky
     list scrolls INSIDE its card down to the bottom of the panel -- and can't stretch the
     row to fit all rows. Height is released on mobile (cards stack + size to content). */
  #board2 > .card { height: 384px; }
  /* The radar FILLS its card (no max-width cap): the SVG stretches to the card and the wide
     viewBox scales the pentagon to fit by height, so it's as large as the card allows and
     shrinks proportionally with the screen. */
  #pentagon { flex: 1 1 auto; min-height: 0; }
  .rel-svg { display: block; width: 100%; height: 100%; }
  .rel-grid { fill: none; stroke: var(--border); stroke-width: 1; }
  .rel-area { fill: color-mix(in srgb, var(--primary) 20%, transparent);
    stroke: var(--primary); stroke-width: 2; stroke-linejoin: round; }
  .rel-dot { fill: var(--primary); }
  .rel-lab { fill: var(--muted); font-size: 11px; }
  .rel-val { fill: var(--fg); font-weight: 700; }
  .rel-score { fill: var(--fg); font-weight: 700; font-size: 21px;
    font-variant-numeric: tabular-nums; }
  .rel-score-cap { fill: var(--muted); font-size: 8.5px; text-transform: uppercase;
    letter-spacing: .05em; }
  /* Run-health trend: a compact sparkline of per-run health over time, under the radar.
     A short footer so it never crowds the radar (the card grows to fit both). */
  .rel-trend { display: flex; align-items: center; gap: 12px; flex: 0 0 auto;
    padding-top: 9px; margin-top: 7px; border-top: 1px solid var(--border); }
  .rt-meta { display: flex; align-items: baseline; gap: 7px; flex: 0 0 auto; }
  .rt-label { color: var(--muted); font-size: 10.5px; text-transform: uppercase;
    letter-spacing: .05em; }
  .rt-now { font-weight: 700; font-size: 16px; color: var(--fg); font-variant-numeric: tabular-nums; }
  .rt-delta { font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .rt-delta.rt-up { color: var(--pass); }
  .rt-delta.rt-down { color: var(--fail); }
  .rt-delta.rt-flat { color: var(--muted); }
  /* Non-uniform scale (preserveAspectRatio=none) makes the line fill the width; the
     non-scaling stroke keeps it an even 2px everywhere (no thickness "walk"). */
  .rt-graph { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
  .rt-spark { width: 100%; height: 30px; display: block; }
  /* The line's time axis: dates of the first and last run in view. */
  .rt-axis { display: flex; justify-content: space-between; color: var(--muted);
    font-size: 10px; margin-top: 2px; font-variant-numeric: tabular-nums; }
  .rt-line { fill: none; stroke: var(--primary); stroke-width: 2; stroke-linejoin: round;
    stroke-linecap: round; vector-effect: non-scaling-stroke; }
  .rt-fill { fill: color-mix(in srgb, var(--primary) 14%, transparent); stroke: none; }
  .rt-hint { color: var(--muted); font-size: 12px; }
  /* Info (ⓘ) button by the Reliability title -> the "how it's computed" popup. */
  .rel-info-btn { display: inline-flex; align-items: center; justify-content: center; padding: 0;
    margin-left: 6px; border: 0; background: none; color: var(--muted); cursor: pointer; }
  .rel-info-btn svg { width: 16px; height: 16px; }
  .rel-info-btn:hover { color: var(--primary); }
  .rel-info-btn:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; border-radius: 50%; }
  .rel-info-intro { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
  .rel-info-list { list-style: none; margin: 0; padding: 0; display: flex;
    flex-direction: column; gap: 12px; }
  .rel-info-list li { border-left: 2px solid var(--primary); padding: 2px 0 2px 12px; }
  .ri-head { display: flex; align-items: baseline; gap: 8px; }
  .ri-name { font-weight: 650; }
  .ri-val { color: var(--primary); font-weight: 700; font-variant-numeric: tabular-nums; }
  .ri-desc { display: block; color: var(--muted); font-size: 12.5px; margin-top: 2px; }
  /* Stacked board: cards size to their content (the row layout's flex:1 1 0 would
     collapse them to a sliver in a column, hiding the chart/flaky behind overflow). */
  @media (max-width: 860px) {
    .board { flex-direction: column; }
    .board > .card { flex: 0 0 auto; }
    /* Stacked (content-sized cards): release the shared height, cap the flaky list instead. */
    #board2 > .card { height: auto; }
    .flaky-scroll { max-height: 300px; }
  }
  /* Unique-tests list: one wrapping column, so a long node id never forces a
     horizontal scrollbar (the dialog body scrolls vertically). */
  .uq-row { padding: 9px 4px; border-bottom: 1px solid var(--border); cursor: pointer;
    font-size: 12.5px; overflow-wrap: anywhere; }
  .uq-row:last-child { border-bottom: 0; }
  .uq-row:hover { background: var(--surface-2); }
  .uq-row:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
  .uq-node { display: block; }
  /* Per-test stats line under the node id: runs, avg time, per-outcome counts. */
  .uq-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px;
    margin-top: 5px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .uq-meta .uq-tot { font-weight: 600; color: var(--fg); }
  .uq-meta .uq-st { display: inline-flex; align-items: center; gap: 4px; }
  .uq-meta .od { width: 9px; height: 9px; border-radius: 2px; }

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
  .af-link svg { width: 13px; height: 13px; color: var(--muted); flex: 0 0 auto; }
  .af-link { max-width: 100%; }
  /* Narrow screens: the toolbar wraps (flex-wrap) AND its chips compact, so however many
     actions a run accumulates they never collide or overflow the dialog. */
  @media (max-width: 640px) {
    .af-links { gap: 6px; }
    .af-link { padding: 4px 7px; font-size: 12px; gap: 4px; }
    .af-link svg { width: 12px; height: 12px; }
  }

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
  /* Email-this-run dialog: a labelled recipients field + a status line. */
  #email-dlg .cbody { display: flex; flex-direction: column; gap: 6px; }
  .em-label { font-weight: 650; font-size: 13px; }
  /* .case-q is flex:1 1 220px; in this flex COLUMN that basis becomes height -> pin it. */
  #email-dlg .case-q { width: 100%; box-sizing: border-box; flex: 0 0 auto; height: 34px; max-width: none; }
  .em-hint { color: var(--muted); font-size: 12px; }
  .em-status { font-size: 13px; margin-top: 4px; }
  .em-status.ok { color: var(--pass); }
  .em-status.err { color: var(--fail); }
  #email-dlg .cactions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 12px; }
  #em-send { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }

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
  .sel-cell input[type="checkbox"], #case-grp, #flk-qonly, #flk-board-qonly, #trend-toggle, #list-grp {
    appearance: none; -webkit-appearance: none; margin: 0; width: 16px; height: 16px;
    cursor: pointer; vertical-align: middle; background: var(--surface);
    border: 1px solid var(--border); border-radius: 4px; flex: 0 0 auto;
    display: inline-grid; place-content: center; transition: background .12s, border-color .12s; }
  .sel-cell input[type="checkbox"]:hover, #case-grp:hover, #flk-qonly:hover,
  #flk-board-qonly:hover, #trend-toggle:hover, #list-grp:hover { border-color: var(--primary); }
  .sel-cell input[type="checkbox"]:focus-visible, #case-grp:focus-visible, #flk-qonly:focus-visible,
  #flk-board-qonly:focus-visible, #trend-toggle:focus-visible, #list-grp:focus-visible {
    outline: 2px solid var(--ring); outline-offset: 1px; }
  .sel-cell input[type="checkbox"]:checked, #case-grp:checked, #flk-qonly:checked,
  #flk-board-qonly:checked, #trend-toggle:checked, #list-grp:checked,
  .sel-cell input[type="checkbox"]:indeterminate {
    background: var(--primary); border-color: var(--primary); }
  .sel-cell input[type="checkbox"]:checked::after, #case-grp:checked::after, #flk-qonly:checked::after,
  #flk-board-qonly:checked::after, #trend-toggle:checked::after, #list-grp:checked::after {
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
  th.sortable, th.gsort, th.rsort { cursor: pointer; }
  th.sortable:hover, th.gsort:hover, th.rsort:hover { color: var(--fg); }
  /* Run-list headers: ONLY the label text (.th-lab) sorts -- the empty cell space around it
     is not clickable. The <th> shows a default cursor; the label carries the pointer/hover. */
  #list th.sortable, #list th.gsort, #list th.rsort { cursor: default; }
  /* Hovering the empty cell space must NOT highlight the label: keep the th muted (inherit
     would resolve to --fg and darken the word). Only .th-lab:hover below highlights it. */
  #list th.sortable:hover, #list th.gsort:hover, #list th.rsort:hover { color: var(--muted); }
  .th-lab { display: inline-flex; align-items: center; gap: 4px; vertical-align: middle;
    cursor: pointer; }
  .th-lab:hover { color: var(--fg); }
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
  #flaky, #history, #compare, #failures, #rel-info, #panel-info {
    max-width: min(680px, 84vw); max-height: 82vh; }
  /* The email form is small; keep it clearly inset from the run dialog's frame. */
  #email-dlg { max-width: min(460px, 84vw); max-height: 82vh; }
  /* The email-send log is a narrow list, also inset from the run dialog. */
  #alerts-dlg { max-width: min(560px, 84vw); max-height: 82vh; }
  .al-row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 4px;
    border-bottom: 1px solid var(--border); font-size: 13px; }
  .al-row:last-child { border-bottom: 0; }
  .al-ok { color: var(--pass); font-weight: 700; flex: 0 0 auto; }
  .al-fail { color: var(--fail); font-weight: 700; flex: 0 0 auto; }
  .al-main { flex: 1 1 auto; min-width: 0; }
  .al-rcpts { overflow-wrap: anywhere; }
  .al-meta { color: var(--muted); font-size: 12px; margin-top: 2px; }
  /* Count chip inside the toolbar "Emails" button. */
  .af-count { background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 999px; padding: 0 7px; font-size: 11px; font-weight: 700;
    font-variant-numeric: tabular-nums; }
  #panel-info-body p { margin: 0; color: var(--fg); font-size: 13.5px; line-height: 1.6; }
  /* The heatmap wants width (more run columns visible). Wide when opened on its own;
     inset (narrower than the run dialog) when opened from inside a run, so it doesn't
     touch the run dialog's frame. */
  #heatmap { max-width: min(1040px, 92vw); max-height: 88vh; }
  #heatmap.hm-inset { max-width: min(880px, 86vw); max-height: 82vh; }
  /* The dim comes from ONE shared full-screen overlay (updateParentDim), not per-dialog, so
     stacking a popup on top of the run detail doesn't double-darken. The ::backdrop stays
     (transparent) only to keep click-outside-to-close working. */
  dialog::backdrop { background: transparent; }
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
  /* A long test id WRAPS so the whole row (incl. the Time column) stays visible without
     horizontal scrolling -- the node column takes the slack and grows taller, not wider.
     (Overrides the global `td { white-space: nowrap }`, which would block wrapping.) */
  .case-node { display: inline-block; white-space: normal; overflow-wrap: anywhere; }
  .case-table { overflow-x: auto; }
  /* border-collapse:separate so the frozen (sticky) outcome column keeps its OWN
     borders -- with collapse, a sticky cell's borders belong to the table and get
     painted over, so the column's row lines vanished and the header doubled up.
     Each cell carries only border-bottom (+ the divider on the first cell), so the
     lines are single and aligned across all columns. */
  .case-table table { width: 100%;
    border-collapse: separate; border-spacing: 0; }
  .case.clickable[aria-expanded="true"] { background: var(--surface-2); }
  .case-table thead th:first-child,
  .case-table tr.case > td:first-child { position: sticky; left: 0;
    border-right: 1px solid var(--border); }
  .case-table tr.case > td:first-child { background: var(--surface); z-index: 1; }
  .case-table tr.case.clickable:hover > td:first-child,
  .case-table tr.case[aria-expanded="true"] > td:first-child { background: var(--surface-2); }
  .case-table thead th:first-child { z-index: 3; }
  .chev { display: inline-flex; width: 16px; justify-content: center; color: var(--muted);
    transition: transform .15s; }
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
  /* Flaky row mirrors the main-page board: the name takes a full-width line (wraps if long),
     the quarantine badge sits on its OWN line UNDER it -- never colliding with the name. */
  .fk-row { align-items: flex-start; }
  .fk-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .fk-main .node { overflow-wrap: anywhere; }
  .fk-sub { display: flex; }
  .hist-row .when { flex: 1 1 auto; overflow-wrap: anywhere; }
  .hist-row .when { color: var(--muted); }
  .hist-row .hist-loc { color: var(--primary); font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; font-size: .92em; }
  .fk-row .fk-meta, .hist-row .dur { color: var(--muted); white-space: nowrap;
    font-variant-numeric: tabular-nums; }
  /* Test-history node header wraps so a long node id never scrolls horizontally. */
  .hist-node { overflow-wrap: anywhere; color: var(--muted); margin-bottom: 4px; }
  .hist-count { color: var(--muted); font-size: 11.5px; margin-bottom: 8px; }
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
  /* Slow/regression modal: two sections (got-slower, slowest) of node·loc·metric rows. */
  .slow-sec { margin-bottom: 18px; }
  .slow-sec h3 { font-size: 13px; font-weight: 650; margin: 0 0 6px;
    display: flex; align-items: center; gap: 6px; }
  .slow-row { display: flex; align-items: baseline; gap: 10px; padding: 9px 0;
    border-bottom: 1px solid var(--border); font-size: 12.5px; }
  .slow-row:last-child { border-bottom: 0; }
  .slow-row .node { flex: 1 1 auto; overflow-wrap: anywhere; }
  .slow-loc { flex: 0 1 auto; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; max-width: 38%; }
  .slow-meta { flex: 0 0 auto; color: var(--muted); white-space: nowrap;
    font-variant-numeric: tabular-nums; }
  .slow-meta b { color: var(--fg); }
  .slow-up, .slow-ratio { color: var(--fail); font-weight: 700; }
  /* Error clusters: a count·signature row that expands to its failing tests. */
  .cl-row { display: flex; align-items: center; gap: 10px; padding: 10px 4px; cursor: pointer;
    border-bottom: 1px solid var(--border); font-size: 12.5px; }
  .cl-row:hover { background: var(--surface-2); }
  .cl-row:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
  .cl-count { flex: 0 0 auto; min-width: 38px; font-weight: 700; color: var(--fail);
    font-variant-numeric: tabular-nums; }
  .cl-sig { flex: 1 1 auto; overflow-wrap: anywhere; }
  .cl-dots { flex: 0 0 auto; display: inline-flex; gap: 3px; }
  /* flex:0 0 auto so the status square keeps its 9x9 even when a long test name wraps to
     several lines (otherwise the flex row squeezes it). align-self:start keeps it on line 1. */
  .cl-dots .od, .cl-item .od { flex: 0 0 auto; align-self: flex-start; width: 9px; height: 9px;
    border-radius: 2px; }
  .cl-row .chev { flex: 0 0 auto; transition: transform .15s; }
  .cl-row[aria-expanded="true"] .chev { transform: rotate(90deg); }
  /* Tests inside an expanded cluster: clearly separated rows that highlight on hover
     and read as links (mono in primary) so it's obvious they open the test. */
  /* Nested under a cluster: a left accent (like the run list's expanded groups), not a
     big indent gap. */
  .cl-items { border-left: 2px solid var(--primary); margin: 0 0 6px; }
  .cl-item { display: flex; align-items: center; gap: 8px; padding: 7px 8px 7px 12px;
    cursor: pointer; font-size: 12px; overflow-wrap: anywhere;
    border-bottom: 1px solid var(--border); }
  .cl-item:last-child { border-bottom: 0; }
  .cl-item:hover { background: var(--surface-2); }
  .cl-item:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
  .cl-item .mono { color: var(--primary); }
  .cl-item .muted { margin-left: auto; white-space: nowrap; }
  /* Test×run heatmap: a FIXED test-name column + a horizontally-scrolling cell pane (a
     carousel like the runs chart). The two are separate columns, so the cells slide
     within their pane and can never ride over the names. The name column is fit-content
     (capped) -- it shrinks to the names (no wasted indent) and only grows, shifting the
     map right, when a name is long. Both grids share row heights + gap, so rows stay
     aligned as the dialog body scrolls vertically. */
  /* Name column is capped (adaptive to the dialog width) so one very long test id can't
     stretch it and open a big empty gap on the left -- long names ellipsis-truncate instead. */
  .hm-wrap { display: grid; grid-template-columns: fit-content(clamp(100px, 22vw, 160px)) 1fr;
    align-items: start; --hm-cell: 22px; --hm-head: 16px; --hm-gap: 3px;
    /* grid-line colour == the regular UI border/divider colour (adaptive per theme); the 3px
       rounded gaps keep the cells clearly separated without the line itself standing out. */
    --hm-grid: var(--border); }
  .hm-names { display: grid; gap: var(--hm-gap); min-width: 0; }
  .hm-scroll { overflow-x: auto; overflow-y: hidden; padding: 0 6px 6px; cursor: grab; }
  .hm-scroll.dragging { cursor: grabbing; }
  /* The run-number row floats ABOVE the map (own transparent grid, same columns + gaps so it
     lines up), with no boxes/lines around the numbers. Its height + the names' corner both
     equal --hm-head, and the map's own top frame follows, so name rows still align with cells. */
  .hm-headrow { display: grid; gap: var(--hm-gap); padding: 0 var(--hm-gap); width: max-content; }
  .hm-rhead { height: var(--hm-head); display: flex; align-items: flex-end; justify-content: center;
    overflow: hidden; font-size: var(--hm-rhead-fs, 9px); color: var(--muted);
    white-space: nowrap; font-variant-numeric: tabular-nums; }
  /* A real grid: the container is painted with the grid-line colour and every cell is inset
     from it by an EQUAL gap on all four sides -- the same value drives both `gap` (interior
     lines) and `padding` (the outer frame), so spacing is identical everywhere and the top/
     bottom/side borders are never eaten. Rounded container + rounded cells. */
  .hm-cells { display: grid; gap: var(--hm-gap); padding: var(--hm-gap); width: max-content;
    background: var(--hm-grid); border-radius: 8px; }
  .hm-corner { height: var(--hm-head); }
  .hm-name { all: unset; box-sizing: border-box; height: var(--hm-cell); display: flex;
    align-items: center; justify-content: flex-end; min-width: 0; padding-right: 10px;
    white-space: nowrap; overflow: hidden; font-size: 11.5px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--primary); cursor: pointer; }
  .hm-name > span { overflow: hidden; text-overflow: ellipsis; }
  .hm-name:hover { text-decoration: underline; }
  .hm-name:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .hm-cell { width: var(--hm-cell); height: var(--hm-cell); display: block; border-radius: 5px;
    cursor: pointer; transition: opacity .12s, filter .1s; }
  .hm-miss { background: var(--surface); cursor: default; }  /* empty grid cell = didn't run */
  /* Hover highlight (map cells only -- NOT the legend swatches) stays ENTIRELY INSIDE the cell:
     an inset ring + a brightness lift. Because nothing is drawn outside the border-box and the
     cell isn't lifted over its neighbours, it can't reach into the 3px gaps or squeeze the
     adjacent squares -- every cell keeps its exact size and the highlight looks identical on
     all of them. A white inset ring reads clearly on any status colour, in both themes. */
  .hm-cells .hm-cell:not(.hm-miss):hover { filter: brightness(1.22);
    box-shadow: inset 0 0 0 2px rgba(255, 255, 255, .92), inset 0 0 0 3px rgba(0, 0, 0, .35); }
  /* Legend = a status focus filter, like the runs-chart legend: focusing a status dims
     the other cells (the .foc-<code> container classes drive it -- no per-cell work). */
  .hm-cells.foc .hm-cell:not(.hm-miss) { opacity: .12; }
  .hm-cells.foc.foc-p .hm-cell[data-o="p"], .hm-cells.foc.foc-f .hm-cell[data-o="f"],
  .hm-cells.foc.foc-e .hm-cell[data-o="e"], .hm-cells.foc.foc-s .hm-cell[data-o="s"] { opacity: 1; }
  .hm-legend { display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
    margin-top: 14px; font-size: 12px; color: var(--muted); }
  .hm-lg { display: inline-flex; align-items: center; gap: 6px; border: 0; background: none;
    color: inherit; font: inherit; padding: 4px 8px; border-radius: 7px; }
  button.hm-lg { cursor: pointer; }
  button.hm-lg:hover { background: var(--surface-2); }
  button.hm-lg:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  button.hm-lg.off { opacity: .4; text-decoration: line-through; }
  .hm-lg .hm-cell { width: 13px; height: 13px; cursor: inherit; transition: none;
    border-radius: 3px; }
  .hm-lg .hm-miss { background: transparent; border: 1px dashed var(--border);
    box-sizing: border-box; }  /* legend swatch keeps the dashed "didn't run" look */
  .hm-reset { border: 0; background: none; color: var(--primary); font: inherit;
    font-size: 12px; cursor: pointer; padding: 4px 8px; }
  .hm-note { margin-top: 8px; font-size: 12px; color: var(--muted); }
  /* Briefly highlight the case a heatmap cell jumped to in the run detail. */
  tr.case.case-focus > td { background: var(--ring); }
  /* Sortable case-table headers reuse the run-list's th.sortable + .arrow styling;
     TIME right-aligns over its values and defaults to slowest-first. */
  .case-table th.sortable { white-space: nowrap; user-select: none; }
  .case-table th.right { text-align: right; }
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
  /* Run-list grouping by dag·task: toggle control + collapsible group headers. */
  .list-ctrls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 10px 12px; }
  .list-grp-lbl { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px;
    color: var(--muted); cursor: pointer; white-space: nowrap; }
  #list .table-wrap > table { width: 100%; }
  tr.lgrp > td { background: var(--surface-2); font-weight: 600; cursor: pointer; user-select: none; }
  tr.lgrp .chev { transition: transform .15s; }
  /* Flaky warning chip -- shown only on groups that actually have flaky tests. Amber/yellow
     with a warning triangle; clicking it scopes the board (chart + flaky panel) to the group. */
  .lgrp-flk { display: inline-flex; align-items: center; gap: 3px; margin-left: 8px;
    padding: 1px 8px 1px 6px; border: 1px solid color-mix(in srgb, var(--warn) 45%, transparent);
    border-radius: 999px; background: var(--warn-bg); color: var(--warn); font-size: 11px;
    font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.6; cursor: pointer;
    vertical-align: middle; }
  .lgrp-flk svg { width: 12px; height: 12px; }
  .lgrp-flk:hover { background: color-mix(in srgb, var(--warn) 26%, var(--warn-bg)); }
  .lgrp-flk:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  /* WHEN is the last column and shrinks to its content (width:1% on the th) so the date and
     its heatmap button stay snug together at the row's right edge -- the leftover width goes
     to the wide DAG/TASK identity columns instead of opening a hole between the date and the
     button. The date is left-aligned so the "When" header still sits right over it. */
  th.gcol-when { width: 1%; }
  /* Keep the cell a real table-cell so its bottom border (the row separator) stays continuous
     to the right edge -- `display:flex` on a <td> drops that border. The flex lives on an
     inner wrapper instead, which lays out the date + heatmap button snugly. */
  td.lgrp-when { white-space: nowrap; }
  .lgrp-when-in { display: flex; align-items: center; }
  .lgrp-hm { margin-left: 8px; flex: 0 0 auto; display: inline-flex; padding: 3px;
    background: none; border: 0; border-radius: 6px; color: var(--muted); cursor: pointer; }
  .lgrp-hm svg { width: 15px; height: 15px; }
  .lgrp-hm:hover { color: var(--primary); background: var(--border); }
  .lgrp-hm:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  /* Align the grouped "DAG" header over the dag name (clears the chevron's footprint). */
  th.gcol-dag { padding-left: 32px; }
  /* A group's runs sit in their own full sub-table, marked by a left accent rather
     than an indent gap (which looked off). */
  tr.grp-runs > td { padding: 0; border-left: 2px solid var(--primary); background: var(--surface); }
  tr.grp-more td { color: var(--muted); font-size: 12px; text-align: center; padding: 8px; }

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
    <button id="f-clear" class="btn icon-btn" type="button" data-i18n-al="clearFilters" hidden>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
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
      <div class="chart-head chart-head-stack">
        <div class="chart-head-row">
          <span data-i18n="history">Recent runs</span>
          <button id="chart-info" class="rel-info-btn" type="button" data-i18n-al="chartInfoAl"
            title="About the runs chart">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
          </button>
          <span class="chart-filter" id="chart-filter" hidden></span>
          <span class="legend" id="legend"></span>
        </div>
        <div class="chart-head-row chart-head-row2">
          <label class="trend-toggle"><input type="checkbox" id="trend-toggle" />
            <span data-i18n="trendToggle">Pass-rate trend</span></label>
          <span class="chart-avg" id="chart-avg" hidden></span>
          <span class="chart-meta-right">
            <span class="chart-range" id="chart-range"></span>
            <span class="chart-nav" id="chart-nav"></span>
          </span>
        </div>
      </div>
      <div id="chart"></div>
    </div>
  </div>
  <div class="board" id="board2" hidden>
    <div class="card pentagon-card" id="pentagon-card">
      <div class="chart-head">
        <span data-i18n="reliabilityTitle">Reliability</span>
        <button id="rel-info-btn" class="rel-info-btn" type="button" data-i18n-al="reliabilityInfoAl"
          title="How the score is computed">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
        </button>
        <span class="flk-scope" id="rel-scope" hidden></span>
      </div>
      <div id="pentagon"></div>
      <div id="rel-trend" class="rel-trend"></div>
    </div>
    <div class="card flaky-card" id="flaky-card" hidden>
      <div class="chart-head">
        <span data-i18n="flakyTitle">Flaky tests</span>
        <button id="flaky-info" class="rel-info-btn" type="button" data-i18n-al="flakyInfoAl"
          title="About flaky tests">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
        </button>
        <span class="flk-scope" id="flk-scope" hidden></span>
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
    <button id="d-email" class="btn icon-btn" type="button" hidden data-i18n-al="emailRun" title="Email">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>
      </svg>
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

<dialog id="email-dlg" aria-labelledby="em-title">
  <div class="dlg-head"><h2 id="em-title" data-i18n="emailTitle">Email this run</h2></div>
  <div class="dlg-body">
    <div class="cbody">
      <label for="em-to" class="em-label" data-i18n="emailToLabel">Recipients</label>
      <input id="em-to" class="case-q" type="text" autocomplete="off" inputmode="email"
        data-i18n-ph="emailToPh" placeholder="name@example.com, other@example.com" />
      <div class="em-hint" data-i18n="emailHint">Comma-separated. Leave empty to use the configured recipients.</div>
      <div class="em-status" id="em-status" hidden></div>
    </div>
    <div class="cactions">
      <button id="em-cancel" class="btn" type="button" data-i18n="cancel">Cancel</button>
      <button id="em-send" class="btn" type="button" data-i18n="emailSend">Send</button>
    </div>
  </div>
</dialog>

<dialog id="alerts-dlg" aria-labelledby="al-title">
  <div class="dlg-head">
    <h2 id="al-title" data-i18n="alertsTitle">Email notifications</h2>
    <span style="flex:1"></span>
    <button id="al-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body"><div id="al-list"></div></div>
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

<dialog id="slow" aria-labelledby="sl-title">
  <div class="dlg-head">
    <h2 id="sl-title" data-i18n="slowTitle">Slow tests &amp; regressions</h2>
    <span class="grow" style="flex:1"></span>
    <button id="sl-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="sl-body"></div>
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

<dialog id="rel-info" aria-labelledby="rel-info-title">
  <div class="dlg-head">
    <h2 id="rel-info-title" data-i18n="relInfoTitle">How the reliability score is computed</h2>
    <span class="grow" style="flex:1"></span>
    <button id="rel-info-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="rel-info-body"></div>
</dialog>

<dialog id="panel-info" aria-labelledby="panel-info-title">
  <div class="dlg-head">
    <h2 id="panel-info-title"></h2>
    <span class="grow" style="flex:1"></span>
    <button id="panel-info-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="panel-info-body"></div>
</dialog>

<dialog id="heatmap" aria-labelledby="hm-title">
  <div class="dlg-head">
    <h2 id="hm-title" data-i18n="heatmapTitle">Test×run heatmap</h2>
    <span class="grow" style="flex:1"></span>
    <button id="hm-close" class="btn icon-btn" type="button" data-i18n-al="closeReport">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="hm-body"></div>
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
      legendReset: "Reset filter", clearFilters: "Clear filters",
      trendToggle: "Pass-rate trend", passRate: "pass rate",
      closeReport: "Close report", ofWord: "of", testsWord: "tests",
      avgWord: "avg", uqRuns: "Total runs",
      apiDocs: "API docs", linksAl: "Links & documentation", ghItem: "GitHub",
      benchTitle: "Test durations (10s buckets)", uniqueTitle: "Unique tests",
      reliabilityTitle: "Reliability", reliabilityHint: "higher is better", relOverall: "score",
      relPass: "Pass rate", relRobust: "No errors", relFresh: "Green now",
      relStable: "Stability", relComplete: "Completeness",
      reliabilityInfoAl: "How the reliability score is computed",
      relInfoTitle: "How the reliability score is computed",
      relInfoIntro: "Each axis is scored 0–100 over the runs currently in view (the top filters "
        + "and any group selection apply). Higher is better; the centre is the average of the five.",
      relPassDesc: "Average of each run's pass rate, across every run in view — the same "
        + "value as the chart's “avg pass rate”.",
      relRobustDesc: "Share of results that are NOT errors (a test crashing or its setup failing).",
      relFreshDesc: "Share of dag·tasks whose LATEST run cleared the success threshold.",
      relStableDesc: "Share of tests that are NOT flaky — that don't flip pass↔fail over the window.",
      relCompleteDesc: "Share of tests that actually ran (were not skipped).",
      relTrend: "Run health", relTrendCollecting: "Collecting data…",
      relTrendVs: "Change: the recent half of the runs vs the older half",
      relTrendNowTip: "Current run health — the value at the right edge of the line",
      relTrendDesc: "The line under the radar tracks run health over time, oldest run on the left "
        + "to the newest on the right — the dates under the line show the span. Per run, health is "
        + "the mean of the three continuous axes (pass rate, no errors, completeness), drawn as a "
        + "moving average so it reads as a trend. The big number is the CURRENT health (the line's "
        + "right edge); the arrow is the recent half's change vs the older half. Green-now and "
        + "Flaky/Stability are radar-only snapshots, so they're not in the line.",
      cId: "ID", cStatus: "Status", cDag: "DAG", cTask: "Task", cRun: "Run", cTry: "Try",
      cTotal: "Total", cPass: "Pass", cFail: "Fail", cErr: "Err", cSkip: "Skip",
      cDuration: "Duration", cWhen: "When", cRuns: "Runs", cPassRate: "Pass %", cAvgDur: "Avg time",
      kRuns: "Runs", kPassingRuns: "Passing runs", kTests: "Unique tests", kFailures: "Failures",
      kAll: "all", kAllTip: "Counts every run in view — not narrowed by a group selection",
      chartInfoAl: "About the runs chart", flakyInfoAl: "About flaky tests",
      chartInfoTitle: "Recent runs chart",
      chartInfoBody: "One bar per run, stacked by outcome (passed / failed / error / skipped), "
        + "oldest → newest. Drag, swipe or use the arrows to scroll the carousel. Tick runs in "
        + "the list to focus the chart on them. Turn on “Pass-rate trend” for a line through each "
        + "run's pass rate with a dashed success-threshold gridline; the header then shows the "
        + "visible run window (e.g. #48–#76 / 76) and its average pass rate.",
      flakyInfoTitle: "Flaky tests",
      flakyInfoBody: "Tests that BOTH pass and fail across the recent window of one dag·task. "
        + "Score = how often the result flips (0–1); trend compares the recent half to the older "
        + "half; a test is quarantined once its score clears the threshold. Use the search box or "
        + "the “Quarantined only” toggle to narrow the list; a row opens that test's history. "
        + "Flakiness is per dag·task — the same test run from two tasks can differ.",
      kFailuresTip: "Tests failing in the latest run of each dag·task (drops off when fixed)",
      kPassed: "Passed", kFailed: "Failed", kErrors: "Errors", kSkipped: "Skipped",
      sPass: "PASS", sFail: "FAIL", sError: "ERROR", success: "success",
      passed: "passed", failed: "failed", error: "error", skipped: "skipped", all: "all",
      hOutcome: "Outcome", hTest: "Test", hTime: "Time",
      afDag: "DAG", afRun: "Run", afTask: "Task", downloadAllure: "Allure results",
      loading: "Loading…", noOutput: "No output captured.",
      noMatch: "No reports match the current filter.",
      noReports: "No reports found yet. Run a PytestOperator task with ArchivingResultParser to populate this view.",
      noCases: "No matching cases.", tryWord: "try",
      failuresTitle: "Failures by error", noFailures: "No failed tests.",
      clBtn: "Error clusters", clBtnAl: "Error clusters in this run",
      compareTitle: "Compare", comparePrev: "Compare to previous",
      comparePrevAl: "Compare to the previous run", compareFail: "Failed to compare: ",
      compareNoChange: "No differences from the previous run.",
      cmp_newly_failed: "Newly failed", cmp_fixed: "Fixed", cmp_still_failing: "Still failing",
      cmp_added: "Added", cmp_removed: "Removed",
      flakyTitle: "Flaky tests", flakyBtn: "Flaky tests",
      flakyBtnAl: "Flaky tests in recent runs", flakyFail: "Failed to load flaky tests: ",
      heatmapTitle: "Test×run heatmap", heatmapBtn: "Heatmap",
      heatmapBtnAl: "Test×run outcome heatmap for this dag·task",
      heatmapFail: "Failed to load heatmap: ", heatmapEmpty: "No runs to chart yet.",
      heatmapTrunc: "Showing the {m} most-broken of {n} tests.",
      noFlaky: "No flaky tests in the recent runs.", flkFailed: "failed",
      flkGroupWarn: "Flaky tests in this group — click to focus the board on it",
      flkSearch: "filter flaky tests…", flkNoMatch: "No flaky tests match the filter.",
      flkSelScope: "selected groups", flkNoSel: "No flaky tests in the selected groups.",
      flkWindow: "Analysis window:", flkWinOpt: "last {n} runs",
      flkWindowTip: "How many recent runs of this dag·task to scan for flakiness",
      flkQuarantinedOnly: "Quarantined only",
      flkQuarantine: "quarantine", flkQuarantineTip: "Flaky enough to quarantine",
      flkScoreTip: "Flakiness: how often the result flips between pass and fail",
      flkTrendUp: "Flaking more lately", flkTrendDown: "Calming down",
      flkTrendFlat: "Steady trend",
      slowTitle: "Test execution time — slowdowns & slowest", kSlow: "Slowdowns",
      slowKpiTip: "Tests whose execution time got slower in recent runs",
      slowFail: "Failed to load slow tests: ",
      slowRegressing: "Got slower (execution time)", slowSlowest: "Slowest tests (avg time)",
      slowNoneReg: "No tests have slowed down in the recent runs.",
      slowNoData: "Not enough run history yet.",
      historyTitle: "Test history", historyBtn: "History",
      historyFail: "Failed to load history: ", noHistory: "No history for this test.",
      histDidntRun: "did not run", histCount: "over the last {n} runs",
      caseSearch: "filter tests…", caseGroup: "Group by module",
      listGroup: "Group by dag·task", runsWord: "runs", selectGroup: "Select group",
      groupMore: "Showing 100 of {n} runs — filter to this dag·task to see all.",
      failCapped: "Showing the first {n} failures.",
      loadFail: "Failed to load reports: ", reportFail: "Failed to load report: ",
      failuresFail: "Failed to load failures: ",
      deleteReport: "Delete report", deleteTitle: "Delete report?",
      deleteTitleN: "Delete {n} reports?",
      deleteConfirm: "This permanently removes the report and its files everywhere.",
      cancel: "Cancel", delete: "Delete", deleting: "Deleting…",
      emailRun: "Email this run", emailTitle: "Email this run", emailToLabel: "Recipients",
      emailToPh: "name@example.com, other@example.com",
      emailHint: "Comma-separated. Leave empty to use the configured recipients.",
      emailSend: "Send", emailSending: "Sending…", emailSent: "Sent ✓",
      emailFail: "Couldn't send the email.",
      emailInvalid: "Invalid email address: “{a}”. Use name@example.com",
      alertsBtn: "Emails", alertsBtnAl: "Email notifications sent for this run",
      alertsTitle: "Email notifications", alertsSentOk: "delivered",
      alertsSentFail: "send failed", alertsAuto: "automatic", alertsManual: "manual",
      alertsEmpty: "No emails were sent for this run.",
      deleteFail: "Failed to delete: ",
      deleteFailedN: "{n} could not be deleted (no permission).",
      nSelected: "{n} selected", deleteSelected: "Delete", clearSel: "Clear",
      selectRow: "Select row", selectAll: "Select all",
      forbidden: "You don't have permission to delete this report (it requires permission to trigger the DAG).",
      older: "Older runs", newer: "Newer runs",
      avgPass: "avg", avgPassTip: "Average pass rate across all {n} runs in the chart (matches the radar)",
      visibleRuns: "Showing runs #{a}–#{b} of {n}",
      prevPage: "Previous page", nextPage: "Next page", page: "Page",
    },
    ru: {
      title: "Pytest Reports", brand: "Pytest-отчёты", refresh: "Обновить",
      filterDag: "фильтр dag_id", filterTask: "фильтр task_id", filterRun: "фильтр run_id",
      filterDagAl: "Фильтр по dag_id", filterTaskAl: "Фильтр по task_id", filterRunAl: "Фильтр по run_id",
      history: "Последние прогоны", copyLink: "Копировать ссылку", copied: "Скопировано",
      chartSelected: "показаны выбранные: {n}", chartShowAll: "показать все",
      legendReset: "Сброс фильтра", clearFilters: "Сбросить фильтры",
      trendToggle: "Тренд прохождения", passRate: "доля прохождения",
      closeReport: "Закрыть отчёт", ofWord: "из", testsWord: "тестов",
      avgWord: "сред.", uqRuns: "Всего прогонов",
      apiDocs: "Документация API", linksAl: "Ссылки и документация", ghItem: "GitHub",
      benchTitle: "Время выполнения тестов (по 10с)", uniqueTitle: "Уникальные тесты",
      reliabilityTitle: "Надёжность", reliabilityHint: "больше — лучше", relOverall: "оценка",
      relPass: "Проходимость", relRobust: "Без ошибок", relFresh: "Сейчас зелёные",
      relStable: "Стабильность", relComplete: "Полнота",
      reliabilityInfoAl: "Как считается оценка надёжности",
      relInfoTitle: "Как считается оценка надёжности",
      relInfoIntro: "Каждая ось — 0–100 по прогонам в поле зрения (учитываются верхние фильтры "
        + "и выделение групп). Больше — лучше; в центре — среднее из пяти.",
      relPassDesc: "Средняя доля прохождения по каждому прогону, по всем прогонам в поле "
        + "зрения — то же значение, что «ср. прохождение» в диаграмме.",
      relRobustDesc: "Доля результатов без ошибок (падение теста или сбой его настройки).",
      relFreshDesc: "Доля dag·task, чей ПОСЛЕДНИЙ прогон прошёл порог успеха.",
      relStableDesc: "Доля тестов, которые НЕ нестабильны — не скачут pass↔fail в окне.",
      relCompleteDesc: "Доля тестов, которые реально выполнились (не были пропущены).",
      relTrend: "Здоровье прогонов", relTrendCollecting: "Собираем данные…",
      relTrendVs: "Изменение: недавняя половина прогонов против ранней",
      relTrendNowTip: "Текущее здоровье прогонов — значение у правого края линии",
      relTrendDesc: "Линия под радаром показывает здоровье прогонов во времени: слева самый старый "
        + "прогон, справа самый новый — даты под линией показывают период. Здоровье прогона — "
        + "среднее трёх непрерывных осей (доля прохождения, отсутствие ошибок, полнота), "
        + "нарисованное скользящим средним, чтобы читалось как тренд. Большое число — ТЕКУЩЕЕ "
        + "здоровье (правый край линии); стрелка — изменение недавней половины против ранней. "
        + "«Зелёный» и Нестабильность — снимки только на радаре, в линию не входят.",
      cId: "ID", cStatus: "Статус", cDag: "DAG", cTask: "Задача", cRun: "Запуск", cTry: "Попытка",
      cTotal: "Всего", cPass: "Усп", cFail: "Пров", cErr: "Ошиб", cSkip: "Проп",
      cDuration: "Время", cWhen: "Когда", cRuns: "Прогоны", cPassRate: "Проход %", cAvgDur: "Ср. время",
      kRuns: "Прогонов", kPassingRuns: "Успешных прогонов", kTests: "Уникальные тесты", kFailures: "Падений",
      kAll: "все", kAllTip: "Считает все прогоны в поле зрения — не сужается выбором группы",
      chartInfoAl: "О диаграмме прогонов", flakyInfoAl: "О нестабильных тестах",
      chartInfoTitle: "Диаграмма последних прогонов",
      chartInfoBody: "Один столбец — один прогон, с накоплением по статусам (passed / failed / "
        + "error / skipped), от старых к новым. Прокрутка — перетаскиванием, свайпом или "
        + "стрелками. Отметьте прогоны в списке, чтобы сфокусировать диаграмму на них. Включите "
        + "«Тренд прохождения» — появится линия по доле прохождения каждого прогона и пунктирный "
        + "порог успеха; в шапке — видимое окно (напр. #48–#76 / 76) и средняя доля прохождения.",
      flakyInfoTitle: "Нестабильные тесты",
      flakyInfoBody: "Тесты, которые в окне последних прогонов одного dag·task И проходят, И "
        + "падают. Score — как часто результат скачет (0–1); тренд сравнивает свежую половину "
        + "со старой; тест уходит в карантин, когда score превышает порог. Сузить список — поиском "
        + "или тумблером «Только карантин»; строка открывает историю теста. Нестабильность "
        + "считается по каждому dag·task — один тест из разных тасок может отличаться.",
      kFailuresTip: "Тесты, падающие в последнем прогоне каждого dag·task (уходят после починки)",
      kPassed: "Пройдено", kFailed: "Провалено", kErrors: "Ошибки", kSkipped: "Пропущено",
      sPass: "OK", sFail: "СБОЙ", sError: "ОШИБКА", success: "успех",
      passed: "пройден", failed: "провален", error: "ошибка", skipped: "пропущен", all: "все",
      hOutcome: "Итог", hTest: "Тест", hTime: "Время",
      afDag: "DAG", afRun: "Запуск", afTask: "Задача", downloadAllure: "Allure-отчёт",
      loading: "Загрузка…", noOutput: "Вывод не захвачен.",
      noMatch: "Нет отчётов под текущий фильтр.",
      noReports: "Отчётов пока нет. Запусти задачу PytestOperator с ArchivingResultParser, чтобы они появились здесь.",
      noCases: "Нет подходящих тестов.", tryWord: "попытка",
      failuresTitle: "Падения по ошибкам", noFailures: "Проваленных тестов нет.",
      clBtn: "Кластеры ошибок", clBtnAl: "Кластеры ошибок в этом прогоне",
      compareTitle: "Сравнение", comparePrev: "Сравнить с предыдущим",
      comparePrevAl: "Сравнить с предыдущим прогоном", compareFail: "Не удалось сравнить: ",
      compareNoChange: "Отличий от предыдущего прогона нет.",
      cmp_newly_failed: "Новые падения", cmp_fixed: "Починены", cmp_still_failing: "Всё ещё падают",
      cmp_added: "Добавлены", cmp_removed: "Удалены",
      flakyTitle: "Нестабильные тесты", flakyBtn: "Нестабильные",
      flakyBtnAl: "Нестабильные тесты за последние прогоны", flakyFail: "Не удалось загрузить: ",
      heatmapTitle: "Тепловая карта тест×прогон", heatmapBtn: "Тепловая карта",
      heatmapBtnAl: "Тепловая карта исходов тест×прогон для этого dag·task",
      heatmapFail: "Не удалось загрузить тепловую карту: ",
      heatmapEmpty: "Пока нет прогонов для карты.",
      heatmapTrunc: "Показаны {m} самых проблемных из {n} тестов.",
      noFlaky: "Нестабильных тестов за последние прогоны нет.", flkFailed: "падений",
      flkGroupWarn: "В этой группе есть нестабильные тесты — нажмите, чтобы сфокусироваться",
      flkSearch: "поиск нестабильных тестов…",
      flkNoMatch: "Под фильтр не попал ни один нестабильный тест.",
      flkSelScope: "выбранные группы",
      flkNoSel: "В выбранных группах нет нестабильных тестов.",
      flkWindow: "Окно анализа:", flkWinOpt: "последние {n} прогонов",
      flkWindowTip: "Сколько последних прогонов этого dag·task сканировать на нестабильность",
      flkQuarantinedOnly: "Только карантин",
      flkQuarantine: "карантин", flkQuarantineTip: "Достаточно нестабилен для карантина",
      flkScoreTip: "Нестабильность: как часто результат скачет между pass и fail",
      flkTrendUp: "Стал чаще флакать", flkTrendDown: "Стабилизируется",
      flkTrendFlat: "Тренд ровный",
      slowTitle: "Время выполнения тестов — замедления и самые медленные", kSlow: "Замедления",
      slowKpiTip: "Тесты, чьё время выполнения выросло за последние прогоны",
      slowFail: "Не удалось загрузить медленные тесты: ",
      slowRegressing: "Стали медленнее (время выполнения)", slowSlowest: "Самые медленные (среднее время)",
      slowNoneReg: "За последние прогоны тесты не замедлялись.",
      slowNoData: "Пока мало истории прогонов.",
      historyTitle: "История теста", historyBtn: "История",
      historyFail: "Не удалось загрузить историю: ", noHistory: "Истории по этому тесту нет.",
      histDidntRun: "не запускался", histCount: "за последние {n} запусков",
      caseSearch: "фильтр тестов…", caseGroup: "Группировать по модулю",
      listGroup: "Группировать по dag·task", runsWord: "прогонов", selectGroup: "Выбрать группу",
      groupMore: "Показаны 100 из {n} прогонов — отфильтруйте по этому dag·task.",
      failCapped: "Показаны первые {n} падений.",
      loadFail: "Не удалось загрузить отчёты: ", reportFail: "Не удалось загрузить отчёт: ",
      failuresFail: "Не удалось загрузить падения: ",
      deleteReport: "Удалить отчёт", deleteTitle: "Удалить отчёт?",
      deleteTitleN: "Удалить отчётов: {n}?",
      deleteConfirm: "Отчёт и его файлы будут удалены безвозвратно — везде.",
      cancel: "Отмена", delete: "Удалить", deleting: "Удаление…",
      deleteFail: "Не удалось удалить: ",
      deleteFailedN: "Не удалось удалить: {n} (нет прав).",
      emailRun: "Отправить на почту", emailTitle: "Отправить прогон на почту",
      emailToLabel: "Получатели", emailToPh: "name@example.com, other@example.com",
      emailHint: "Через запятую. Пусто — отправить настроенным получателям.",
      emailSend: "Отправить", emailSending: "Отправка…", emailSent: "Отправлено ✓",
      emailFail: "Не удалось отправить письмо.",
      emailInvalid: "Неверный адрес почты: «{a}». Формат: name@example.com",
      alertsBtn: "Письма", alertsBtnAl: "Отправки письма по этому запуску",
      alertsTitle: "Отправки на почту", alertsSentOk: "отправлено",
      alertsSentFail: "ошибка отправки", alertsAuto: "автоматически", alertsManual: "вручную",
      alertsEmpty: "По этому запуску писем не отправлялось.",
      nSelected: "Выбрано: {n}", deleteSelected: "Удалить", clearSel: "Снять",
      selectRow: "Выбрать строку", selectAll: "Выбрать все",
      forbidden: "Нет прав на удаление этого отчёта (нужно право запускать DAG).",
      older: "Старее", newer: "Новее",
      avgPass: "ср.", avgPassTip: "Средняя доля прохождения по всем {n} прогонам диаграммы (совпадает с радаром)",
      visibleRuns: "Показаны прогоны #{a}–#{b} из {n}",
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
  function debounce(fn, ms) {
    var timer = null;
    return function () { clearTimeout(timer); timer = setTimeout(fn, ms); };
  }
  function fmtDur(s) { return (Number(s) || 0).toFixed(2) + "s"; }
  function fmtTime(s) {
    if (!s) return "—";
    var d = new Date(s);
    try { return isNaN(d) ? esc(s) : d.toLocaleString(LOCALE); } catch (e) { return esc(s); }
  }
  function statusOf(r) { return r.success ? "pass" : (r.errors > 0 ? "error" : "fail"); }
  // A run's overall status maps to a chart-legend key; toggling that legend status off
  // hides the run from the list below (the chart keeps the bar, dimming the segment).
  var STATUS_KEY = { pass: "passed", fail: "failed", error: "error" };
  function statusShown(r) { return chartSel[STATUS_KEY[statusOf(r)]] !== false; }
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
  var sort = { key: "created_at", dir: -1 };       // run-level sort (flat list + within a group)
  var groupSort = { key: "created_at", dir: -1 };  // order of the dag·task groups

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
  var emailAvailable = false;   // echoed by /api/reports; shows the run-detail Email button
  var CHART_VISIBLE = 30; // bars visible at once; beyond that the strip scrolls (carousel)
  var PAGE_SIZE = 100;    // list rows per page
  var chartScroll = null; // null => snap to newest; else a remembered scrollLeft (px)
  var chartDragged = false;
  var listPage = 0;
  var listGroup = true;          // group the run list by dag·task (on by default; checkbox-toggled)
  var listExpanded = {};         // group key -> expanded? (collapsed by default)
  var groupRunSort = {};         // group key -> {key,dir} run-sort override for that group only
  var GROUP_ROW_CAP = 100;       // max run rows rendered per expanded group (bounds the DOM)
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
  // Slowdowns KPI + modal cache. slowSeq guards the KPI fetch, slowModalSeq the modal's.
  var slowCount = null, slowData = null, slowSeq = 0, slowModalSeq = 0, slowFailed = false, slowTimer = null;
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
    // "Failures" = what's broken NOW: failed+errors in the latest run of each dag·task,
    // so the count shrinks as tests get fixed (not every failure ever archived).
    var latestRun = {};
    reports.forEach(function (r) {
      var k = r.dag_id + "|" + r.task_id;
      if (!latestRun[k] || String(r.created_at || "") > String(latestRun[k].created_at || "")) {
        latestRun[k] = r;
      }
    });
    // Selecting group(s) scopes the Failures + Slowdowns KPIs to those dag·tasks (like
    // the flaky panel) -- failures are recomputed from the latest run of the picked
    // dag·tasks; slowdowns are counted from the loaded regressed list, scoped the same.
    var sk = selKeySet();
    var failures = Object.keys(latestRun).reduce(function (a, k) {
      if (sk && !sk[k]) return a;
      return a + (latestRun[k].failed || 0) + (latestRun[k].errors || 0);
    }, 0);
    var slowShown = slowCount;
    if (sk && slowData && slowData.regressed) {
      slowShown = slowData.regressed.filter(function (x) {
        return sk[x.dag_id + "|" + x.task_id];
      }).length;
    }
    var cards = [
      // These two count EVERY run in view (top filters only) and ignore a group selection,
      // unlike the scoped Failures/Slowdowns -- the "all" chip makes that explicit.
      { label: t("kRuns"), value: runs, all: true },
      { label: t("kPassingRuns"), value: ok + " / " + runs, cls: ok === runs ? "c-pass" : "", all: true },
      { label: t("kTests"), value: uniqueTests == null ? "…" : uniqueTests,
        id: "kpi-unique", click: uniqueTests > 0 },
      { label: t("kFailures"), value: failures, cls: failures ? "c-fail" : "c-pass",
        id: "kpi-failures", click: failures > 0, tip: t("kFailuresTip") },
      { label: t("kSlow"), value: slowShown == null ? (slowFailed ? "—" : "…") : slowShown,
        cls: slowShown ? "c-fail" : "", id: "kpi-slow", click: true, tip: t("slowKpiTip") },
    ];
    kpisEl.hidden = false;
    kpisEl.innerHTML = cards.map(function (c) {
      var attrs = (c.id ? ' id="' + c.id + '"' : "")
        + (c.tip ? ' title="' + esc(c.tip) + '"' : "")
        + (c.click ? ' role="button" tabindex="0"' : "");
      var allChip = c.all ? ' <span class="kpi-all" title="' + esc(t("kAllTip")) + '">'
        + esc(t("kAll")) + "</span>" : "";
      return '<div class="kpi' + (c.click ? " clickable" : "") + '"' + attrs
        + '><div class="label">' + esc(c.label) + allChip + '</div>'
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
    var sk = document.getElementById("kpi-slow");
    if (sk) {
      sk.addEventListener("click", openSlow);
      sk.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openSlow(); }
      });
    }
  }

  function renderLegend() {
    var leg = document.getElementById("legend");
    var allOn = ORDER.every(function (o) { return chartSel[o[0]]; });
    leg.innerHTML = ORDER.map(function (o) {
      return '<button type="button" class="' + (chartSel[o[0]] ? "" : "off")
        + '" data-status="' + o[0] + '" aria-pressed="' + !!chartSel[o[0]] + '">'
        + '<i style="background:' + o[2] + '"></i>' + esc(t(o[0])) + "</button>";
    }).join("")
      + (allOn ? ""  // reset appears only once a status is hidden
        : '<button type="button" class="leg-reset" data-reset="1">'
          + esc(t("legendReset")) + "</button>");
    leg.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        if (b.getAttribute("data-reset")) {
          ORDER.forEach(function (o) { chartSel[o[0]] = true; });  // clear the focus
        } else {
          // "Focus" model: clicking a status shows ONLY it (others off); click more to
          // add/remove; emptying the selection falls back to "all shown".
          var s = b.getAttribute("data-status");
          if (ORDER.every(function (o) { return chartSel[o[0]]; })) {
            ORDER.forEach(function (o) { chartSel[o[0]] = o[0] === s; });
          } else {
            chartSel[s] = !chartSel[s];
            if (ORDER.every(function (o) { return !chartSel[o[0]]; })) {
              ORDER.forEach(function (o) { chartSel[o[0]] = true; });
            }
          }
        }
        renderLegend();   // refresh selection state + the reset button
        renderChart();    // bars show only the selected statuses
        renderList();     // and the list shows only those runs
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
  // The visible-window context next to the arrows: which runs are on screen ("#48-#76
  // of 76") and, when the trend is on, their average pass rate. Recomputed on scroll
  // from scrollLeft (bars are evenly spaced at `slot`), so it tracks the carousel live.
  function updateChartMeta(barsEl, win, slot) {
    var rEl = document.getElementById("chart-range"), aEl = document.getElementById("chart-avg");
    var count = win.length;
    if (!count || !slot) return;                       // nothing to show / not laid out yet
    var vw = barsEl.clientWidth || 0, sl = barsEl.scrollLeft;
    var first = Math.ceil(sl / slot - 0.5);            // first bar whose centre is in view
    var last = Math.floor((sl + vw) / slot - 0.5);     // last such bar
    // Clamp BOTH ends into [0, count-1]: before layout settles clientWidth can read 0,
    // which pushes `first` to `count` and indexes past the array (win[first] undefined).
    first = Math.max(0, Math.min(first, count - 1));
    last = Math.max(0, Math.min(last, count - 1));
    if (last < first) last = first;
    if (rEl) {
      rEl.innerHTML = "<b>#" + win[first].seq + "–#" + win[last].seq + "</b> / " + count;
      rEl.title = t("visibleRuns").replace("{a}", win[first].seq)
        .replace("{b}", win[last].seq).replace("{n}", count);
    }
    if (aEl) {
      // Average over ALL runs in the chart (not just the visible window) so it's the overall
      // pass rate -- identical to the radar's Pass rate, and stable as you scroll the carousel.
      var sum = 0, k = 0;
      if (passTrend) {
        for (var i = 0; i < count; i++) {
          var tot = win[i].total || 0;
          if (tot > 0) { sum += (win[i].passed || 0) / tot; k++; }
        }
      }
      if (k === 0) { aEl.hidden = true; }
      else {
        var avg = sum / k;
        aEl.hidden = false;
        aEl.innerHTML = esc(t("avgPass")) + " <b>" + Math.round(avg * 100) + "%</b>";
        aEl.classList.toggle("below", avg < successThreshold);
        aEl.title = t("avgPassTip").replace("{n}", k);
      }
    }
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
    // Sit just below the cursor, offset to its left (flips to the other side near an edge).
    var x = ev.clientX - w - pad;
    if (x < 8) x = ev.clientX + pad;
    var y = ev.clientY + pad;
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
      card.hidden = true; document.getElementById("chart-nav").innerHTML = "";
      var rEl0 = document.getElementById("chart-range"); if (rEl0) rEl0.innerHTML = "";
      var aEl0 = document.getElementById("chart-avg"); if (aEl0) aEl0.hidden = true;
      return;
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
    updateChartMeta(barsEl, win, slot);
    barsEl.addEventListener("scroll", function () {
      chartScroll = barsEl.scrollLeft; updateChartArrows(barsEl); updateChartMeta(barsEl, win, slot);
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
    var thy = yOf(successThreshold);  // the orange success line, in pixels
    var dots = pts.map(function (p) {
      var bad = p.rate < successThreshold;  // below the line = failing run
      return '<circle class="trend-dot' + (bad ? " trend-dot-bad" : "") + '" cx="'
        + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1)
        + '" r="3.2" data-id="' + esc(p.r.id) + '"></circle>';
    }).join("");
    // Draw the line as segments so the stretch below the success threshold turns red.
    // A segment straddling the line is split at the crossing point so the colour flips
    // exactly where it crosses.
    function trendSeg(x1, y1, x2, y2, bad) {
      return '<line class="trend-line' + (bad ? " trend-danger" : "") + '" x1="' + x1.toFixed(1)
        + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) + '"></line>';
    }
    var segs = "";
    for (var si = 0; si < pts.length - 1; si++) {
      var a = pts[si], b = pts[si + 1];
      var aBad = a.rate < successThreshold, bBad = b.rate < successThreshold;
      if (aBad === bBad) {
        segs += trendSeg(a.x, a.y, b.x, b.y, aBad);
      } else {  // one point each side: split at y = threshold (a.y !== b.y here)
        var f = (thy - a.y) / (b.y - a.y);
        var xc = a.x + (b.x - a.x) * f;
        segs += trendSeg(a.x, a.y, xc, thy, aBad) + trendSeg(xc, thy, b.x, b.y, bBad);
      }
    }
    strip.insertAdjacentHTML("beforeend",
      '<svg class="trend-svg" width="' + stripW + '" height="' + (strip.clientHeight || 128)
      + '" aria-hidden="true">' + segs + dots + "</svg>");
    strip.querySelectorAll(".trend-dot").forEach(function (dot, i) {
      var p = pts[i];
      dot.addEventListener("click", function () { if (!chartDragged) openDetail(p.r.id); });
      bindTip(dot, function () {
        return "<b>#" + p.r.seq + "</b> " + esc(t("passRate")) + ": "
          + Math.round(p.rate * 100) + "% (" + (p.r.passed || 0) + "/" + (p.r.total || 0) + ")";
      });
    });
    // Dashed threshold gridline, pinned (lives in #chart, outside the scrolling strip).
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
    // Also reset the group-header checkboxes (checked + indeterminate) -- otherwise a
    // ticked group stays ticked after "show all" even though its runs are deselected.
    syncSelAll(); syncGroupChecks(); updateBulkBar(); renderChart(); renderFlakyBoard(); renderKpis(); renderReliability();
  }

  // Comparator for a given run-sort state {key, dir} -- reused by the flat list and
  // by each group (which may carry its own override).
  function runComparator(s) {
    var col = COLS.filter(function (c) { return c.key === s.key; })[0] || COLS[0];
    var getv = col.get || function (r) { return r[col.key]; };
    return function (a, b) {
      var x = getv(a), y = getv(b);
      if (typeof x === "string") { x = x.toLowerCase(); y = String(y).toLowerCase(); }
      if (x < y) return -1 * s.dir;
      if (x > y) return 1 * s.dir;
      return 0;
    };
  }
  function sortReports() { reports.sort(runComparator(sort)); }

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

  // Group the run list by dag·task: a checkbox toggles it (like the detail's
  // group-by-module). Each header collapses/expands and its checkbox selects the whole
  // group, which focuses the chart on it.
  function groupReports(rows) {
    var order = [], byKey = {};
    rows.forEach(function (r) {
      var key = JSON.stringify([r.dag_id, r.task_id]);
      if (!byKey[key]) {
        byKey[key] = { key: key, dag: r.dag_id, task: r.task_id, runs: [] };
        order.push(byKey[key]);
      }
      byKey[key].runs.push(r);
    });
    // The newest run drives the group's status / when and the status/recency
    // ordering -- independent of how runs are sorted within the group.
    order.forEach(function (g) {
      g.newest = g.runs.reduce(function (a, b) {
        return String(a.created_at || "") >= String(b.created_at || "") ? a : b;
      });
      g.passed = g.runs.filter(function (r) { return r.success; }).length;
      g.avgDur = g.runs.reduce(function (s, r) { return s + (+r.duration || 0); }, 0) / g.runs.length;
    });
    return order;
  }
  // Flat-list column headers -- sorted by the global run sort.
  function headCells() {
    return COLS.map(function (c) {
      var asc = sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none";
      return '<th class="sortable" data-key="' + c.key + '" aria-sort="' + asc + '">'
        + '<span class="th-lab">' + esc(t(c.label)) + arrow(c.key) + "</span></th>";
    }).join("");
  }
  // A group's full column header -- sorts the runs of THAT group only (class rsort,
  // tagged with the group key); arrows reflect the group's effective sort `eff`.
  function subHead(g, eff) {
    var cells = COLS.map(function (c) {
      var on = eff.key === c.key;
      var ar = on ? '<span class="arrow">' + (eff.dir === 1 ? "↑" : "↓") + "</span>" : "";
      return '<th class="rsort" data-key="' + c.key + '" data-gkey="' + esc(g.key)
        + '" aria-sort="' + (on ? (eff.dir === 1 ? "ascending" : "descending") : "none") + '">'
        + '<span class="th-lab">' + esc(t(c.label)) + ar + "</span></th>";
    }).join("");
    return '<th class="sel-cell"></th>' + cells + "<th></th>";
  }
  // A group-level column header (reorders the groups; uses the separate groupSort).
  function gHeadCell(key, label, cls) {
    var asc = groupSort.key === key ? (groupSort.dir === 1 ? "ascending" : "descending") : "none";
    return '<th class="gsort' + (cls ? " " + cls : "") + '" data-key="' + key
      + '" aria-sort="' + asc + '"><span class="th-lab">' + esc(t(label))
      + groupArrow(key) + "</span></th>";
  }
  function groupArrow(key) {
    if (groupSort.key !== key) return "";
    return '<span class="arrow">' + (groupSort.dir === 1 ? "↑" : "↓") + "</span>";
  }
  // A group's value for the active group-sort column.
  function groupVal(g) {
    if (groupSort.key === "dag_id") return g.dag.toLowerCase();
    if (groupSort.key === "task_id") return g.task.toLowerCase();
    if (groupSort.key === "runs") return g.runs.length;
    if (groupSort.key === "pass_rate") return g.passed / g.runs.length;
    if (groupSort.key === "avg_dur") return g.avgDur;
    if (groupSort.key === "status") return g.newest.success ? 2 : (g.newest.errors ? 0 : 1);
    return String(g.newest.created_at || "");  // created_at, and the default
  }
  // Yellow warning chip -- rendered ONLY for groups that have at least one flaky test.
  function flkGroupChip(g) {
    var c = flkCountByKey[g.key] || 0;
    if (!c) return "";
    return ' <button type="button" class="lgrp-flk" data-key="' + esc(g.key)
      + '" aria-label="' + esc(t("flkGroupWarn")) + '" title="' + esc(t("flkGroupWarn")) + '">'
      + ICONS.error + "<span>" + c + "</span></button>";
  }
  function groupHeaderHtml(g) {
    var exp = !!listExpanded[g.key];
    var nSel = g.runs.filter(function (r) { return selectedIds.has(r.id); }).length;
    var rate = Math.round(g.passed / g.runs.length * 100);
    var st = statusOf(g.newest);
    return '<tr class="lgrp" data-key="' + esc(g.key) + '">'
      + '<td class="sel-cell"><input type="checkbox" class="gsel" data-key="' + esc(g.key) + '"'
        + (nSel === g.runs.length ? " checked" : "") + ' aria-label="' + esc(t("selectGroup")) + '"></td>'
      + '<td class="mono"><span class="chev"' + (exp ? ' style="transform:rotate(90deg)"' : "")
        + ">" + CHEV + "</span> " + esc(g.dag) + "</td>"
      + '<td class="mono">' + esc(g.task) + flkGroupChip(g) + "</td>"
      + '<td class="num">' + g.runs.length + "</td>"
      + '<td class="num">' + rate + "%</td>"
      + '<td class="num">' + fmtDur(g.avgDur) + "</td>"
      + "<td>" + badge(st, statusLabel(st)) + "</td>"
      + '<td class="muted lgrp-when"><div class="lgrp-when-in">' + fmtTime(g.newest.created_at)
      + '<button type="button" class="lgrp-hm" data-key="' + esc(g.key)
      + '" data-i18n-al="heatmapBtnAl" title="' + esc(t("heatmapBtn")) + '">'
      + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
      + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
      + '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'
      + "</svg></button></div></td></tr>";
  }

  function renderList() {
    if (!reports.length) {
      listEl.innerHTML = '<div class="state">'
        + esc(allReports.length ? t("noMatch") : t("noReports")) + "</div>";
      updateBulkBar();  // no rows -> drop any stale bulk bar
      return;
    }
    sortReports();
    // Legend status toggles also filter the list (chart keeps the bars).
    var shown = reports.filter(statusShown);
    if (!shown.length) {
      listEl.innerHTML = '<div class="state">' + esc(t("noMatch")) + "</div>";
      updateBulkBar();
      return;
    }
    var ctrls = '<div class="list-ctrls"><label class="list-grp-lbl"><input type="checkbox" id="list-grp"'
      + (listGroup ? " checked" : "") + "> " + esc(t("listGroup")) + "</label></div>";
    var selAllTh = '<th class="sel-cell"><input type="checkbox" id="sel-all" aria-label="'
      + esc(t("selectAll")) + '"></th>';

    var pages = 1, keyMap = {}, theadInner, body, pager = "";
    if (listGroup) {
      // The top header (gsort) reorders the GROUPS -- and, for run columns, the runs
      // too (handled in the click). Each opened group's own header (rsort) sorts only
      // that group's runs (groupRunSort override, else the global run sort).
      theadInner = selAllTh + gHeadCell("dag_id", "cDag", "gcol-dag")
        + gHeadCell("task_id", "cTask")
        + gHeadCell("runs", "cRuns") + gHeadCell("pass_rate", "cPassRate")
        + gHeadCell("avg_dur", "cAvgDur") + gHeadCell("status", "cStatus")
        + gHeadCell("created_at", "cWhen", "gcol-when");
      var groups = groupReports(shown);
      groups.forEach(function (g) { keyMap[g.key] = g; });
      groups.sort(function (a, b) {
        var x = groupVal(a), y = groupVal(b);
        if (x < y) return -1 * groupSort.dir;
        if (x > y) return 1 * groupSort.dir;
        return 0;
      });
      body = groups.map(function (g) {
        if (!listExpanded[g.key]) return groupHeaderHtml(g);
        var eff = groupRunSort[g.key] || sort;  // this group's own run sort, else global
        var runs = g.runs.slice().sort(runComparator(eff));
        var more = g.runs.length > GROUP_ROW_CAP
          ? '<tr class="grp-more"><td colspan="' + (COLS.length + 2) + '">'
            + esc(t("groupMore").replace("{n}", String(g.runs.length))) + "</td></tr>"
          : "";
        return groupHeaderHtml(g)
          + '<tr class="grp-runs"><td colspan="8"><div class="table-wrap">'
          + '<table class="sub-table"><thead><tr>' + subHead(g, eff) + "</tr></thead><tbody>"
          + renderRows(runs.slice(0, GROUP_ROW_CAP)) + more + "</tbody></table></div></td></tr>";
      }).join("");
    } else {
      theadInner = selAllTh + headCells() + "<th></th>";
      pages = Math.ceil(shown.length / PAGE_SIZE);
      listPage = Math.max(0, Math.min(listPage, pages - 1));
      body = renderRows(shown.slice(listPage * PAGE_SIZE, listPage * PAGE_SIZE + PAGE_SIZE));
      pager = pages > 1
        ? '<div class="pager"><button type="button" class="nav-btn" id="pg-prev"'
            + (listPage <= 0 ? " disabled" : "") + ' aria-label="' + esc(t("prevPage")) + '">‹</button>'
          + "<span>" + esc(t("page")) + " " + (listPage + 1) + " / " + pages + "</span>"
          + '<button type="button" class="nav-btn" id="pg-next"'
            + (listPage >= pages - 1 ? " disabled" : "") + ' aria-label="' + esc(t("nextPage")) + '">›</button></div>'
        : "";
    }
    listEl.innerHTML = ctrls + '<div class="table-wrap"><table><thead><tr>' + theadInner
      + "</tr></thead><tbody>" + body + "</tbody></table></div>" + pager;

    var lg = document.getElementById("list-grp");
    if (lg) lg.addEventListener("change", function () {
      // Start the (re)entered view clean: folded, no stale per-group sort overrides.
      listGroup = lg.checked; listExpanded = {}; groupRunSort = {}; listPage = 0; renderList();
    });
    listEl.querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function (e) {
        if (!e.target.closest(".th-lab")) return;  // only the label sorts, not the empty space
        var k = th.getAttribute("data-key");
        if (sort.key === k) sort.dir *= -1; else { sort.key = k; sort.dir = 1; }
        listPage = 0;
        renderList();
      });
    });
    listEl.querySelectorAll("th.gsort").forEach(function (th) {  // top header: groups + tests
      th.addEventListener("click", function (e) {
        if (!e.target.closest(".th-lab")) return;  // only the label sorts, not the empty space
        var k = th.getAttribute("data-key");
        if (groupSort.key === k) groupSort.dir *= -1; else { groupSort.key = k; groupSort.dir = 1; }
        groupRunSort = {};  // drop per-group overrides -- the top header is the global control
        // If the column maps to a run field, move the runs (in every group) too.
        if (COLS.some(function (c) { return c.key === k; })) { sort.key = k; sort.dir = groupSort.dir; }
        renderList();
      });
    });
    listEl.querySelectorAll("th.rsort").forEach(function (th) {  // sort one group's runs only
      th.addEventListener("click", function (e) {
        if (!e.target.closest(".th-lab")) return;  // only the label sorts, not the empty space
        var gk = th.getAttribute("data-gkey"), k = th.getAttribute("data-key");
        var cur = groupRunSort[gk] || { key: sort.key, dir: sort.dir };
        groupRunSort[gk] = cur.key === k ? { key: k, dir: -cur.dir } : { key: k, dir: 1 };
        renderList();
      });
    });
    var pgPrev = document.getElementById("pg-prev"), pgNext = document.getElementById("pg-next");
    if (pgPrev) pgPrev.addEventListener("click", function () { if (listPage > 0) { listPage--; renderList(); } });
    if (pgNext) pgNext.addEventListener("click", function () { if (listPage < pages - 1) { listPage++; renderList(); } });
    // Group headers: row toggles expand/collapse; its checkbox selects the whole group
    // (selecting focuses the chart, and ticks the group even while collapsed).
    listEl.querySelectorAll("tr.lgrp").forEach(function (tr) {
      tr.addEventListener("click", function () {
        var key = tr.getAttribute("data-key");
        listExpanded[key] = !listExpanded[key];
        renderList();
      });
    });
    listEl.querySelectorAll(".lgrp-hm").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation();  // open the heatmap, don't toggle the group
        var g = keyMap[b.getAttribute("data-key")];
        if (g) openHeatmap(g.dag, g.task);
      });
    });
    listEl.querySelectorAll(".lgrp-flk").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation();  // scope the board to this group, don't toggle the expand
        var cb = b.closest("tr").querySelector(".gsel");
        if (cb && !cb.checked) { cb.checked = true; cb.dispatchEvent(new Event("change")); }
        var card = document.getElementById("flaky-card");
        if (card && !card.hidden) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });
    listEl.querySelectorAll(".gsel").forEach(function (cb) {
      var g = keyMap[cb.getAttribute("data-key")];
      var nSel = g.runs.filter(function (r) { return selectedIds.has(r.id); }).length;
      cb.indeterminate = nSel > 0 && nSel < g.runs.length;
      cb.addEventListener("click", function (e) { e.stopPropagation(); });
      cb.addEventListener("change", function () {
        g.runs.forEach(function (r) {
          if (cb.checked) selectedIds.add(r.id); else selectedIds.delete(r.id);
        });
        renderChart(); renderList(); updateBulkBar(); renderFlakyBoard(); renderKpis(); renderReliability();
      });
    });
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
        syncSelAll(); syncGroupChecks(); updateBulkBar(); renderChart(); renderFlakyBoard(); renderKpis(); renderReliability();
      });
    });
    var selAll = document.getElementById("sel-all");
    if (selAll) selAll.addEventListener("change", function () {
      if (listGroup) {
        // Select every run across all groups (even collapsed) and tick the groups.
        reports.forEach(function (r) {
          if (selAll.checked) selectedIds.add(r.id); else selectedIds.delete(r.id);
        });
        listEl.querySelectorAll(".sel").forEach(function (cb) { cb.checked = selAll.checked; });
        syncGroupChecks();
      } else {
        listEl.querySelectorAll(".sel").forEach(function (cb) {
          cb.checked = selAll.checked;
          var id = cb.getAttribute("data-id");
          if (selAll.checked) selectedIds.add(id); else selectedIds.delete(id);
        });
      }
      selAll.indeterminate = false;
      updateBulkBar(); renderChart(); renderFlakyBoard(); renderKpis(); renderReliability();
    });
    syncSelAll(); updateBulkBar();
  }

  // Reflect the current selection onto the group checkboxes (incl. collapsed groups).
  function syncGroupChecks() {
    if (!listGroup) return;
    var byKey = {};
    groupReports(reports).forEach(function (g) { byKey[g.key] = g; });
    listEl.querySelectorAll(".gsel").forEach(function (cb) {
      var g = byKey[cb.getAttribute("data-key")];
      if (!g) return;
      var n = g.runs.filter(function (r) { return selectedIds.has(r.id); }).length;
      cb.checked = n === g.runs.length;
      cb.indeterminate = n > 0 && n < g.runs.length;
    });
  }

  function syncSelAll() {
    var selAll = document.getElementById("sel-all");
    if (!selAll) return;
    if (listGroup) {  // count over all runs, since collapsed groups render no rows
      var sn = reports.filter(function (r) { return selectedIds.has(r.id); }).length;
      selAll.checked = reports.length > 0 && sn === reports.length;
      selAll.indeterminate = sn > 0 && sn < reports.length;
      return;
    }
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

  function renderAll() { renderKpis(); renderChart(); renderList(); renderReliability(); if (detail) renderDetail(); }

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
        emailAvailable = !!d.email_available;
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
    var fc = document.getElementById("f-clear");  // reset button: only when a filter is set
    if (fc) fc.hidden = !(dag || task || run);
    reports = allReports.filter(function (r) {
      return matchesIn(r.dag_id, dag) && matchesIn(r.task_id, task) && matchesIn(r.run_id, run);
    });
    assignSeq();
    // Filter resets to the newest runs / first page; a delete keeps the user's place.
    if (!keepPage) { chartScroll = null; listPage = 0; }
    document.getElementById("board").hidden = allReports.length === 0;
    document.getElementById("board2").hidden = allReports.length === 0;
    renderKpis(); renderChart(); renderList(); renderFlakyBoard();
    refreshUniqueTests();
    refreshSlow();
  }
  // The dag·task keys ("dag|task") of the runs the user has ticked, or null if nothing
  // is selected. Selecting a group (or runs) scopes the chart AND the flaky/failures/slow
  // boards to those dag·tasks -- one pick narrows the whole dashboard.
  function selKeySet() {
    if (!selectedIds.size) return null;
    var m = {};
    reports.forEach(function (r) {
      if (selectedIds.has(r.id)) m[r.dag_id + "|" + r.task_id] = 1;
    });
    return m;
  }
  // Flaky panel on the main board: global flaky tests, filtered client-side by the
  // dag/task search; a row opens that test's history.
  var allFlaky = [];
  // Per-group flaky count, keyed exactly like a group's key (JSON [dag_id, task_id]); drives
  // the yellow warning chip on the run-list groups. Rebuilt whenever the flaky data changes.
  var flkCountByKey = {};
  function rebuildFlkCounts() {
    flkCountByKey = {};
    allFlaky.forEach(function (f) {
      var k = JSON.stringify([f.dag_id, f.task_id]);
      flkCountByKey[k] = (flkCountByKey[k] || 0) + 1;
    });
  }
  function renderFlakyBoard() {
    var box = document.getElementById("flaky-list");
    if (!box) return;
    // No flaky anywhere -> drop the whole panel so the runs chart takes the full width.
    // It reappears (with content) the moment any flaky test shows up. When the panel's
    // presence flips, the chart is re-rendered so its bars re-fill the new (wider/narrower)
    // width -- otherwise they'd stay sized to the old half-width layout.
    // No flaky anywhere -> hide the panel; the radar beside it grows to fill the row. The chart
    // is on its own full-width row now, so its width doesn't depend on the flaky panel.
    var flakyCard = document.getElementById("flaky-card");
    if (flakyCard) flakyCard.hidden = !allFlaky.length;
    if (!allFlaky.length) return;
    var dag = document.getElementById("f-dag").value.trim().toLowerCase();
    var task = document.getElementById("f-task").value.trim().toLowerCase();
    var qEl = document.getElementById("flk-board-q");
    var q = qEl ? qEl.value.trim().toLowerCase() : "";
    var qOnlyEl = document.getElementById("flk-board-qonly");
    var qOnly = !!(qOnlyEl && qOnlyEl.checked);
    var selKeys = selKeySet();
    var scope = document.getElementById("flk-scope");
    if (scope) {
      scope.hidden = !selKeys;
      if (selKeys) scope.textContent = t("flkSelScope");
    }
    var rows = allFlaky.filter(function (f) {
      if (selKeys && !selKeys[f.dag_id + "|" + f.task_id]) return false;
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
      // Distinguish "nothing flaky" / "selection has none" / "filtered everything out".
      var msg = !allFlaky.length ? "noFlaky" : selKeys ? "flkNoSel" : "flkNoMatch";
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
      .then(function (d) {
        allFlaky = d.flaky || []; rebuildFlkCounts();
        renderFlakyBoard(); renderList(); renderReliability();  // stability axis uses flaky
      })
      .catch(function () {
        allFlaky = []; rebuildFlkCounts(); renderFlakyBoard(); renderList(); renderReliability();
      });
  }

  // -- Reliability radar (pentagon): the 3rd main-board dashboard ---------------------
  // Five 0-100 axes (higher = better) over the runs in view -- scoped by the top filters and
  // any group selection, exactly like the chart/flaky panel. Pure read of already-loaded data
  // (report summaries + flaky list), so it never fires its own request.
  function reliabilityAxes() {
    var selKeys = selKeySet();
    var inScope = function (o) { return !selKeys || selKeys[o.dag_id + "|" + o.task_id]; };
    var rows = reports.filter(inScope), flk = allFlaky.filter(inScope);
    var T = 0, E = 0, S = 0, latest = {}, passSum = 0, passK = 0;
    rows.forEach(function (r) {
      T += r.total || 0; E += r.errors || 0; S += r.skipped || 0;
      var tt = r.total || 0;
      if (tt > 0) { passSum += (r.passed || 0) / tt; passK++; }  // per-run ratio (matches chart)
      var k = r.dag_id + "|" + r.task_id;
      if (!latest[k] || String(r.created_at || "") > String(latest[k].created_at || "")) {
        latest[k] = r;
      }
    });
    var keys = Object.keys(latest), green = 0, uniq = 0;
    keys.forEach(function (k) { if (latest[k].success) green++; uniq += latest[k].total || 0; });
    var clamp = function (v) { return Math.max(0, Math.min(100, Math.round(v))); };
    return [
      // Pass rate = mean of each run's pass ratio -- the SAME formula as the chart's "avg
      // pass rate", so one group reads identically on both (chart is the visible window, the
      // radar is every run in view, so they can differ once the window no longer covers all).
      { key: "pass", label: t("relPass"), value: passK ? clamp(passSum / passK * 100) : 100 },
      { key: "robust", label: t("relRobust"), value: T ? clamp(100 - E / T * 100) : 100 },
      { key: "fresh", label: t("relFresh"), value: keys.length ? clamp(green / keys.length * 100) : 100 },
      { key: "stable", label: t("relStable"), value: uniq ? clamp(100 - flk.length / uniq * 100) : 100 },
      { key: "complete", label: t("relComplete"), value: T ? clamp(100 - S / T * 100) : 100 },
    ];
  }
  function pentagonSvg(axes) {
    // Wide viewBox: labels live INSIDE it, so the whole radar scales as one unit and a long
    // label never spills over the card edge on a small screen (it just shrinks with the rest).
    var W = 460, H = 232, cx = W / 2, cy = H / 2 + 2, R = 90, n = axes.length;
    var ang = function (i) { return (-90 + i * (360 / n)) * Math.PI / 180; };
    var at = function (i, rr) { var a = ang(i); return [cx + rr * Math.cos(a), cy + rr * Math.sin(a)]; };
    var ptsAt = function (rr) {
      return axes.map(function (_, i) { var p = at(i, rr); return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
    };
    var rings = [0.25, 0.5, 0.75, 1].map(function (f) {
      return '<polygon class="rel-grid" points="' + ptsAt(R * f) + '"/>';
    }).join("");
    var spokes = axes.map(function (_, i) {
      var p = at(i, R);
      return '<line class="rel-grid" x1="' + cx + '" y1="' + cy + '" x2="' + p[0].toFixed(1) + '" y2="' + p[1].toFixed(1) + '"/>';
    }).join("");
    var dataPts = axes.map(function (a, i) {
      var p = at(i, R * (a.value / 100)); return p[0].toFixed(1) + "," + p[1].toFixed(1);
    }).join(" ");
    var dots = axes.map(function (a, i) {
      var p = at(i, R * (a.value / 100));
      return '<circle class="rel-dot" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="3"/>';
    }).join("");
    var labels = axes.map(function (a, i) {
      var p = at(i, R + 14), c = Math.cos(ang(i)), s = Math.sin(ang(i));
      var anchor = Math.abs(c) < 0.3 ? "middle" : (c > 0 ? "start" : "end");
      var dy = s > 0.3 ? "0.9em" : (s < -0.3 ? "-0.3em" : "0.32em");
      return '<text class="rel-lab" x="' + p[0].toFixed(1) + '" y="' + p[1].toFixed(1)
        + '" text-anchor="' + anchor + '" dy="' + dy + '">' + esc(a.label)
        + '<tspan class="rel-val" dx="4">' + a.value + "</tspan></text>";
    }).join("");
    var overall = Math.round(axes.reduce(function (s, a) { return s + a.value; }, 0) / n);
    var center = '<text class="rel-score" x="' + cx + '" y="' + (cy - 1) + '" text-anchor="middle">' + overall + "</text>"
      + '<text class="rel-score-cap" x="' + cx + '" y="' + (cy + 12) + '" text-anchor="middle">' + esc(t("relOverall")) + "</text>";
    return '<svg viewBox="0 0 ' + W + " " + H + '" class="rel-svg" role="img" aria-label="' + esc(t("reliabilityTitle")) + '">'
      + rings + spokes + '<polygon class="rel-area" points="' + dataPts + '"/>' + dots + center + labels + "</svg>";
  }
  // -- Run-health trend: a per-run health series over time, drawn as a sparkline under the
  // radar. "Health" is the mean of the three CONTINUOUS per-run axes (pass rate, no-errors,
  // completeness). Green-now (a binary 0/100 per run) and Flaky/Stability (a window metric) are
  // radar snapshots, not per-run signals, so they're left off the line. Pure read of the loaded
  // summaries, scoped like the radar.
  function reliabilityTrend() {
    var selKeys = selKeySet();
    var inScope = function (o) { return !selKeys || selKeys[o.dag_id + "|" + o.task_id]; };
    var rows = reports.filter(inScope).slice().sort(function (a, b) {
      return String(a.created_at || "") < String(b.created_at || "") ? -1 : 1;  // oldest -> newest
    });
    var clamp = function (v) { return Math.max(0, Math.min(100, v)); };
    var values = rows.map(function (r) {
      var tt = r.total || 0;
      var pass = tt ? (r.passed || 0) / tt * 100 : 100;
      var robust = tt ? 100 - (r.errors || 0) / tt * 100 : 100;
      var complete = tt ? 100 - (r.skipped || 0) / tt * 100 : 100;
      return clamp(Math.round((pass + robust + complete) / 3));
    });
    // The time range the line spans (first/last run in view) -- shown as the X-axis labels,
    // so the "over time" reading is explicit instead of implied.
    return {
      values: values,
      from: rows.length ? rows[0].created_at : null,
      to: rows.length ? rows[rows.length - 1].created_at : null,
    };
  }
  // Short, locale-aware day-month label for the trend's time axis ("31 May" / "31 мая").
  function fmtTrendDate(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d)) return "";
    try {
      var opts = { day: "numeric", month: "short" };
      if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
      return d.toLocaleDateString(LOCALE === "ru" ? "ru-RU" : "en-GB", opts);
    } catch (e) { return iso.slice(0, 10); }
  }
  // Trailing moving average so the line reads as a trend, not per-run jitter. Window scales
  // with the run count (none for short histories, up to 9 for long ones).
  function smoothSeries(series) {
    var n = series.length, k = Math.min(9, Math.max(1, Math.floor(n / 12)));
    if (k < 2) return series.slice();
    var out = [];
    for (var i = 0; i < n; i++) {
      var lo = Math.max(0, i - k + 1), sum = 0;
      for (var j = lo; j <= i; j++) sum += series[j];
      out.push(sum / (i - lo + 1));
    }
    return out;
  }
  // "now" = the recent half's mean health; "delta" = recent half minus older half -- the same
  // recent-vs-older split the flaky trend uses, so improving/declining reads consistently.
  function trendDelta(series) {
    var n = series.length;
    if (n < 2) return null;
    var half = Math.floor(n / 2);
    var mean = function (a) { return a.reduce(function (s, v) { return s + v; }, 0) / a.length; };
    var older = mean(series.slice(0, half)), recent = mean(series.slice(half));
    return { now: Math.round(recent), delta: Math.round(recent - older) };
  }
  function trendSparkline(rawSeries) {
    var series = smoothSeries(rawSeries);
    var W = 240, H = 40, pad = 4, n = series.length;
    var x = function (i) { return n < 2 ? W / 2 : pad + i * (W - 2 * pad) / (n - 1); };
    var y = function (v) { return pad + (100 - v) / 100 * (H - 2 * pad); };
    var line = series.map(function (v, i) { return x(i).toFixed(1) + "," + y(v).toFixed(1); }).join(" ");
    var area = "M" + x(0).toFixed(1) + "," + y(0).toFixed(1)
      + series.map(function (v, i) { return "L" + x(i).toFixed(1) + "," + y(v).toFixed(1); }).join("")
      + "L" + x(n - 1).toFixed(1) + "," + y(0).toFixed(1) + "Z";
    return '<svg class="rt-spark" viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none"'
      + ' role="img" aria-label="' + esc(t("relTrend")) + '">'
      + '<path class="rt-fill" d="' + area + '"/>'
      + '<polyline class="rt-line" points="' + line + '"/></svg>';
  }
  function renderRelTrend() {
    var box = document.getElementById("rel-trend");
    if (!box) return;
    var tr = reliabilityTrend(), series = tr.values, d = trendDelta(series);
    if (!d) { box.innerHTML = '<span class="rt-hint">' + esc(t("relTrendCollecting")) + "</span>"; return; }
    // The headline number is the CURRENT health -- the last point of the smoothed line --
    // so it always matches what the right edge of the graph shows.
    var smoothed = smoothSeries(series);
    var now = Math.round(smoothed[smoothed.length - 1]);
    var cls = d.delta > 0 ? "rt-up" : (d.delta < 0 ? "rt-down" : "rt-flat");
    var arrow = d.delta > 0 ? "▲" : (d.delta < 0 ? "▼" : "→");
    var sign = d.delta > 0 ? "+" : "";
    // X-axis: the dates of the first and last run in view, so the time span is explicit.
    var axis = '<div class="rt-axis"><span>' + esc(fmtTrendDate(tr.from)) + "</span><span>"
      + esc(fmtTrendDate(tr.to)) + "</span></div>";
    box.innerHTML = '<div class="rt-meta"><span class="rt-label">' + esc(t("relTrend")) + "</span>"
      + '<span class="rt-now" title="' + esc(t("relTrendNowTip")) + '">' + now + "</span>"
      + '<span class="rt-delta ' + cls + '" title="' + esc(t("relTrendVs")) + '">' + arrow + " " + sign + d.delta
      + '</span></div><div class="rt-graph">' + trendSparkline(series) + axis + "</div>";
  }
  function renderReliability() {
    var el = document.getElementById("pentagon");
    if (!el) return;
    var selKeys = selKeySet();
    var sc = document.getElementById("rel-scope");
    if (sc) { sc.hidden = !selKeys; if (selKeys) sc.textContent = t("flkSelScope"); }
    el.innerHTML = pentagonSvg(reliabilityAxes());
    renderRelTrend();
  }
  // "How the score is computed" popup: each axis with its live value + a plain-language
  // definition (matches reliabilityAxes exactly), so the radar is self-explaining.
  var relInfoDlg = document.getElementById("rel-info");
  var REL_DESC = { pass: "relPassDesc", robust: "relRobustDesc", fresh: "relFreshDesc",
    stable: "relStableDesc", complete: "relCompleteDesc" };
  function openRelInfo() {
    var body = document.getElementById("rel-info-body");
    body.innerHTML = '<p class="rel-info-intro">' + esc(t("relInfoIntro")) + "</p>"
      + '<ul class="rel-info-list">' + reliabilityAxes().map(function (a) {
          return '<li><span class="ri-head"><span class="ri-name">' + esc(a.label) + "</span>"
            + '<span class="ri-val">' + a.value + "</span></span>"
            + '<span class="ri-desc">' + esc(t(REL_DESC[a.key])) + "</span></li>";
        }).join("") + "</ul>"
      + '<p class="rel-info-intro" style="margin:14px 0 0">' + esc(t("relTrendDesc")) + "</p>";
    if (typeof relInfoDlg.showModal === "function") { if (!relInfoDlg.open) relInfoDlg.showModal(); }
    else relInfoDlg.setAttribute("open", "");
    updateParentDim();
  }
  function closeRelInfo() { if (relInfoDlg.open) relInfoDlg.close(); else relInfoDlg.removeAttribute("open"); }
  // Generic "about this panel" popup (a title + one paragraph from i18n) for the runs chart
  // and the flaky panel.
  var panelInfoDlg = document.getElementById("panel-info");
  function openPanelInfo(titleKey, bodyKey) {
    document.getElementById("panel-info-title").textContent = t(titleKey);
    document.getElementById("panel-info-body").innerHTML = "<p>" + esc(t(bodyKey)) + "</p>";
    if (typeof panelInfoDlg.showModal === "function") { if (!panelInfoDlg.open) panelInfoDlg.showModal(); }
    else panelInfoDlg.setAttribute("open", "");
    updateParentDim();
  }
  function closePanelInfo() { if (panelInfoDlg.open) panelInfoDlg.close(); else panelInfoDlg.removeAttribute("open"); }
  (function () {
    var b = document.getElementById("rel-info-btn");
    if (b) b.addEventListener("click", openRelInfo);
    var c = document.getElementById("rel-info-close");
    if (c) c.addEventListener("click", closeRelInfo);
    if (relInfoDlg) { relInfoDlg.addEventListener("close", updateParentDim); closeOnBackdrop(relInfoDlg, closeRelInfo); }
    var ci = document.getElementById("chart-info");
    if (ci) ci.addEventListener("click", function () { openPanelInfo("chartInfoTitle", "chartInfoBody"); });
    var fi = document.getElementById("flaky-info");
    if (fi) fi.addEventListener("click", function () { openPanelInfo("flakyInfoTitle", "flakyInfoBody"); });
    var pc = document.getElementById("panel-info-close");
    if (pc) pc.addEventListener("click", closePanelInfo);
    if (panelInfoDlg) { panelInfoDlg.addEventListener("close", updateParentDim); closeOnBackdrop(panelInfoDlg, closePanelInfo); }
  })();
  // Duration-regression scan honouring the top dag/task/run filters (like the other
  // KPIs): feeds the "Slowdowns" count and primes the modal so its first open is instant.
  function slowQuery(win) {
    var q = uniqueQuery();  // dag_id / task_id / run_id from the top filter bar
    return win ? (q ? q + "&" : "") + "window=" + encodeURIComponent(win) : q;
  }
  function loadSlow() {
    var my = ++slowSeq;
    fetch(API + "slow?" + slowQuery())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (my !== slowSeq) return;
        slowData = d; slowCount = d ? d.total_regressed : null; slowFailed = !d; renderKpis();
      })
      .catch(function () { if (my === slowSeq) { slowData = null; slowFailed = true; renderKpis(); } });
  }
  // Debounced refresh on filter changes, mirroring refreshUniqueTests; also keeps an
  // open modal in sync with the filter.
  function refreshSlow() {
    clearTimeout(slowTimer);
    slowTimer = setTimeout(function () {
      loadSlow();
      if (slowDlg.open) loadSlowModal();
    }, 250);
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
  // The run's case table sorts by execution time, slowest first by default; the
  // TEST / TIME headers toggle. (Top-slowest & regressions across runs live on the
  // main page only -- a single run has no "slower than usual" context.)
  var caseSort = { key: "time", dir: "desc" };

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
    // Lay slices out by their actual footprint (drawn + GAP) within the gapped arc, not by
    // their raw proportion: this keeps a full GAP between every drawn segment, so when a
    // share is ~0% its rounded cap stays a clear dot and two tiny slices can't overlap.
    var avail = total > 0 ? C - nSeg * GAP : C;
    var cursor = 0, parts = "";
    segs.forEach(function (s) {
      var v = s[2] || 0;
      if (total <= 0 || v <= 0) return;
      var pct = Math.round((v / total) * 100);
      var lit = filter === "all" || filter === s[0];
      var drawn = Math.max((v / total) * avail, 0.1);  // a tiny share -> a rounded dot
      parts += '<circle class="dseg" data-status="' + s[0] + '" data-count="' + v
        + '" data-pct="' + pct + '" cx="60" cy="60" r="50" '
        + 'fill="none" stroke="' + s[1] + '" stroke-width="' + SW + '" stroke-dasharray="'
        + drawn.toFixed(2) + " " + (C - drawn).toFixed(2) + '" stroke-dashoffset="'
        + (-(cursor + GAP / 2)).toFixed(2) + '" opacity="' + (lit ? 1 : 0.3) + '"></circle>';
      cursor += drawn + GAP;
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
    // Only offer "Flaky tests" when this dag·task actually has flaky ones (same 30-run window
    // the modal uses), so the button never opens an empty list.
    if (flkCountByKey[JSON.stringify([m.dag_id, m.task_id])] > 0) {
      var zap = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
        + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + '<path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/></svg>';
      out += '<button type="button" class="af-link" id="flk-btn" data-i18n-al="flakyBtnAl">'
        + zap + esc(t("flakyBtn")) + "</button>";
    }
    var grid = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
      + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
      + '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';
    out += '<button type="button" class="af-link" id="hm-btn" data-i18n-al="heatmapBtnAl">'
      + grid + esc(t("heatmapBtn")) + "</button>";
    if ((m.failed || 0) + (m.errors || 0) > 0) {
      var lst = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
        + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>';
      out += '<button type="button" class="af-link" id="cl-btn" data-i18n-al="clBtnAl">'
        + lst + esc(t("clBtn")) + "</button>";
    }
    // Email-notification bench: how many times this run was mailed; opens the send log.
    if ((m.alerts || []).length > 0) {
      var mail = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
        + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>';
      out += '<button type="button" class="af-link" id="alerts-btn" data-i18n-al="alertsBtnAl">'
        + mail + esc(t("alertsBtn")) + ' <span class="af-count">' + m.alerts.length + "</span></button>";
    }
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
    sel.sort(caseCmp);  // slowest-first by default; groups inherit this order
    if (!sel.length) {
      tb.innerHTML = '<tr><td colspan="4"><div class="state">' + esc(t("noCases")) + "</div></td></tr>";
      return;
    }
    if (caseGroup) {
      var groups = {};
      var order = [];  // module order follows the active sort (first appearance in sel)
      sel.forEach(function (o) {
        var mod = caseModule(o.c.node_id);
        if (groups[mod]) groups[mod].push(o);
        else { groups[mod] = [o]; order.push(mod); }
      });
      tb.innerHTML = order.map(function (mod) {
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
    document.getElementById("d-email").hidden = !emailAvailable;

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
      + '<div class="card table-wrap case-table"><table>'
      + '<thead><tr id="case-head"></tr></thead><tbody></tbody></table></div>';

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
    var hmBtn = document.getElementById("hm-btn");
    if (hmBtn) hmBtn.addEventListener("click", function () { openHeatmap(m.dag_id, m.task_id); });
    // Per-run error clusters: a clear toolbar button opens the clusters modal scoped to
    // this run; a cluster's test jumps to its history.
    var clBtn = document.getElementById("cl-btn");
    if (clBtn) clBtn.addEventListener("click", function () {
      // latest=0: cluster THIS run's failures (run_id-scoped), not "the dag·task's
      // latest run" — the opened run may be an older one (deep-link / history).
      var qs = "?" + new URLSearchParams(
        { dag_id: m.dag_id, task_id: m.task_id, run_id: m.run_id, latest: "0" }
      ).toString();
      openClusters(qs, rec && rec.seq ? "#" + rec.seq : "", function (it) {
        closeFailures();
        openHistory(it.dag_id, it.task_id, it.node_id);
      });
    });
    var alertsBtn = document.getElementById("alerts-btn");
    if (alertsBtn) alertsBtn.addEventListener("click", function () { openAlertsLog(m); });
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
    renderCaseHead();
    fillBench();
    fillCases();
  }
  // Sortable case-table header: OUTCOME (plain) + TEST + TIME. TIME starts descending
  // so the slowest cases in the run surface first; clicking a header toggles direction.
  // Same ↑/↓ arrow + th.sortable styling as the run-list header on the main page.
  function caseHeadCell(key, label, cls) {
    var on = caseSort.key === key;
    var aria = on ? (caseSort.dir === "asc" ? "ascending" : "descending") : "none";
    var ar = on ? '<span class="arrow">' + (caseSort.dir === "asc" ? "↑" : "↓") + "</span>" : "";
    return '<th class="sortable' + (cls ? " " + cls : "") + '" data-key="' + key
      + '" role="button" tabindex="0" aria-sort="' + aria + '">' + esc(label) + ar + "</th>";
  }
  function renderCaseHead() {
    var head = document.getElementById("case-head");
    if (!head) return;
    head.innerHTML = caseHeadCell("outcome", t("hOutcome"), "")
      + caseHeadCell("node", t("hTest"), "")
      + caseHeadCell("time", t("hTime"), "right") + "<th></th>";
    head.querySelectorAll("th.sortable").forEach(function (th) {
      var fn = function () {
        var k = th.getAttribute("data-key");
        if (caseSort.key === k) caseSort.dir = caseSort.dir === "asc" ? "desc" : "asc";
        else caseSort = { key: k, dir: k === "time" ? "desc" : "asc" };
        renderCaseHead(); fillCases();
      };
      th.addEventListener("click", fn);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); }
      });
    });
  }
  // Outcome severity for sorting: ascending puts the broken tests first.
  var OUTCOME_RANK = { failed: 0, error: 1, skipped: 2, passed: 3 };
  // Compares two {c, i} case entries by the active sort (time numeric / outcome rank /
  // node string), with a stable tiebreak so equal rows keep a deterministic order.
  function caseCmp(a, b) {
    var dir = caseSort.dir === "asc" ? 1 : -1;
    if (caseSort.key === "time") {
      var d = (+a.c.time || 0) - (+b.c.time || 0);
      if (d) return d > 0 ? dir : -dir;
    } else if (caseSort.key === "outcome") {
      var ra = OUTCOME_RANK[a.c.outcome], rb = OUTCOME_RANK[b.c.outcome];
      if (ra === undefined) ra = 9;
      if (rb === undefined) rb = 9;
      if (ra !== rb) return (ra - rb) * dir;
    } else if (a.c.node_id !== b.c.node_id) {
      return (a.c.node_id < b.c.node_id ? -1 : 1) * dir;
    }
    if (a.c.node_id !== b.c.node_id) return a.c.node_id < b.c.node_id ? -1 : 1;
    return a.i - b.i;
  }

  function openDetail(id, focusNode) {
    filter = "all"; currentId = id;
    caseQuery = ""; caseGroup = false; caseCollapsed = {};
    caseSort = { key: "time", dir: "desc" };
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
      .then(function (d) {
        detail = d; detail.cases = d.cases || []; renderDetail();
        if (focusNode) focusCaseRow(focusNode);  // jump to + expand a specific test
      })
      .catch(function (e) {
        dBody.innerHTML = '<div class="state c-fail">' + esc(t("reportFail") + e.message) + "</div>";
      });
  }
  // Scroll the case table to a node, expand its output, and flash it (used when a heatmap
  // cell opens the run). The detail opened with filter=all + no grouping, so the row exists.
  function focusCaseRow(node) {
    var labels = dBody.querySelectorAll(".case-table tr.case .case-node");
    for (var i = 0; i < labels.length; i++) {
      if (labels[i].textContent === node) {
        var tr = labels[i].closest("tr.case");
        if (tr.getAttribute("aria-expanded") !== "true") tr.click();  // expand via its toggle
        tr.scrollIntoView({ block: "center" });
        tr.classList.add("case-focus");
        setTimeout(function () { tr.classList.remove("case-focus"); }, 1600);
        return;
      }
    }
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
    d.addEventListener("click", function (e) {
      // Only a genuine backdrop click closes: the target must BE the dialog element (the
      // backdrop), not a bubbled click from inner content. Without `e.target === d`, a
      // synthetic inner click (e.g. focusCaseRow's tr.click(), coords 0,0 -> reads as
      // "outside") would dismiss a just-opened dialog. Reset the flag so it never goes stale.
      if (startedOutside && e.target === d && outside(e)) closeFn();
      startedOutside = false;
    });
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
  // A single full-screen dim inside OUR document (standalone page, or the iframe when
  // embedded). One overlay no matter how many dialogs stack -- popups opened from inside the
  // run detail never add a second layer of darkening. Dialogs (top layer) render above it.
  function setLocalDim(on) {
    var ID = "apx-local-dim";
    var ov = document.getElementById(ID);
    if (on) {
      if (!ov) {
        ov = document.createElement("div");
        ov.id = ID;
        ov.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.5);"
          + "z-index:1000;pointer-events:none;";
        document.body.appendChild(ov);
      }
    } else if (ov && ov.parentNode) {
      ov.parentNode.removeChild(ov);
    }
  }
  function updateParentDim() {
    var anyOpen = (dlg && dlg.open) || (confirmDlg && confirmDlg.open)
      || (failuresDlg && failuresDlg.open) || (compareDlg && compareDlg.open)
      || (flakyDlg && flakyDlg.open) || (historyDlg && historyDlg.open)
      || (uniqueDlg && uniqueDlg.open) || (slowDlg && slowDlg.open)
      || (heatmapDlg && heatmapDlg.open) || (relInfoDlg && relInfoDlg.open)
      || (panelInfoDlg && panelInfoDlg.open) || (emailDlg && emailDlg.open)
      || (alertsDlg && alertsDlg.open);
    setLocalDim(anyOpen);   // dim our own page/iframe once
    setParentDim(anyOpen);  // and (embedded) the Airflow chrome around the iframe
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

  // Email-this-run dialog: POST the current run's token to /email. Recipients are validated
  // + capped server-side; the field is optional (empty -> the configured recipients). The
  // whole flow is RBAC-gated on the server, so a forbidden user just gets a 403 here.
  var emailDlg = document.getElementById("email-dlg");
  var emStatus = document.getElementById("em-status");
  var emSend = document.getElementById("em-send");
  var emTo = document.getElementById("em-to");
  function setEmStatus(msg, cls) {
    emStatus.hidden = !msg;
    emStatus.textContent = msg || "";
    emStatus.className = "em-status" + (cls ? " " + cls : "");
  }
  function openEmail() {
    if (!currentId) return;
    emTo.value = ""; setEmStatus("", ""); emSend.disabled = false;
    if (typeof emailDlg.showModal === "function") { if (!emailDlg.open) emailDlg.showModal(); }
    else emailDlg.setAttribute("open", "");
    updateParentDim();
    emTo.focus();
  }
  function closeEmail() { if (emailDlg.open) emailDlg.close(); else emailDlg.removeAttribute("open"); }
  // Mirrors the backend validator (the server re-checks anyway); instant, readable feedback.
  var EMAIL_JS_RE = /^[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+)*@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/;
  function validEmail(s) {
    return s.length <= 254 && s.indexOf("@") > 0
      && s.slice(0, s.indexOf("@")).length <= 64 && EMAIL_JS_RE.test(s);
  }
  function sendEmail() {
    if (!currentId) return;
    var raw = emTo.value.trim();
    var body = {};
    if (raw) {
      var list = raw.split(/[,;]/).map(function (s) { return s.trim(); }).filter(Boolean);
      // Validate BEFORE any request: name the bad address in the user's language.
      for (var i = 0; i < list.length; i++) {
        if (!validEmail(list[i])) {
          setEmStatus(t("emailInvalid").replace("{a}", list[i]), "err");
          return;
        }
      }
      // Dedupe case-insensitively so one mailbox gets one email.
      var seen = {}, uniq = [];
      list.forEach(function (a) {
        var k = a.toLowerCase();
        if (!seen[k]) { seen[k] = 1; uniq.push(a); }
      });
      body.recipients = uniq;
    }
    emSend.disabled = true; setEmStatus(t("emailSending"), "");
    fetch(API + "reports/" + encodeURIComponent(currentId) + "/email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
      if (res.ok && res.d && res.d.sent) {
        setEmStatus(t("emailSent"), "ok");
        setTimeout(function () { if (emailDlg.open) closeEmail(); }, 900);
      } else {
        // Show the server's reason (RBAC 403, 400 bad recipient, 503 no transport, 502 send fail).
        setEmStatus(t("emailFail") + (res.d && res.d.detail ? " " + res.d.detail : ""), "err");
        emSend.disabled = false;
      }
    }).catch(function () {
      setEmStatus(t("emailFail"), "err"); emSend.disabled = false;
    });
  }
  document.getElementById("d-email").addEventListener("click", openEmail);
  document.getElementById("em-cancel").addEventListener("click", closeEmail);
  emSend.addEventListener("click", sendEmail);
  emTo.addEventListener("keydown", function (e) { if (e.key === "Enter") sendEmail(); });
  emailDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(emailDlg, closeEmail);

  // Email-send log: the run's stored notification history (who was mailed, and whether the
  // handoff to the mail server succeeded), newest first.
  var alertsDlg = document.getElementById("alerts-dlg");
  function openAlertsLog(m) {
    var rows = (m.alerts || []).slice().reverse();
    document.getElementById("al-list").innerHTML = rows.map(function (a) {
      var mark = a.ok
        ? '<span class="al-ok" title="' + esc(t("alertsSentOk")) + '">✓</span>'
        : '<span class="al-fail" title="' + esc(t("alertsSentFail")) + '">✗</span>';
      var who = (a.recipients || []).map(function (r) { return esc(r); }).join(", ");
      var meta = [a.at ? fmtTime(a.at) : "", a.kind || "", t(a.manual ? "alertsManual" : "alertsAuto")]
        .filter(Boolean).map(esc).join(" · ");
      return '<div class="al-row">' + mark + '<div class="al-main">'
        + '<div class="al-rcpts">' + who + '</div><div class="al-meta">' + meta + "</div></div></div>";
    }).join("") || '<div class="state">' + esc(t("alertsEmpty")) + "</div>";
    if (typeof alertsDlg.showModal === "function") { if (!alertsDlg.open) alertsDlg.showModal(); }
    else alertsDlg.setAttribute("open", "");
    updateParentDim();
  }
  function closeAlertsLog() { if (alertsDlg.open) alertsDlg.close(); else alertsDlg.removeAttribute("open"); }
  document.getElementById("al-close").addEventListener("click", closeAlertsLog);
  alertsDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(alertsDlg, closeAlertsLog);

  // Failures modal: clicking the FAILURES KPI groups every failed/errored case across
  // the visible runs into clusters by normalized error (see /api/failure-clusters), so
  // common root causes surface instead of per-failure spam.
  var failuresDlg = document.getElementById("failures");
  var flBody = document.getElementById("fl-body");

  // Renders error clusters into `box`; each cluster expands to its failing tests, and a
  // test click calls onItem(test). Shared by the global modal and the per-run panel.
  function renderClusters(box, clusters, onItem) {
    if (!clusters || !clusters.length) {
      box.innerHTML = '<div class="state">' + esc(t("noFailures")) + "</div>";
      return;
    }
    box.innerHTML = clusters.map(function (c, i) {
      var dots = (c.outcomes || []).map(outcomeDot).join("");
      var head = '<div class="cl-row" tabindex="0" role="button" aria-expanded="false" data-i="' + i + '">'
        + '<span class="cl-count">' + (c.count || 0) + "×</span>"
        + '<span class="cl-sig mono">' + esc(c.signature || c.sample || "?") + "</span>"
        + '<span class="cl-dots">' + dots + '</span><span class="chev">' + CHEV + "</span></div>";
      var items = (c.tests || []).map(function (it) {
        return '<div class="cl-item" tabindex="0" role="button" data-id="' + esc(it.id)
          + '" data-node="' + esc(it.node_id) + '" data-dag="' + esc(it.dag_id)
          + '" data-task="' + esc(it.task_id) + '" data-outcome="' + esc(it.outcome) + '">'
          + outcomeDot(it.outcome) + '<span class="mono">' + esc(it.node_id) + "</span>"
          + '<span class="muted">' + esc(it.dag_id) + "·" + esc(it.task_id) + "</span></div>";
      }).join("");
      return head + '<div class="cl-items" data-items="' + i + '" hidden>' + items + "</div>";
    }).join("");
    box.querySelectorAll(".cl-row").forEach(function (row) {
      var toggle = function () {
        var its = box.querySelector('.cl-items[data-items="' + row.getAttribute("data-i") + '"]');
        var open = row.getAttribute("aria-expanded") === "true";
        row.setAttribute("aria-expanded", String(!open));
        if (its) its.hidden = open;
      };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      });
    });
    box.querySelectorAll(".cl-item").forEach(function (el) {
      var act = function (e) {
        e.stopPropagation();
        onItem({
          id: el.getAttribute("data-id"), node_id: el.getAttribute("data-node"),
          dag_id: el.getAttribute("data-dag"), task_id: el.getAttribute("data-task"),
          outcome: el.getAttribute("data-outcome"),
        });
      };
      el.addEventListener("click", act);
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); act(e); }
      });
    });
  }

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
  // Opens the failures dialog and loads clusters for the given query scope. ``onItem``
  // handles a click on a test inside a cluster. Used globally (KPI) and per-run (detail).
  // Narrow server-built clusters to the picked dag·task group(s): keep only the matching
  // tests, recompute the per-cluster count, drop emptied clusters, re-sort biggest-first.
  function scopeClusters(clusters, keys) {
    var out = [];
    (clusters || []).forEach(function (c) {
      var tests = (c.tests || []).filter(function (tt) { return keys[tt.dag_id + "|" + tt.task_id]; });
      if (tests.length) {
        out.push({ signature: c.signature, sample: c.sample, outcomes: c.outcomes,
          count: tests.length, tests: tests });
      }
    });
    out.sort(function (a, b) { return b.count - a.count; });
    return out;
  }
  function openClusters(qs, subtitle, onItem, scopeKeys) {
    if (typeof failuresDlg.showModal === "function") { if (!failuresDlg.open) failuresDlg.showModal(); }
    else failuresDlg.setAttribute("open", "");
    updateParentDim();
    document.getElementById("fl-title").textContent =
      t("failuresTitle") + (subtitle ? " · " + subtitle : "");
    flBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    fetch(API + "failure-clusters" + qs)
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        var clusters = d.clusters || [];
        if (scopeKeys) clusters = scopeClusters(clusters, scopeKeys);
        var cap = (d.capped && !scopeKeys)
          ? '<div class="state muted">' + esc(t("failCapped").replace("{n}", d.total)) + "</div>" : "";
        flBody.innerHTML = '<div id="cl-list"></div>' + cap;
        renderClusters(document.getElementById("cl-list"), clusters, onItem);
      })
      .catch(function (e) {
        flBody.innerHTML = '<div class="state c-fail">' + esc(t("failuresFail") + e.message) + "</div>";
      });
  }
  function openFailures() {
    var sk = selKeySet();
    openClusters(filterQuery(), sk ? t("flkSelScope") : "", function (it) {
      openDetail(it.id);      // resets filter to "all"...
      filter = it.outcome;    // ...then land on the failing cases
      closeFailures();
    }, sk);
  }
  function closeFailures() {
    if (failuresDlg.open) failuresDlg.close(); else failuresDlg.removeAttribute("open");
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
  // Per-test stats line in the catalogue: total runs, average time, and per-outcome
  // counts (only the non-zero ones, each a coloured dot + count) -- all from /api/slow's
  // sibling scan in /api/unique-tests, so no extra request.
  function uqStats(x) {
    if (x.runs == null) return "";  // tolerate an older API without stats
    var parts = [
      '<span class="uq-tot" title="' + esc(t("uqRuns")) + '">' + (x.runs || 0) + "×</span>",
      '<span class="uq-avg">' + esc(t("avgWord")) + " " + esc(fmtDur(x.avg_duration || 0)) + "</span>",
    ];
    [["passed", x.passed], ["failed", x.failed], ["error", x.errors], ["skipped", x.skipped]]
      .forEach(function (o) {
        if (o[1]) {
          parts.push('<span class="uq-st" title="' + esc(outcomeLabel(o[0])) + '">'
            + outcomeDot(o[0]) + o[1] + "</span>");
        }
      });
    return '<span class="uq-meta">' + parts.join("") + "</span>";
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
            + '<span class="mono uq-node">' + esc(x.node_id) + "</span>" + uqStats(x) + "</div>";
        }).join("")
      : '<div class="state">' + esc(t("noCases")) + "</div>";
    listEl.querySelectorAll(".uq-row").forEach(function (row) {
      var open = function () {
        // Merge across every dag·task this node id ran in -- matches the aggregated count
        // shown on the row (the same test triggered from two places is one timeline).
        openHistory(null, null, row.getAttribute("data-node"));
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
  var flkSeq = 0;  // guards against a stale window's response overwriting a newer one
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
    var my = ++flkSeq;  // ignore a stale window's response landing after a newer one
    fetch(API + "flaky?" + q.toString())
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { if (my !== flkSeq) return; fkState.rows = d.flaky || []; fillFlakyRows(); })
      .catch(function (e) {
        if (my !== flkSeq) return;
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
        + '<span class="fk-main"><span class="node mono">' + esc(f.node_id) + "</span>"
        + (f.quarantined ? '<span class="fk-sub">' + quarantineBadge(f) + "</span>" : "")
        + "</span>"
        + '<span class="fk-meta">' + flakyMeta(f) + "</span></div>";
    }).join("");
  }
  function closeFlaky() { if (flakyDlg.open) flakyDlg.close(); else flakyDlg.removeAttribute("open"); }
  document.getElementById("fk-close").addEventListener("click", closeFlaky);
  flakyDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(flakyDlg, closeFlaky);

  // Slow tests & duration regressions across all dag·tasks: a "got slower" section
  // (recent-half avg vs older half) plus a slowest-by-average leaderboard. One window
  // selector; the global scan primes the first open so it's instant.
  var slowDlg = document.getElementById("slow");
  var slBody = document.getElementById("sl-body");
  var slowState = { window: 0, data: null };
  function slowLoc(x) {
    return '<span class="slow-loc muted">' + esc(x.dag_id) + "·" + esc(x.task_id) + "</span>";
  }
  function slowRowReg(x) {
    return '<div class="slow-row"><span class="node mono">' + esc(x.node_id) + "</span>"
      + slowLoc(x) + '<span class="slow-meta"><span class="slow-up">▲</span> '
      + esc(fmtDur(x.old_avg)) + " → <b>" + esc(fmtDur(x.new_avg)) + "</b>"
      + (x.ratio ? ' <span class="slow-ratio">×' + x.ratio + "</span>" : "") + "</span></div>";
  }
  function slowRowAvg(x) {
    return '<div class="slow-row"><span class="node mono">' + esc(x.node_id) + "</span>"
      + slowLoc(x) + '<span class="slow-meta"><b>' + esc(fmtDur(x.avg)) + "</b>"
      + (x.regressed ? ' <span class="slow-up" title="' + esc(t("slowRegressing")) + '">▲</span>' : "")
      + "</span></div>";
  }
  function openSlow() {
    if (!slowState.window) slowState.window = (slowData && slowData.window) || 30;
    if (typeof slowDlg.showModal === "function") { if (!slowDlg.open) slowDlg.showModal(); }
    else slowDlg.setAttribute("open", "");
    updateParentDim();
    slBody.innerHTML = '<div class="flk-ctrls"><label title="' + esc(t("flkWindowTip")) + '">'
      + esc(t("flkWindow")) + ' <select id="sl-win">'
      + FLK_WINDOWS.map(function (w) {
          return '<option value="' + w + '"' + (w === slowState.window ? " selected" : "") + ">"
            + esc(t("flkWinOpt").replace("{n}", w)) + "</option>";
        }).join("")
      + "</select></label></div><div id=\"sl-list\"></div>";
    document.getElementById("sl-win").addEventListener("change", function () {
      slowState.window = +this.value; loadSlowModal();
    });
    if (slowData && slowData.window === slowState.window) {
      slowState.data = slowData; fillSlow();
    } else {
      loadSlowModal();
    }
  }
  function loadSlowModal() {
    var listEl = document.getElementById("sl-list");
    if (listEl) {
      listEl.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    }
    var my = ++slowModalSeq;  // ignore a stale window/filter response after a newer one
    fetch(API + "slow?" + slowQuery(slowState.window))
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { if (my !== slowModalSeq) return; slowState.data = d; fillSlow(); })
      .catch(function (e) {
        if (my !== slowModalSeq) return;
        var el = document.getElementById("sl-list");
        if (el) el.innerHTML = '<div class="state c-fail">' + esc(t("slowFail") + e.message) + "</div>";
      });
  }
  function fillSlow() {
    var listEl = document.getElementById("sl-list");
    if (!listEl || !slowState.data) return;
    var d = slowState.data, reg = d.regressed || [], slowest = d.slowest || [];
    // Scope to the picked dag·task group(s), like the flaky panel + the KPI count.
    var sk = selKeySet();
    if (sk) {
      var inSel = function (x) { return sk[x.dag_id + "|" + x.task_id]; };
      reg = reg.filter(inSel); slowest = slowest.filter(inSel);
    }
    var title = document.getElementById("sl-title");
    if (title) title.textContent = t("slowTitle") + (sk ? " · " + t("flkSelScope") : "");
    listEl.innerHTML =
      '<div class="slow-sec"><h3><span class="slow-up">▲</span> ' + esc(t("slowRegressing"))
        + " (" + reg.length + ")</h3>"
      + (reg.length ? reg.map(slowRowReg).join("")
          : '<div class="state">' + esc(t("slowNoneReg")) + "</div>")
      + "</div><div class=\"slow-sec\"><h3>" + esc(t("slowSlowest"))
        + " (" + slowest.length + ")</h3>"
      + (slowest.length ? slowest.map(slowRowAvg).join("")
          : '<div class="state">' + esc(t("slowNoData")) + "</div>")
      + "</div>";
  }
  function closeSlow() { if (slowDlg.open) slowDlg.close(); else slowDlg.removeAttribute("open"); }
  document.getElementById("sl-close").addEventListener("click", closeSlow);
  slowDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(slowDlg, closeSlow);

  // Test history: one test's outcome + duration across the runs of its dag·task.
  var historyDlg = document.getElementById("history");
  var histBody = document.getElementById("hist-body");
  function openHistory(dag, task, node) {
    if (typeof historyDlg.showModal === "function") { if (!historyDlg.open) historyDlg.showModal(); }
    else historyDlg.setAttribute("open", "");
    updateParentDim();
    histBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    // dag/task omitted (Unique tests) -> the server merges this node id across every place
    // it ran; given -> just that dag·task's runs.
    var params = { node_id: node };
    if (dag) params.dag_id = dag;
    if (task) params.task_id = task;
    var q = new URLSearchParams(params);
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
    // Make the (capped) window explicit: the timeline shows only the newest N runs.
    head += '<div class="hist-count">' + esc(t("histCount").replace("{n}", rows.length)) + "</div>";
    histBody.innerHTML = head + rows.map(function (h) {
      var label = h.outcome ? outcomeLabel(h.outcome) : t("histDidntRun");
      var dur = h.duration != null ? fmtDur(h.duration) : "";
      // Merged history (opened from Unique tests) tags each run with its dag·task so it's
      // clear the same test ran from more than one place.
      var loc = h.dag_id ? ' · <span class="hist-loc">' + esc(h.dag_id + "·" + h.task_id)
        + "</span>" : "";
      return '<div class="hist-row">' + outcomeDot(h.outcome)
        + '<span class="when">' + esc(label) + " · " + esc(fmtTime(h.created_at)) + loc + "</span>"
        + '<span class="dur">' + esc(dur) + "</span></div>";
    }).join("");
  }
  document.getElementById("hist-close").addEventListener("click", closeHistory);
  historyDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(historyDlg, closeHistory);

  // Test×run heatmap: a per-dag·task matrix (rows = tests sorted most-broken first,
  // columns = recent runs old→new, cell = outcome) so flaky rows, regression blocks and
  // a build-breaking run read at a glance. A FIXED test-name column + a drag/scroll cell
  // carousel (like the runs chart) -- cells slide under the names, never over. Same window
  // selector as flaky/slow; hover shows the plugin's tooltip; click a cell to open that
  // run, a test name to open its history. Delegated handlers + closure data (no per-cell
  // listeners) keep it light at the row/column caps.
  var heatmapDlg = document.getElementById("heatmap");
  var hmBody = document.getElementById("hm-body");
  var hmState = { dag: null, task: null, window: 30 };
  var hmData = null;  // last rendered {runs, tests}; read by the delegated tooltip + clicks
  var hmSeq = 0;      // guards against a stale window's response overwriting a newer one
  var hmSel = { p: true, f: true, e: true, s: true };  // legend focus (mirrors chartSel)
  var HM_COLOR = { p: "--pass", f: "--fail", e: "--error", s: "--skip" };
  function hmOutcome(code) {
    return { p: "passed", f: "failed", e: "error", s: "skipped" }[code] || "";
  }
  function hmAllOn() { return hmSel.p && hmSel.f && hmSel.e && hmSel.s; }
  function applyHmFocus() {
    // Drive the dimming from container classes (no per-cell work, fine at the caps).
    var cellsEl = document.querySelector("#hm-grid .hm-cells");
    if (!cellsEl) return;
    var on = !hmAllOn();
    cellsEl.classList.toggle("foc", on);
    ["p", "f", "e", "s"].forEach(function (k) { cellsEl.classList.toggle("foc-" + k, on && hmSel[k]); });
  }
  function renderHmLegend() {
    var el = document.getElementById("hm-legend");
    if (!el) return;
    el.innerHTML = ["p", "f", "e", "s"].map(function (k) {
        return '<button type="button" class="hm-lg' + (hmSel[k] ? "" : " off")
          + '" data-o="' + k + '" aria-pressed="' + !!hmSel[k] + '">'
          + '<span class="hm-cell" style="background:var(' + HM_COLOR[k] + ')"></span>'
          + esc(outcomeLabel(hmOutcome(k))) + "</button>";
      }).join("")
      + '<span class="hm-lg"><span class="hm-cell hm-miss"></span>' + esc(t("histDidntRun")) + "</span>"
      + (hmAllOn() ? "" : '<button type="button" class="hm-reset">' + esc(t("legendReset")) + "</button>");
    el.querySelectorAll("button.hm-lg").forEach(function (b) {
      b.addEventListener("click", function () {
        // Same "focus" model as the runs-chart legend: click shows only that status;
        // click more to add/remove; emptying falls back to all-shown.
        var s = b.getAttribute("data-o");
        if (hmAllOn()) { ["p", "f", "e", "s"].forEach(function (k) { hmSel[k] = k === s; }); }
        else {
          hmSel[s] = !hmSel[s];
          if (!hmSel.p && !hmSel.f && !hmSel.e && !hmSel.s) hmSel.p = hmSel.f = hmSel.e = hmSel.s = true;
        }
        renderHmLegend(); applyHmFocus();
      });
    });
    var rst = el.querySelector(".hm-reset");
    if (rst) rst.addEventListener("click", function () {
      hmSel.p = hmSel.f = hmSel.e = hmSel.s = true; renderHmLegend(); applyHmFocus();
    });
  }
  function hmShort(node) {
    // Drop the file path, keep class::test (the informative tail); full id is in the tooltip.
    var i = node.indexOf("::");
    return i >= 0 ? node.slice(i + 2) : node;
  }
  function findRun(dag, task, run) {
    var best = null;  // newest try of this dag·task·run, to open its detail on click
    allReports.forEach(function (x) {
      if (x.dag_id === dag && x.task_id === task && x.run_id === run
          && (!best || (x.try_number || 0) > (best.try_number || 0))) best = x;
    });
    return best;
  }
  // The heatmap's own drag-to-pan -- deliberately NOT the chart's, whose `chartDragged`
  // resets on a setTimeout that fires after `click`, so a slightly-draggy cell click would
  // be swallowed. `hmDragMoved` is read synchronously by the click handler and reset on the
  // next pointerdown, so a real pan is suppressed but an ordinary click always lands.
  var hmDrag = null, hmDragMoved = 0;
  function enableHmDrag(el) {
    el.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "touch") return;  // touch/trackpad use native scroll
      hmDrag = { el: el, x: e.clientX, left: el.scrollLeft };
      el.classList.add("dragging");
    });
  }
  function hmDragMove(e) {
    if (!hmDrag) return;
    var dx = e.clientX - hmDrag.x;
    if (Math.abs(dx) > hmDragMoved) hmDragMoved = Math.abs(dx);
    hmDrag.el.scrollLeft = hmDrag.left - dx;
  }
  function hmDragEnd() {
    if (!hmDrag) return;
    hmDrag.el.classList.remove("dragging");
    hmDrag = null;  // hmDragMoved persists until the next pointerdown so click() can read it
  }
  function hmCellTip(cell, ev) {
    if (!hmData) return;
    var r = +cell.getAttribute("data-r"), c = +cell.getAttribute("data-c");
    var tt = hmData.tests[r], run = hmData.runs[c] || {};
    if (!tt) return;
    var code = tt.cells[c], col = HM_COLOR[code] || "--muted";
    var label = code === "-" ? t("histDidntRun") : outcomeLabel(hmOutcome(code));
    tipShow(
      '<div class="tt">' + esc(hmShort(tt.node_id)) + "</div>"
      + '<div class="tm wrap">' + esc(tt.node_id) + "</div>"
      + '<div class="tm">#' + (c + 1)
        + (run.created_at ? " · " + esc(fmtTime(run.created_at)) : "") + "</div>"
      + '<div class="tr"><span><i style="background:var(' + col + ')"></i>'
        + esc(label) + "</span></div>",
      ev,
    );
  }
  function openHeatmap(dag, task) {
    hmState.dag = dag; hmState.task = task; hmState.window = 30;
    hmSel.p = hmSel.f = hmSel.e = hmSel.s = true;  // reset the legend focus per open
    // Inset (narrower than the run dialog) when opened from inside a run; wide otherwise.
    var det = document.getElementById("detail");
    heatmapDlg.classList.toggle("hm-inset", !!(det && det.open));
    if (typeof heatmapDlg.showModal === "function") { if (!heatmapDlg.open) heatmapDlg.showModal(); }
    else heatmapDlg.setAttribute("open", "");
    updateParentDim();
    var title = document.getElementById("hm-title");
    if (title) title.textContent = t("heatmapTitle") + " · " + dag + "·" + task;
    hmBody.innerHTML = '<div class="flk-ctrls"><label title="' + esc(t("flkWindowTip")) + '">'
      + esc(t("flkWindow")) + ' <select id="hm-win">'
      + FLK_WINDOWS.map(function (w) {
          return '<option value="' + w + '"' + (w === hmState.window ? " selected" : "") + ">"
            + esc(t("flkWinOpt").replace("{n}", w)) + "</option>";
        }).join("")
      + "</select></label></div>"
      + '<div class="hm-legend" id="hm-legend"></div>'  // legend on top: visible without scrolling
      + '<div id="hm-grid"></div>';
    document.getElementById("hm-win").addEventListener("change", function () {
      hmState.window = +this.value; loadHeatmap();
    });
    var grid = document.getElementById("hm-grid");
    grid.addEventListener("pointerdown", function () { hmDragMoved = 0; });  // fresh per gesture
    grid.addEventListener("click", function (e) {
      if (hmDragMoved > 6) return;  // a real pan shouldn't open anything; a click always does
      var name = e.target.closest(".hm-name");
      if (name) { closeHeatmap(); openHistory(hmState.dag, hmState.task, name.getAttribute("data-node")); return; }
      var cell = e.target.closest(".hm-cell");
      if (cell && cell.hasAttribute("data-c") && !cell.classList.contains("hm-miss") && hmData) {
        var run = hmData.runs[+cell.getAttribute("data-c")];
        var tt = hmData.tests[+cell.getAttribute("data-r")];
        var rec = run && findRun(hmState.dag, hmState.task, run.run_id);
        if (rec) { closeHeatmap(); openDetail(rec.id, tt && tt.node_id); }  // jump to that test
      }
    });
    grid.addEventListener("mouseover", function (e) {
      var cell = e.target.closest(".hm-cell");
      if (cell && cell.hasAttribute("data-r")) hmCellTip(cell, e);  // instant, no hover delay
    });
    grid.addEventListener("mousemove", function (e) {
      if (tipEl && tipEl.style.display === "block") tipMove(e);
    });
    grid.addEventListener("mouseout", function (e) {
      if (e.target.closest(".hm-cell")) tipHide();
    });
    loadHeatmap();
  }
  function loadHeatmap() {
    var gridEl = document.getElementById("hm-grid");
    if (gridEl) gridEl.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    var q = new URLSearchParams({
      dag_id: hmState.dag, task_id: hmState.task, window: String(hmState.window),
    });
    var my = ++hmSeq;
    fetch(API + "heatmap?" + q.toString())
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { if (my !== hmSeq) return; renderHeatmap(d); })
      .catch(function (e) {
        if (my !== hmSeq) return;
        var el = document.getElementById("hm-grid");
        if (el) el.innerHTML = '<div class="state c-fail">' + esc(t("heatmapFail") + e.message) + "</div>";
      });
  }
  function renderHeatmap(d) {
    var gridEl = document.getElementById("hm-grid");
    if (!gridEl) return;
    hmData = d;
    var runs = d.runs || [], tests = d.tests || [], n = runs.length;
    if (!tests.length) { gridEl.innerHTML = '<div class="state">' + esc(t("heatmapEmpty")) + "</div>"; return; }
    // Fixed column of test names (short, readable; full id on hover) -- the corner spacer
    // matches the run-header row height so rows line up with the scrolling pane.
    var names = '<div class="hm-corner"></div>' + tests.map(function (tt) {
      return '<button type="button" class="hm-name" data-node="' + esc(tt.node_id)
        + '" title="' + esc(tt.node_id) + '"><span>' + esc(hmShort(tt.node_id)) + "</span></button>";
    }).join("");
    // Scrolling pane: a run-number header row, then one row of cells per test.
    // Shrink the header font when the largest label has more digits, so e.g. "#100" or
    // "#1000" stays inside its cell instead of spilling over its neighbour.
    var digits = String(n).length;
    var rheadFs = digits <= 2 ? 9 : digits === 3 ? 8 : 6;
    var head = "";
    for (var c = 0; c < n; c++) {
      var show = (c % 5 === 0) || (c === n - 1);  // label every 5th run + the last
      head += '<div class="hm-rhead">' + (show ? "#" + (c + 1) : "") + "</div>";
    }
    var cells = tests.map(function (tt, r) {
      return (tt.cells || []).map(function (code, c) {
        var miss = code === "-";
        var bg = miss ? "" : ' style="background:var(' + (HM_COLOR[code] || "--muted") + ')"';
        return '<span class="hm-cell' + (miss ? " hm-miss" : "") + '" data-o="' + code
          + '" data-r="' + r + '" data-c="' + c + '"' + bg + "></span>";
      }).join("");
    }).join("");
    var note = d.truncated
      ? '<div class="hm-note">' + esc(t("heatmapTrunc").replace("{m}", tests.length).replace("{n}", d.total_tests)) + "</div>"
      : "";
    var cols = "grid-template-columns:repeat(" + n + ", var(--hm-cell))";
    gridEl.innerHTML = '<div class="hm-wrap"><div class="hm-names">' + names + "</div>"
      + '<div class="hm-scroll">'
      + '<div class="hm-headrow" style="--hm-rhead-fs:' + rheadFs + "px;" + cols + '">' + head + "</div>"
      + '<div class="hm-cells" style="' + cols + '">' + cells + "</div>"
      + "</div></div>" + note;
    enableHmDrag(gridEl.querySelector(".hm-scroll"));  // heatmap-local drag-to-pan
    renderHmLegend(); applyHmFocus();  // clickable status focus, like the chart legend
  }
  function closeHeatmap() { if (heatmapDlg.open) heatmapDlg.close(); else heatmapDlg.removeAttribute("open"); }
  document.getElementById("hm-close").addEventListener("click", closeHeatmap);
  heatmapDlg.addEventListener("close", updateParentDim);
  closeOnBackdrop(heatmapDlg, closeHeatmap);

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
  document.addEventListener("pointermove", hmDragMove);
  document.addEventListener("pointerup", hmDragEnd);
  document.addEventListener("pointercancel", hmDragEnd);
  // Debounce the top filters: each keystroke otherwise re-renders the whole page
  // (chart + list + KPIs + flaky) -- costly on large datasets. Call with no arg so it
  // resets to page 1 / newest (binding the listener directly passes the Event as the
  // keepPage flag, which wrongly preserved the page).
  var debouncedFilter = debounce(function () { applyFilter(); }, 150);
  ["f-dag", "f-task", "f-run"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", debouncedFilter);
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
  var fClear = document.getElementById("f-clear");
  if (fClear) fClear.addEventListener("click", function () {
    ["f-dag", "f-task", "f-run"].forEach(function (id) { document.getElementById(id).value = ""; });
    applyFilter();  // re-filters + hides this button
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
