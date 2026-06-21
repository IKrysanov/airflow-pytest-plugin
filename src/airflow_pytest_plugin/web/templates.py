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

"""The single-page viewer (dependency-free HTML/CSS/JS, no build step).

Data-dense dashboard styling with light/dark tokens and inline SVG icons. The
theme follows Airflow: embedded in Airflow's (same-origin) iframe it reads the
parent's colour mode and tracks changes live, falling back to the OS preference
when run standalone. Test cases expand in place to show their traceback.
"""

from __future__ import annotations

_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Pytest Reports</title>
<style>
  :root {
    --bg: #f8fafc; --surface: #ffffff; --surface-2: #f1f5f9;
    --fg: #0f172a; --muted: #64748b; --border: #e2e8f0;
    --primary: #1e40af; --on-primary: #ffffff; --ring: #1e40af33;
    --pass: #16a34a; --fail: #dc2626; --skip: #d97706; --error: #7c3aed;
    --pass-bg: #16a34a1a; --fail-bg: #dc26261a; --skip-bg: #d977061a; --error-bg: #7c3aed1a;
    --shadow: 0 1px 2px #0f172a14, 0 1px 3px #0f172a1f;
  }
  html[data-theme="dark"] {
    --bg: #0b1220; --surface: #111a2e; --surface-2: #16233d;
    --fg: #e2e8f0; --muted: #94a3b8; --border: #24314c;
    --primary: #3b82f6; --on-primary: #0b1220; --ring: #3b82f655;
    --pass: #4ade80; --fail: #f87171; --skip: #fbbf24; --error: #c4b5fd;
    --pass-bg: #4ade8019; --fail-bg: #f8717119; --skip-bg: #fbbf2419; --error-bg: #c4b5fd19;
    --shadow: 0 1px 2px #0006, 0 1px 3px #0008;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .num { font-variant-numeric: tabular-nums; }
  .muted { color: var(--muted); }

  header {
    position: sticky; top: 0; z-index: 20; background: var(--surface);
    border-bottom: 1px solid var(--border); display: flex; align-items: center;
    gap: 12px; padding: 12px 20px; flex-wrap: wrap;
  }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 650;
    font-size: 16px; letter-spacing: -.01em; }
  .brand svg { color: var(--primary); }
  .grow { flex: 1 1 auto; }
  input, button { font: inherit; color: var(--fg); }
  .field {
    background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 8px; padding: 7px 11px; flex: 0 1 170px; min-width: 120px;
  }
  .field:focus { outline: 2px solid var(--ring); outline-offset: 1px; border-color: var(--primary); }
  .btn {
    background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 8px; padding: 7px 12px; cursor: pointer;
    display: inline-flex; align-items: center; gap: 7px; transition: background .15s, border-color .15s;
  }
  .btn:hover { background: var(--border); }
  .btn:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .btn.primary { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
  .btn.primary:hover { filter: brightness(1.08); }
  .icon-btn { padding: 7px; }

  main { padding: 18px 20px 40px; max-width: 1600px; margin: 0 auto; }

  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 18px; }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; box-shadow: var(--shadow); }
  .kpi .label { font-size: 12px; color: var(--muted); text-transform: uppercase;
    letter-spacing: .04em; }
  .kpi .value { font-size: 26px; font-weight: 700; margin-top: 4px; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    box-shadow: var(--shadow); overflow: hidden; }
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
  dialog::backdrop { background: #0f172a99; backdrop-filter: blur(2px); }
  .dlg-head { display: flex; align-items: center; gap: 12px; padding: 16px 20px;
    border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); }
  .dlg-head h2 { margin: 0; font-size: 15px; font-weight: 650; }
  .dlg-body { padding: 18px 20px 22px; max-height: 72vh; overflow: auto; }
  .pills { display: flex; flex-wrap: wrap; gap: 7px; margin: 16px 0 12px; }
  .pill { border: 1px solid var(--border); background: var(--surface-2); color: var(--fg);
    border-radius: 999px; padding: 5px 12px; cursor: pointer; font-size: 13px;
    transition: background .12s, border-color .12s; }
  .pill:hover { border-color: var(--primary); }
  .pill[aria-pressed="true"] { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
  .pill:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .case-node { display: inline-block; max-width: 60ch; overflow-wrap: anywhere; }
  .case.clickable[aria-expanded="true"] { background: var(--surface-2); }
  .chev { display: inline-flex; color: var(--muted); transition: transform .15s; }
  .case[aria-expanded="true"] .chev { transform: rotate(90deg); }
  .case-exp > td { padding: 0 12px 12px; border-bottom: 1px solid var(--border); }
  /* The traceback blends into the row -- no boxed frame, just a quote rule. */
  .tb { margin: 0; padding: 2px 0 6px 12px; border-left: 2px solid var(--border);
    overflow-x: auto; max-width: 100%; font-size: 12.5px; line-height: 1.55;
    white-space: pre; color: var(--fg); }

  @media (max-width: 680px) {
    header { padding: 10px 12px; gap: 8px; }
    main { padding: 12px 12px 32px; }
    th, td { padding: 8px 9px; }
    .kpi { padding: 12px 13px; }
    .kpi .value { font-size: 22px; }
    .dlg-head { padding: 13px 14px; }
    .dlg-body { padding: 14px 14px 18px; }
  }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>
</head>
<body>
<header>
  <span class="brand">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M9 3h6M10 3v6.3a2 2 0 0 1-.4 1.2L4.5 18a2 2 0 0 0 1.6 3.2h11.8a2 2 0 0 0 1.6-3.2l-5.1-7.5a2 2 0 0 1-.4-1.2V3"/>
      <path d="M7.2 15h9.6"/>
    </svg>
    Pytest Reports
  </span>
  <span class="grow"></span>
  <input id="f-dag" class="field" placeholder="filter dag_id" aria-label="Filter by dag_id"
         list="dags" autocomplete="off" />
  <input id="f-run" class="field" placeholder="filter run_id" aria-label="Filter by run_id"
         list="runs" autocomplete="off" />
  <datalist id="dags"></datalist>
  <datalist id="runs"></datalist>
  <button id="refresh" class="btn primary" type="button">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/>
    </svg>
    Refresh
  </button>
</header>

<main>
  <div class="kpis" id="kpis" hidden></div>
  <div class="card"><div id="list"></div></div>
</main>

<dialog id="detail" aria-labelledby="d-title">
  <div class="dlg-head">
    <h2 id="d-title">Report</h2>
    <span class="grow"></span>
    <button id="d-close" class="btn icon-btn" type="button" aria-label="Close report">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12"/>
      </svg>
    </button>
  </div>
  <div class="dlg-body" id="d-body"></div>
</dialog>

<script>
(function () {
  // API base derived from the current path: works under any mount prefix and in
  // the Airflow iframe (e.g. /pytest-reports/ -> /pytest-reports/api/).
  var API = location.pathname.replace(/\/+$/, "") + "/api/";

  var ICONS = {
    pass: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
    fail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    skip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4v16M19 5v14"/><path d="M19 12 9 5v14z"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></svg>',
  };
  var CHEV = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmtDur(s) { return (Number(s) || 0).toFixed(2) + "s"; }
  function fmtTime(s) {
    if (!s) return "—";
    var d = new Date(s);
    return isNaN(d) ? esc(s) : d.toLocaleString();
  }
  function statusOf(r) { return r.success ? "pass" : (r.errors > 0 ? "error" : "fail"); }
  function badge(kind, text) {
    return '<span class="badge b-' + kind + '">' + ICONS[kind] + esc(text) + "</span>";
  }

  /* ---- theme: follow Airflow -----------------------------------------
     Embedded in Airflow's same-origin iframe, derive the colour mode from the
     parent document (explicit class/attr, else background luminance) and track
     changes live. Standalone, fall back to the OS preference. */
  function luminance(rgb) {
    var m = /rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/.exec(rgb || "");
    if (!m) return null;
    if (m[4] !== undefined && parseFloat(m[4]) === 0) return null;  // transparent
    return (0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]) / 255;
  }
  function parentDoc() {
    try {
      if (window.parent && window.parent !== window) return window.parent.document;
    } catch (e) { /* cross-origin / sandboxed */ }
    return null;
  }
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
    } catch (e) { /* fall through */ }
    return null;
  }
  function systemTheme() {
    return (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  }
  function applyTheme() {
    document.documentElement.setAttribute("data-theme", airflowTheme() || systemTheme());
  }
  applyTheme();
  (function watchTheme() {
    var pdoc = parentDoc();
    if (pdoc && window.MutationObserver) {
      try {
        var mo = new MutationObserver(applyTheme);
        var opts = { attributes: true, attributeFilter: ["class", "style", "data-theme", "data-color-mode"] };
        mo.observe(pdoc.documentElement, opts);
        if (pdoc.body) mo.observe(pdoc.body, opts);
      } catch (e) {}
    }
    if (window.matchMedia) {
      try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme); } catch (e) {}
    }
    window.addEventListener("storage", applyTheme);
  })();

  /* ---- list ----------------------------------------------------------- */
  var listEl = document.getElementById("list");
  var kpisEl = document.getElementById("kpis");
  var allReports = [];  // everything fetched
  var reports = [];     // the current filtered view
  var sort = { key: "created_at", dir: -1 };

  var COLS = [
    { key: "status", label: "Status", get: function (r) { return r.success ? 2 : (r.errors ? 0 : 1); } },
    { key: "dag_id", label: "DAG", cls: "mono" },
    { key: "task_id", label: "Task", cls: "mono" },
    { key: "run_id", label: "Run", cls: "mono muted" },
    { key: "try_number", label: "Try", num: true },
    { key: "total", label: "Total", num: true },
    { key: "passed", label: "Pass", num: true, color: "c-pass" },
    { key: "failed", label: "Fail", num: true, color: "c-fail" },
    { key: "errors", label: "Err", num: true, color: "c-error" },
    { key: "skipped", label: "Skip", num: true, color: "c-skip" },
    { key: "duration", label: "Duration", num: true },
    { key: "created_at", label: "When" },
  ];

  function renderKpis() {
    if (!reports.length) { kpisEl.hidden = true; return; }
    var runs = reports.length;
    var ok = reports.filter(function (r) { return r.success; }).length;
    var tests = reports.reduce(function (a, r) { return a + r.total; }, 0);
    var failures = reports.reduce(function (a, r) { return a + r.failed + r.errors; }, 0);
    var cards = [
      { label: "Runs", value: runs },
      { label: "Passing runs", value: ok + " / " + runs, cls: ok === runs ? "c-pass" : "" },
      { label: "Tests", value: tests },
      { label: "Failures", value: failures, cls: failures ? "c-fail" : "c-pass" },
    ];
    kpisEl.hidden = false;
    kpisEl.innerHTML = cards.map(function (c) {
      return '<div class="kpi"><div class="label">' + c.label + '</div>'
        + '<div class="value ' + (c.cls || "") + '">' + esc(c.value) + "</div></div>";
    }).join("");
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

  function renderRows() {
    return reports.map(function (r) {
      var st = statusOf(r);
      var cells = COLS.map(function (c) {
        if (c.key === "status") return "<td>" + badge(st, st.toUpperCase()) + "</td>";
        if (c.key === "duration") return '<td class="num">' + fmtDur(r.duration) + "</td>";
        if (c.key === "created_at") return '<td class="muted">' + fmtTime(r.created_at) + "</td>";
        var v = r[c.key];
        var cls = [c.cls || "", c.num ? "num" : "", c.color || ""].join(" ").trim();
        return "<td" + (cls ? ' class="' + cls + '"' : "") + ">" + esc(v) + "</td>";
      }).join("");
      return '<tr class="clickable" tabindex="0" data-id="' + esc(r.id) + '">' + cells + "</tr>";
    }).join("");
  }

  function arrow(key) {
    if (sort.key !== key) return "";
    return '<span class="arrow">' + (sort.dir === 1 ? "↑" : "↓") + "</span>";
  }

  function renderList() {
    if (!reports.length) {
      listEl.innerHTML = allReports.length
        ? '<div class="state">No reports match the current filter.</div>'
        : '<div class="state">No reports found yet. Run a '
          + '<span class="mono">PytestOperator</span> task with '
          + '<span class="mono">ArchivingJUnitResultParser</span> to populate this view.</div>';
      return;
    }
    sortReports();
    var head = COLS.map(function (c) {
      var asc = sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none";
      return '<th class="sortable" data-key="' + c.key + '" aria-sort="' + asc + '">'
        + esc(c.label) + arrow(c.key) + "</th>";
    }).join("");
    listEl.innerHTML = '<div class="table-wrap"><table><thead><tr>' + head
      + "</tr></thead><tbody>" + renderRows() + "</tbody></table></div>";

    listEl.querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var k = th.getAttribute("data-key");
        if (sort.key === k) sort.dir *= -1; else { sort.key = k; sort.dir = 1; }
        renderList();
      });
    });
    listEl.querySelectorAll("tr.clickable").forEach(function (tr) {
      var open = function () { openDetail(tr.getAttribute("data-id")); };
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
    });
  }

  function skeleton() {
    var rows = "";
    for (var i = 0; i < 6; i++) {
      rows += '<tr><td colspan="12"><div class="skeleton" style="width:'
        + (60 + (i * 7) % 35) + '%"></div></td></tr>';
    }
    listEl.innerHTML = '<div class="table-wrap"><table><tbody>' + rows + "</tbody></table></div>";
  }

  function load() {
    skeleton();
    kpisEl.hidden = true;
    fetch(API + "reports")
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        allReports = d.reports || [];
        populateSuggestions();
        applyFilter();
      })
      .catch(function (e) {
        listEl.innerHTML = '<div class="state c-fail">Failed to load reports: ' + esc(e.message) + "</div>";
      });
  }

  // Filter the loaded reports client-side by case-insensitive substring (``in``)
  // on dag_id and run_id, so typing narrows the table instantly.
  function matchesIn(haystack, needle) {
    return !needle || String(haystack).toLowerCase().indexOf(needle.toLowerCase()) !== -1;
  }
  function applyFilter() {
    var dag = document.getElementById("f-dag").value.trim();
    var run = document.getElementById("f-run").value.trim();
    reports = allReports.filter(function (r) {
      return matchesIn(r.dag_id, dag) && matchesIn(r.run_id, run);
    });
    renderKpis();
    renderList();
  }
  // Suggestions: the distinct dag_ids / run_ids seen, surfaced via native
  // <datalist> so the input shows a matching dropdown as the user types.
  function populateSuggestions() {
    var dags = {}, runs = {};
    allReports.forEach(function (r) { dags[r.dag_id] = 1; runs[r.run_id] = 1; });
    function fill(id, keys) {
      document.getElementById(id).innerHTML = Object.keys(keys).sort().map(function (k) {
        return '<option value="' + esc(k) + '"></option>';
      }).join("");
    }
    fill("dags", dags);
    fill("runs", runs);
  }

  /* ---- detail --------------------------------------------------------- */
  var dlg = document.getElementById("detail");
  var dBody = document.getElementById("d-body");
  var dTitle = document.getElementById("d-title");
  var detail = null, filter = "all", lastFocus = null;

  function renderDetail() {
    var m = detail;
    var counts = { all: m.cases.length, passed: 0, failed: 0, error: 0, skipped: 0 };
    m.cases.forEach(function (c) { if (counts[c.outcome] != null) counts[c.outcome]++; });

    var kpis = [
      ["Passed", m.passed, "c-pass"], ["Failed", m.failed, "c-fail"],
      ["Errors", m.errors, "c-error"], ["Skipped", m.skipped, "c-skip"],
      ["Duration", fmtDur(m.duration), ""],
    ].map(function (k) {
      return '<div class="kpi"><div class="label">' + k[0] + '</div>'
        + '<div class="value ' + k[2] + '">' + esc(k[1]) + "</div></div>";
    }).join("");

    var pills = ["all", "failed", "error", "skipped", "passed"].map(function (k) {
      return '<button class="pill" type="button" data-f="' + k + '" aria-pressed="'
        + (filter === k) + '">' + k + " (" + counts[k] + ")</button>";
    }).join("");

    var rows = m.cases.filter(function (c) { return filter === "all" || c.outcome === filter; });
    var body = rows.length ? rows.map(function (c, i) {
      var kind = { passed: "pass", failed: "fail", error: "error", skipped: "skip" }[c.outcome] || "skip";
      var output = (c.message && c.message.trim()) ? c.message : "No output captured.";
      return '<tr class="case clickable" tabindex="0" role="button" aria-expanded="false" data-exp="' + i + '">'
        + "<td>" + badge(kind, c.outcome) + "</td>"
        + '<td><span class="case-node mono">' + esc(c.node_id) + "</span></td>"
        + '<td class="num right">' + fmtDur(c.time) + "</td>"
        + '<td class="right"><span class="chev">' + CHEV + "</span></td></tr>"
        + '<tr class="case-exp" data-row="' + i + '" hidden><td colspan="4">'
        + '<pre class="tb mono">' + esc(output) + "</pre></td></tr>";
    }).join("") : '<tr><td colspan="4"><div class="state">No matching cases.</div></td></tr>';

    dBody.innerHTML = '<div class="kpis">' + kpis + "</div>"
      + '<div class="pills">' + pills + "</div>"
      + '<div class="card table-wrap"><table><thead><tr>'
      + '<th>Outcome</th><th>Test</th><th class="right">Time</th><th></th>'
      + "</tr></thead><tbody>" + body + "</tbody></table></div>";

    dBody.querySelectorAll(".pill").forEach(function (p) {
      p.addEventListener("click", function () { filter = p.getAttribute("data-f"); renderDetail(); });
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
    filter = "all";
    lastFocus = document.activeElement;
    dBody.innerHTML = '<div class="state"><div class="skeleton" style="width:40%;margin:0 auto"></div></div>';
    dTitle.textContent = "Loading report…";
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    fetch(API + "reports/" + encodeURIComponent(id))
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        detail = d; detail.cases = d.cases || [];
        dTitle.textContent = d.dag_id + " · " + d.task_id + " · try " + d.try_number;
        renderDetail();
      })
      .catch(function (e) {
        dBody.innerHTML = '<div class="state c-fail">Failed to load report: ' + esc(e.message) + "</div>";
      });
  }

  function closeDetail() {
    if (dlg.open) dlg.close(); else dlg.removeAttribute("open");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  document.getElementById("d-close").addEventListener("click", closeDetail);
  dlg.addEventListener("cancel", function () { if (lastFocus && lastFocus.focus) lastFocus.focus(); });

  /* ---- wire ----------------------------------------------------------- */
  document.getElementById("refresh").addEventListener("click", load);
  ["f-dag", "f-run"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", applyFilter);
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
