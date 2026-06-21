# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-...

A much richer Airflow 3 viewer: history chart, success donut, captured output for
every test, RBAC-gated deletion, EN/RU localisation, deep-links, and a look that
matches Airflow.

### Added
- **History chart** above the table — per-run stacked bars (pass/fail/error/skip)
  with a legend toggle, run numbers, and a carousel past 30 runs; click a bar to
  open that run.
- **Success donut** in the detail view: pass-rate in the centre, click a slice to
  filter the case table, hover for its share.
- **Captured output for every test** (passed included) — `system-out`/`-err` plus
  failure/error tracebacks and skip reasons, expandable per row.
- **Delete a report** from the UI (with confirmation): removes its files and now-
  empty `dag/run/task` dirs; refuses any path outside the report root.
- **Airflow RBAC**: reads filter the list and gate detail (`403`) to DAGs the user
  may read; deletion requires permission to trigger the DAG. Checks fail **closed**;
  authorizers are injectable; the standalone dev server is open.
- **Back-links** to the run's DAG / DAG run / task instance in Airflow (driven via
  the History API, as the plugin iframe is sandboxed).
- **Shareable deep-links** that keep Airflow's chrome: `?report=<token>` rides the
  Airflow parent URL, so a copied link reopens the report inside Airflow.
- **EN/RU localisation** following Airflow's selected language, with locale-aware
  dates/numbers.
- **List pagination** at 100 rows/page.

### Changed
- **Looks like Airflow**: Inter font, brand blue `#017CEE`, and `STATE_COLORS`;
  a navy dark theme and white/bordered light theme sampled from Airflow's own UI,
  with the page background read live from the parent when embedded (no white
  flash). Flat surfaces, an aligned header, a gentle `rgba(0,0,0,.5)` modal
  backdrop, and a nav icon in Airflow's `fg.muted` grey.

### Security
- Report tokens are untrusted: path components are sanitised (no `.`/`..`
  escape) and every resolved path is bounded to the report root before any read
  or delete, so a crafted token can't reach files outside it.

### Tests
- ~97% coverage (delete/RBAC + path-traversal guards, captured-output extraction,
  config/compat fallbacks); inline JS is syntax-checked with `node --check`;
  integration tests drive a real Airflow `SimpleAuthManager` (admin vs viewer)
  and verify the auth import paths and fail-closed behaviour.

## [0.1.0] - 2026-06-21

Initial release: archive `airflow-pytest-operator` JUnit results and browse them
in the Airflow 3 web UI.

### Added
- `ArchivingJUnitResultParser` — a drop-in `parser=` for `PytestOperator` that
  subclasses the operator's `JUnitResultParser` and archives each run's JUnit
  XML plus a self-describing `meta.json` sidecar under
  `{root}/{dag_id}/{run_id}/{task_id}/t{try}[/m{map}]/`. Airflow coordinates come
  from `get_current_context()` (available because the parser runs inside the
  task's `execute()`); off-task calls fall back to a synthetic ref. Because the
  report directory is parser-supplied, the operator's runner never deletes it —
  no `cleanup="never"` required.
- `ReportSource` interface and `FileSystemReportSource`, which indexes reports by
  scanning `meta.json` sidecars (fast listing, no XML parse) and parses
  `junit.xml` on demand for per-case detail using the operator's parser.
- `ReportLayout` — the single `ReportRef → directory` mapping shared by the
  producer and reader, with filesystem-safe path sanitisation (true identity
  preserved in `meta.json` and a reversible API token).
- FastAPI app (`create_app`) serving a dependency-free single-page viewer plus a
  JSON API (`/api/reports`, `/api/reports/{id}`, `/api/health`). Mountable under
  any prefix; the page derives its API base at runtime.
- `PytestReportsPlugin` — an `AirflowPlugin` registering the app via
  `fastapi_apps` and a nav link via `external_views`, discovered through the
  `airflow.plugins` entry point. Registration is best-effort: missing FastAPI
  leaves the producer parser unaffected.
- View models (`ReportRef`, `ReportSummary`, `ReportDetail`, `CaseView`) and
  config resolution (`get_reports_root`: `AIRFLOW_PYTEST_REPORTS_ROOT` env →
  `[pytest_reports] reports_root` cfg → `/opt/airflow/pytest-reports`).
- Standalone dev server: `python -m airflow_pytest_plugin.web`.
- CI/CD: lint + type-check, a unit matrix (py3.10–3.13, no Airflow), an Airflow 3
  integration matrix, CodeQL, OpenSSF Scorecard, DCO, and Trusted-Publishing
  release/TestPyPI workflows with SHA-pinned actions.

[Unreleased]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/IKrysanov/airflow-pytest-plugin/releases/tag/v0.1.0
