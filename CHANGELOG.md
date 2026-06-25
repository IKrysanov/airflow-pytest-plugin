# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/IKrysanov/airflow-pytest-plugin/releases/tag/v0.1.0
