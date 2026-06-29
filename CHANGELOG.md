# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Test×run heatmap** — a per-dag·task matrix (rows = tests, columns = recent runs
  oldest→newest, each cell coloured by that test's outcome; `did not run` shown as an
  empty dashed cell) that surfaces flaky rows (alternating colours), regression blocks
  (failures filling in on the right) and a build-breaking run (a red/error column) at a
  glance. Rows sort most-broken first (fail+error count, then flakiness). A **fixed
  test-name column + a drag/scroll cell carousel** (like the runs chart) keeps names
  readable as the matrix scrolls; hovering a cell shows the plugin's standard tooltip
  (test · run · outcome). The legend is a **status focus filter** (like the runs-chart
  legend) — click a status to dim the rest. Opens from a **Heatmap** button on each
  dag·task group header in the run list and from a run's toolbar; clicking a **cell opens
  that run and jumps to / expands that test**, a test name opens its history. A window
  selector mirrors the flaky/slow panels.
- **`GET /api/heatmap`** — the outcome matrix for one dag·task (`dag_id` + `task_id`
  required, `window` optional). Rows are compact single-char cell codes
  (`p`/`f`/`e`/`s`, `-` = didn't run) aligned to `runs`; RBAC-filtered, window clamped
  to 2–100, rows capped at 300 (`truncated` flags it). Load profile mirrors `/api/flaky`
  for one group (cached scan, bounded).

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

[Unreleased]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/IKrysanov/airflow-pytest-plugin/releases/tag/v0.1.0
