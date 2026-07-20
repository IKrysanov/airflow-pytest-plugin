# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Allure archives only ever read regular files, and never follow a link** — results are
  written on the worker by arbitrary pytest code, so a test could drop
  `allure-results/x-result.json -> /opt/airflow/airflow.cfg` and have the reader package it up
  for anyone allowed to download the run, or mail it as an attachment. Entries are now opened
  with `O_NOFOLLOW` and must be regular files, which closes three failure modes at once:
  symlink escape, swapping an entry for a link *after* it was checked (there is no window
  left), and a **named pipe, whose `open()` blocks forever** and would pin a server thread per
  download. Skipped entries are logged. Applies to the download and the email attachment alike.
- **A member larger than ~2 GiB no longer breaks the download mid-stream** — the size is
  unknown when its header goes out, so `zipfile` assumed "no ZIP64" and then raised past the
  limit, after bytes were already on the wire. Entries are written ZIP64-ready.
- **Allure downloads are streamed, not buffered in memory** — the endpoint built the whole zip
  in RAM per request, so a few concurrent downloads of a large results tree could exhaust the
  Airflow api-server the plugin runs inside. Measured on a 286 MB results dir: three parallel
  downloads peaked at **1237 MB** before, **56 MB** after. The archive is now buffered to a temp
  file and yielded in chunks (cleaned up even if the client disconnects mid-download).

### Added
- **Dashboard settings** — a ⚙ button in the header opens a panel picker for the main board:
  *Recent runs*, *Reliability* and *Flaky tests* each get a switch. A panel switched off is not
  rendered at all (not merely collapsed), its row closes up so no gap is left, and the choice is
  remembered in the browser — a reload will not bring a dismissed panel back. Everything is on by
  default, the run list below is never affected, and a corrupt stored value falls back to all-on
  rather than a blank board. Switches are real checkboxes (keyboard- and screen-reader-operable)
  and each spells its state out in words next to the track. **Off costs nothing:** the panel's
  DOM is released rather than merely hidden, so it is not rebuilt on every filter change — on a
  3200-run board that takes the page from ~8700 nodes to ~1500. A change made in another tab is
  picked up here too, so two open dashboards don't disagree about which panels exist.

## [0.6.1] - 2026-07-20

### Added
- **Coverage card in a run** — the run detail shows overall line coverage next to Duration
  (payload gains `coverage`, 0–1 or `null`; omitted when a run carries none). Switch it on with
  `ArchivingResultParser(coverage=True)`, which is self-contained — the operator needs no
  `coverage=True` of its own, and setting both is harmless. Coverage is read at archive time and
  baked into `meta.json`, so it **survives a failed run** (the operator raises before pushing its
  XCom, but the parser has already run) and costs the api-server no metadata-DB round-trip. Use
  `coverage_source="src"` when the project already narrows coverage — pytest-cov unions scopes, so
  a bare `--cov` would widen the number. Runs archived without the flag still fall back to reading
  the operator's XCom (successful runs only), baking it in on first view.
- **ⓘ notes on the KPI cards** — *Unique tests*, *Failures*, *Slowdowns* and *Coverage* each
  explain how they are computed (the 1000-run scan cap, "latest run of each dag·task", the
  1.3×/0.5 s slowdown rule, where coverage comes from and which bar applies), reusing the same
  popup as the chart and radar. Keyboard-reachable, localised, and they don't trigger the card's
  own drill-down.
- **Coverage target** — `AIRFLOW_PYTEST_SUCCESS_COVERAGE` (env/cfg, 0–1, default `0.85`) sets the
  bar: at or above it the card is green (*meets target 85%*), below it red. A suite can pin its
  own bar with `ArchivingResultParser(coverage_threshold=0.5)`, which **outranks** the env var —
  one global setting can't say a core library belongs at 95% while a legacy suite is fine at 50%.
  Out-of-range values are rejected with a warning rather than clamped (`90` meaning `0.9` falls
  back to the default instead of painting every run red). **Presentational only:** a shortfall
  never fails a run — enforcing coverage stays the operator's `cov_fail_under` gate. The verdict
  is spelled out in words beside the number, so it doesn't depend on seeing the tint.

### Security
- **Auth fails closed inside Airflow** — if Airflow is installed but its auth API can't be
  imported (e.g. after an upgrade moved it), the reader now denies every report and logs the
  reason, instead of falling back to allow-all as it did for the standalone dev server. Without
  Airflow at all, standalone stays open as before. `GET /api/health` gained a third `auth` value,
  `denied`, for that state — reporting it as `open` would tell an operator the opposite of what
  is happening.

### Fixed
- **The viewer follows Airflow's language** — the parent's `<html lang>` was read before the
  language i18next actually stores, so a served `index.html` with a hardcoded `lang="en"` pinned
  the plugin to English on a Russian stand. The stored choice now wins, and a late write during
  Airflow's boot is picked up instead of being missed.
- **KPI titles shrink instead of wrapping** — a long localised title ("УСПЕШНЫХ ПРОГОНОВ") used
  to wrap, stranding the "all" chip beside a two-line block so it read as unrelated content. The
  title now stays on one line and scales down to fit (growing back on resize), and the card grid's
  minimum widened to 190px so it never has to shrink far enough to clip. No wrap and no ellipsis
  from 320px to 1440px.
- **A closed run stays closed** — opening a run via the task-log tracking link
  (`?dag=…&run=…&task=…`) then dismissing it left those params in the URL, so the next refresh
  (the ⟳ button or a browser reload) reopened it. Closing now clears every deep-link param.
- **Donut % sits balanced with its caption** — the percentage is lifted a touch above the ring
  midline so the number and the "of N" caption below it straddle the centre symmetrically.

### Changed
- **Coverage reads don't hammer the metadata DB** — a settled run confirmed to carry no XCom
  coverage is remembered per process, so its detail stops re-querying Airflow's shared metadata
  DB on every open. Fresh runs keep being probed, so late-arriving coverage is never missed.

## [0.6.0] - 2026-07-05

### Added
- **Email alerts (opt-in, producer-side)** — styled HTML summaries (green pass / amber flaky /
  red fail, inline-CSS for mail clients, everything escaped) with the failed / flaky tests and a
  link back to the run. Per-task switches: `ArchivingResultParser(email=True)` mails every run,
  `email_only_fail=True` mails only fail / flaky (wins when both set); default sends nothing.
  Recipients from `AIRFLOW_PYTEST_ALERTS_EMAIL_TO` (validated, case-insensitively deduped, capped
  at 50); transport = Airflow's SMTP, or the standalone `AIRFLOW_PYTEST_SMTP_*` client (wins when
  its host is set). Raw Allure results ride along as `allure-results.zip` (skipped over 10 MB).
  Best-effort: a mail / config failure never fails the task.
- **Email a run from the UI** — an ✉ button (shown only with a transport) sends the run's summary
  via `POST /api/reports/{id}/email`: RBAC-gated (DAG read), recipients validated client- and
  server-side, capped at 10, subject header-sanitized, failure reason surfaced.
- **Per-run send log (✉ bench)** — every attempt lands in `meta.json` (`alerts`, sanitized, newest
  50; new optional `ReportSource.record_alert`). The toolbar bench shows green = delivered /
  red = failed counts, refreshes in place after a manual send, and opens the per-send log.
- **Tracking URL in the task log** — after archiving, the parser logs a short readable deep link
  that opens the run inside the Airflow UI (`…/plugin/pytest-reports?dag=…&run=…&task=…&try=…`).
  Needs `[api]`/`[webserver]` `base_url`; otherwise the log lists the run's coordinates.
- **Run-health trend** — a sparkline under the reliability radar (moving average of pass rate,
  no-errors, completeness) with a date axis, a current value and a ▲/▼ delta; scoped by the same
  filters as the radar, no extra request.
- **Case table sorts by Outcome** (ascending = broken first).

### Fixed
- **Donut polish** — slices are real SVG arcs (dash-drawn circles rendered faceted edges in
  Chrome), the % label is ink-centred for any digit count with "of N" clear below, and hovering
  from the hole no longer strobes (the lifted slice always covers the resting one).
- **No more `get_connection_from_secrets` DeprecationWarning per send** — emitted by Airflow's
  own `send_email` internals; the compat shim silences exactly that one warning.

### Security
- CodeQL findings on the release PR fixed. Report tokens decode with **strict** base64 (junk
  bytes — e.g. smuggled CRLF — now `400`, not silently decoded). **Log injection**: the email
  endpoint sanitizes every user-influenced value it logs (the raw token and the token-derived
  `dag_id`/`run_id`, which an unsigned token lets an attacker fill with newlines) to a single
  line. **ReDoS**: the email validator is now regex-free — plain character-set and length
  checks, provably linear on any input. Plus a removed no-effect statement. Three `unused-global-variable` findings on `common.py`'s shared error-response
  constants (`ERR_400/403/404`) resolved by declaring them in `__all__` — they are used by
  sibling route modules, so the finding was a stale intra-module false positive.

### Internal
- `flaky_core` extracted (web-free flaky scoring); Airflow's mail API wrapped in `compat.airflow`
  (`send_airflow_email`) so compat is again the only module importing Airflow; `run_tracking_url`
  lives in `plugin` with `config.get_base_url()` — the link is independent of the email flags.
- Audit hardening: atomic, concurrency-safe alert-log writes; memory-bounded Allure attachment
  (>50 MB raw never buffered); every `test_outcomes` consumer tolerates a row without `outcome`;
  SMTP config validated (header-safe sender, port range, half-credentials warning, recipient cap)
  with one normalization path for automatic and manual sends.

### Tests
- 336 unit / 75 UI. Alerting end to end (pure classification + HTML, orchestrator vs a temp
  source + spy mailer, SMTP transport + header-injection guard, endpoint RBAC / validation
  errors, send-log + attachments, config validation, a window-bounded load test) plus UI
  coverage for the trend, ✉ dialog + live bench, donut geometry (ink-centre pixel scan, hover
  stability, full-circle case), short deep-links (happy + stale), and a real e2e suite: 10 runs
  of a `@pytest.mark.flaky(reruns=3)` test settle green and stay invisible to the detector.

## [0.5.0] - 2026-07-02

### Added
- **Test×run heatmap** — a per-dag·task matrix (rows = tests, columns = recent runs, cells
  coloured by outcome) that surfaces flaky rows, regression blocks and build-breaking runs at
  a glance. Fixed name column + drag/scroll cell carousel; rows sort most-broken first; legend
  is a status focus filter. Opens from each group header and a run's toolbar; a cell opens that
  run and jumps to the test, a name opens its history. Backed by **`GET /api/heatmap`** (compact
  cell codes, RBAC-filtered, window 2–100, rows capped 300).
- **Reliability radar (pentagon)** — a 3rd main-board dashboard: the runs chart is now full width
  on top, and the radar shares the row below it 50/50 with the flaky panel. Scores the runs in view
  on five 0–100 axes (pass rate, no-errors, green-now, stability, completeness) with an overall score;
  its ⓘ popup explains each axis with its live value. Scopes with the top filters + group selection.
- **ⓘ "about this panel" popups** on the runs chart and the flaky panel (alongside the radar's),
  explaining what each shows and how it's read.
- **Merged test history** — opening a test from *Unique tests* now shows one timeline across every
  dag·task it ran in (each run tagged with its dag·task); `GET /api/test-history` merges when
  dag/task are omitted, stays scoped when given. The modal states the run count shown.

### Changed
- **Flaky UI reflects reality** — with no flaky tests the flaky panel disappears and the runs chart
  takes the full width; a group with flaky tests shows an amber ⚠ chip (click to focus the board on
  it); a run's *Flaky tests* button appears only when that dag·task has flaky ones.
- **"all" chip on the RUNS and PASSING RUNS KPIs** — they count every run in view and are not
  narrowed by a group selection (unlike Failures/Slowdowns), which the chip now makes explicit.
- **Radar pass rate == chart avg pass rate** — the radar's *Pass rate* uses the same per-run mean
  as the chart's *avg pass rate* (was a pooled ratio), and the chart's average now spans ALL runs in
  the chart (not just the visible window), so the two read identically.
- **UI polish** — modal dimming is one shared full-screen overlay (stacked popups no longer
  double-darken); chart tooltips sit just below-left of the cursor; **chart bars show an even 2px
  ring on hover instead of brightening** (no colour flicker/uneven outline when sweeping many bars);
  **the radar fills its card and scales proportionally** with the screen; **the flaky panel fills its
  card and scrolls to the bottom** (matched height with the radar) instead of stopping at a fixed
  cap; the heatmap is a crisp rounded grid with uniform spacing and a soft border-coloured line,
  adaptive run-number labels, and a uniform inset hover; run-list group columns fill the width with
  a continuous row separator.

### Fixed
- Failure-cluster status square keeps its size when a long test name wraps.
- Removed a `type: ignore` that mypy flagged as unused in some environments.

### Tests
- Added coverage for merged history (backend + UI), the flaky-absent/chip/button states, the
  reliability radar (+ pass-rate == chart avg, adaptivity), the "all" KPI chips, the panel ⓘ
  popups, the single modal dim, the tooltip placement, the bounded-scroll flaky panel, the
  chart-bar hover ring, and the cluster square; green (no-flaky) + evil (XSS-payload) UI fixtures.
- **Security regression guards** — an explicit XXE test (external-entity junit → blocked by
  defusedxml, no leak) and a stored-XSS UI test (a hostile test name / failure message renders as
  inert escaped text, never executes). Load- and security-smoked a 663-run demo: every API endpoint
  under ~0.06 s; metrics 404 without a token; traversal/malformed/zero-test inputs handled safely.

## [0.4.0] - 2026-06-29

### Added
- **Prometheus metrics** — `GET /api/metrics` exposes per-dag·task gauges from each
  dag·task's latest run (`airflow_pytest_latest_*{dag_id,task_id}`) plus globals
  (`airflow_pytest_up` / `runs` / `dagtasks` / `latest_failures` / `build_info`) in the
  Prometheus text format — all gauges (no `_total` suffix), values at full precision (no
  scientific-notation rounding), no new dependency. **Secure by default:**
  disabled unless `AIRFLOW_PYTEST_METRICS_TOKEN` is set, then requires
  `Authorization: Bearer <token>` (constant-time compare; label values escaped). The token
  is declared as a bearer security scheme, so Swagger's *Authorize* box sends it correctly.
  **Load-cheap:** one cached scan, summary-derived (no per-run reads), cardinality-capped
  at 2000 series. See the *Prometheus metrics* README section.
- **Slow tests & duration regressions** — a new *Slowdowns* KPI opens a panel
  listing tests whose **execution time got slower** (recent-half average duration vs
  the older half, over a configurable window) and the **slowest tests** by average
  duration. A test that speeds back up drops off the list. Inside a run, the case
  table now sorts by execution time (slowest first).
- **`GET /api/slow`** — duration regressions (`regressed`) and the slowest tests
  (`slowest`) across the last `window` runs of each dag·task, RBAC-filtered.
- **`AIRFLOW_PYTEST_SLOW_FACTOR`** (default `1.3`) and
  **`AIRFLOW_PYTEST_SLOW_MIN_DELTA`** (default `0.5` s) — tune how much slower, in
  ratio and absolute seconds, a test must get before it counts as a regression.
- **Per-test stats in the *Unique tests* catalogue** — each test now shows its total
  runs, average execution time and per-outcome counts (passed / failed / errors /
  skipped), aggregated by `GET /api/unique-tests?full=1` from the same scan (no extra
  cost).
- **Error clustering** — the *Failures* KPI now groups failed/errored cases into
  clusters by a normalized error signature (numbers / hex / UUIDs masked), biggest
  cluster first, so common root causes surface instead of a flat per-failure list; each
  cluster expands to its tests (clickable). The run detail gets an *Error clusters*
  button opening the same clusters scoped to that run. New `GET /api/failure-clusters`
  (filters + RBAC mirror `/api/failures`).
- **Runs-chart window context** — the runs chart now shows which runs are on screen
  (e.g. *#48–#76 / 76*, updating live as you scroll the carousel) next to the arrows, and,
  when the trend is on, the **average pass rate of the visible window** (e.g. *avg 92%*,
  tinted red when it dips below the success threshold) next to the toggle.

### Changed
- **Failures now reflect current state** — the *Failures* KPI and the failures/clusters
  endpoints count only each dag·task's **latest** run, so a fixed test drops off once its
  next run is green (the list shrinks as code improves) instead of listing every failure
  ever archived. Pass `latest=0` to `/api/failures` or `/api/failure-clusters` for the
  full history.
- **Chart legend is now a status filter (focus, not hide)** — clicking a status in the
  legend (e.g. *passed*) shows **only** that status in the chart and the run list below
  (grouped or flat); click more statuses to add them, and a *Reset filter* button clears
  the selection back to all.
- **UI polish** — a *Clear filters* button next to the dag/task/run filters (shown only
  when a filter is set); error-cluster expansions use the run-list's left-accent style
  (no oversized indent); the in-run *Error clusters* modal opens inset like the other
  run popups instead of spanning the run window; the pass-rate **success-threshold line**
  is now a muted, thin gridline (a `--thresh-soft` token) so it recedes behind the data
  instead of competing with it; its `%` label is a translucent glass chip (a
  `--surface-glass` token + backdrop blur) that never fully hides a trend dot behind it
  while the text stays readable; the runs-chart header is now laid out in two fixed rows
  (title + legend on top; *Pass-rate trend* toggle left and the carousel arrows right
  below) so the controls stay put instead of reflowing as the window resizes.
- **Selecting a dag·task group now scopes the whole dashboard** — ticking a group (or
  runs) already focused the runs chart; now the *Flaky tests* panel, the **Failures** and
  **Slowdowns** KPIs (and their modals) all narrow to the selected dag·task(s) too, with a
  *selected groups* chip. One pick filters the entire board — chart, flaky, failures,
  slowdowns — at once (client-side, so it works for any set of groups).

### Fixed
- **Group checkbox now clears with *show all*** — selecting a dag·task group focuses the
  chart on its runs; clicking *show all* on the chart cleared the selection and unticked
  the individual run checkboxes but left the **group header checkbox** still ticked. It
  now resets (checked + indeterminate) along with the rest.
- **`/api/flaky` now has a read budget** — a new `_FLAKY_SCAN_CAP` (2000 run-meta files,
  mirroring `/api/slow`) bounds the work so many dag·tasks × a large window can't make one
  request walk most of the archive; `capped` flags it. Found via load testing (150 dag·tasks
  × window 200 went from ~5.0s to ~2.9s).
- **Run-detail donut: tiny slices no longer overlap** — a very small fail/error share
  rendered as a rounded dot positioned by its raw proportion, so two small slices could
  slide on top of each other. Slices are now laid out by their actual footprint within the
  gapped arc, keeping a full gap between every segment.

### Tests
- **Playwright UI regression suite** (`tests/ui`, opt-in marker `ui`) — boots the standalone
  dev server against a seeded report tree and drives a real browser to guard the dashboard
  (KPIs, donut non-overlap, group-scoping, modals, legend filter, trend/threshold, mobile
  no-horizontal-scroll). Run with `pip install -e '.[web,ui-test]' && playwright install
  chromium && pytest -m ui`; a dedicated `ui` CI job runs it. The default `pytest` stays
  unit-only and browser-free. Tests run on both a small and a **large (3200-run)** seed so
  layout is verified at scale.
- **Embedded-in-Airflow UI tests** (`tests/ui`, marker `ui_airflow`) — boot a real Airflow 3
  api-server with the plugin mounted and drive Playwright against the embedded app at
  `/pytest-reports/`, proving it loads/serves under Airflow's own runtime + auth manager. A
  dedicated `ui-airflow` CI job installs Airflow (official constraints) + the browser and runs
  `pytest -m ui_airflow`; it auto-skips when Airflow isn't installed.

## [0.3.2] - 2026-06-28

### Added
- **Group the run list by dag·task (on by default)** — a checkbox over the list
  (like the run detail's *group by module*) folds the runs into collapsible dag·task
  groups under a **sortable** dag / task / runs / pass-% / avg-time / status / when
  header that **reorders the groups** (and, for run columns, the runs too); uncheck
  it for the flat, paginated list. Each group shows its run count, pass-rate, average
  duration and last status, and expands to its own **sortable** full column header +
  runs (first 100) — and that header sorts **only its own group**, independently. A
  group's checkbox selects all its runs (even while collapsed; *select all* ticks
  every group), which **focuses the history chart on that group**.
- **`GET /api/groups`** — runs aggregated by dag·task (count, pass-rate, average
  duration, newest run's status/time), RBAC-filtered with optional `dag_id` /
  `task_id`. Lets grouped views and dashboards read group stats without fetching
  every run (the basis for scaling past in-browser grouping).

### Changed
- **Swagger / OpenAPI tidied** — every JSON endpoint now documents a real example
  response (instead of a bare `string`) and the status codes it can return (`400`
  malformed token, `403` RBAC, `404` not found), so `GET /api/docs` is accurate.
- The top dag/task/run filters are **debounced** (one re-render after typing settles,
  not per keystroke) and reset to page 1 / newest as intended.

### Fixed
- **Responsive board on narrow screens** — the recent-runs chart and flaky panel no
  longer collapse to a sliver when stacked; each sizes to its content.
- The grouped **DAG** column header now sits over the dag name (was shifted left by
  the expander chevron).

## [0.3.1] - 2026-06-27

### Added
- **Retention / auto-cleanup** — opt-in deletion of old runs by **age**
  (`AIRFLOW_PYTEST_RETENTION_MAX_AGE_DAYS`), **count** per dag·task
  (`…_MAX_RUNS`), or total **size** (`…_MAX_TOTAL_MB`); env or `[pytest_reports]`
  cfg. Schedule the exported `prune_reports` callable from a maintenance DAG (it
  also takes a `RetentionPolicy` and a `dry_run` flag). The newest run of each
  dag·task is always kept, and cleanup is scheduler-driven — the plugin never
  deletes on its own.
- **Flaky, deeper** — `/api/flaky` now reports a **flakiness score** (flip rate
  0–1, shown with an explanatory tooltip), a **trend** (`up`/`down`/`flat`, recent
  vs older half) and a **quarantine** flag (score ≥
  `AIRFLOW_PYTEST_FLAKY_QUARANTINE_SCORE`, default `0.5`). A **minimum-score floor**
  (`AIRFLOW_PYTEST_FLAKY_MIN_SCORE`, default `0.1`) drops near-steady tests — e.g. a
  lone failure in a long passing history — out of the list. The flaky modal gains an
  analysis-window selector and a quarantined-only filter; the home flaky panel shows
  score + trend and gains its own **search box** and **quarantined-only** toggle. The
  default window is configurable (`AIRFLOW_PYTEST_FLAKY_WINDOW`, default `30`).

- **Chart run-filter** — ticking runs in the list now filters the history chart to
  just those bars (empty selection = all), so you can read the trend of a chosen
  subset; a "show all" affordance on the chart clears it.
- **Pass-rate trend line** — a checkbox over the chart overlays a cyan line through
  each bar's pass ratio (top of the green band), with per-run dots (exact pass-% on
  hover) and an amber dashed gridline at the success threshold; while it's on the
  bars recede and the hovered one lights up, so the quality trend and the bar
  against it read at a glance. Off by default; `/api/reports` now echoes
  `success_threshold` for the gridline.
- **Configurable success threshold** — a run now counts as successful (the *Passing
  runs* KPI and the PASS status) when its pass rate over *executed* tests is at or
  above `AIRFLOW_PYTEST_SUCCESS_THRESHOLD` (env or cfg, default `0.85`); skipped
  tests are excluded, and `1.0` keeps the old strict "zero failures" behaviour.

### Fixed
- Test-history modal no longer scrolls horizontally on a long test name (it wraps).

## [0.3.0] - 2026-06-25

Cross-run analytics: flaky detection, history, comparison, and a test catalogue.

### Added
- **Cross-run intelligence** — *Compare to previous* (`GET /api/compare`) diffs a run
  against the prior one (newly failed / fixed / still failing / added / removed);
  *Flaky tests* (`GET /api/flaky`) finds tests that both pass and fail over recent
  runs; expanding a case shows its *History* (`GET /api/test-history`). A **flaky
  panel** sits beside the home chart.
- **Per-run duration histogram** — test times in 10-second buckets, a scrollable
  carousel with a per-bucket hover count.
- **Unique tests** KPI (`GET /api/unique-tests`) counts distinct tests (not the
  per-run total summed) and opens a searchable, paginated catalogue.
- **Case search & group-by-module** in the run table, and an **API docs** link
  (Swagger UI) in the header.
- `GET /api/health` now reports readiness — `reports_root` (where the producer writes
  and the reader reads), whether it exists, the auth mode (`airflow`/`open`), and
  whether the hardened `defusedxml` parser is active — with no directory scan.
  `GET /api/version` exposes the build version.
- **`AIRFLOW_PYTEST_PLUGIN_ENABLE`** env var (default `True`) — a kill switch that
  stops the reader registering its UI + API with Airflow; the producer is unaffected.
- **Directory-scan cache** (`AIRFLOW_PYTEST_SCAN_CACHE_TTL`, default `2.0`s) — the
  several summary-driven endpoints on one page load now share a single tree walk
  instead of rescanning each (single-flight, invalidated on delete). At 5 000 runs the
  home page's data calls drop from ~1.2 s to ~0.1 s; deletes still update instantly.
- Each run's `meta.json` stores a compact per-test outcomes map
  (`ReportSource.test_outcomes`), with a `junit.xml` fallback for older archives.

### Changed
- Run-detail polish: the donut shows the test count with rounded, lift-on-hover arcs;
  the home chart and flaky panel split the row; modals stay clear of the window edges,
  scroll within, and nested popups sit inset inside a run.
- The header's *API* button is now a **links menu** (GitHub repo + API docs). The JSON
  routes are split into per-tag modules and the **Swagger UI is grouped into sections**
  (monitoring / reports / failures / compare / flaky) with a summary on every endpoint;
  the viewer and its icons are kept out of the OpenAPI schema.

### Fixed
- `/api/openapi.json` / Swagger UI no longer error (response-type annotations now
  resolve under `from __future__ import annotations`); chart hover tooltips render in
  front of run modals; the flaky outcome strip is capped at the 10 most recent runs;
  `/api/unique-tests` bounds its scan so the KPI can't trigger an unbounded read; the
  donut re-lights when the status filter changes (it stuck on the status a run was
  opened with — e.g. from the *Failures* list).

## [0.2.1] - 2026-06-23

Viewer polish and a failed-test overview.

### Added
- **Failed-tests view** — the *Failures* KPI lists every failed/errored case across
  the visible runs (`GET /api/failures`), paginated 100/page; a row opens that run.
- **`task_id` filter** in the top search, and the **run number** (`#N`) in the
  report header (matching the chart bar and list **ID**).

### Changed
- Allure download moved into the report header; filter suggestions drop in a tidy
  in-app list (replacing the native datalist popup); the case table's outcome column
  is frozen with a divider; modal dimming now covers the whole Airflow window (nav
  included) and modals close on backdrop click / Esc.

### Fixed
- A chart-bar click opens its run again (a drag no longer eats it); filters reset to
  page 1 from any page; following a DAG/run/task link clears the full-screen dim.

## [0.2.0] - 2026-06-22

A much richer Airflow 3 viewer.

### Added
- **History chart** of per-run stacked bars — a smooth drag/swipe/arrow carousel past
  30 runs, tied to a sortable **ID** column — and a **success donut** with
  click-to-filter.
- **Captured output for every test** (passed included), expandable per row.
- **Delete reports** (single or **bulk**, with confirmation), RBAC-checked and
  path-bounded.
- **Airflow RBAC** — reads gate the list/detail (`403`), deletes need DAG-trigger
  permission; fail-closed.
- **Back-links** to the DAG/run/task, shareable `?report=` deep-links, **EN/RU**
  localisation, and list pagination (100/page).
- **Allure / TestOps export** (opt-in `ArchivingResultParser(allure=True)`): archives
  raw Allure results next to the report, served at `GET /api/reports/{id}/allure.zip`.

### Changed
- **Renamed** `ArchivingJUnitResultParser` → `ArchivingResultParser` — update your
  `parser=` import.
- **Looks like Airflow** — Inter font, brand colours, and navy-dark / white-light
  themes sampled from Airflow's UI, followed live from the parent.

### Security
- Report tokens are sanitised and every resolved path is bounded to the report root.

### Tests
- ~97% coverage; inline JS is syntax-checked; integration tests drive a real Airflow
  `SimpleAuthManager`.

## [0.1.0] - 2026-06-21

Initial release: archive `airflow-pytest-operator` JUnit results and browse them in
the Airflow 3 web UI.

### Added
- `ArchivingJUnitResultParser` — a drop-in `parser=` for `PytestOperator` that
  archives each run's JUnit XML + a self-describing `meta.json` under
  `{root}/{dag}/{run}/{task}/t{try}[/m{map}]/` (no `cleanup="never"` required).
- `ReportSource` / `FileSystemReportSource` (scan `meta.json`, parse `junit.xml` on
  demand), `ReportLayout`, and the view models.
- FastAPI `create_app` serving the single-page viewer + JSON API, registered as an
  `AirflowPlugin` (`fastapi_apps` + `external_views`); plus a standalone dev server.
- CI/CD: lint, type-check, unit (py3.10–3.13) + Airflow 3 integration matrices,
  CodeQL, OpenSSF Scorecard, DCO, and Trusted-Publishing release workflows.

[Unreleased]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/IKrysanov/airflow-pytest-plugin/releases/tag/v0.1.0
