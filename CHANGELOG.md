# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/IKrysanov/airflow-pytest-plugin/releases/tag/v0.1.0
