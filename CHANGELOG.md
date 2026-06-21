# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/IKrysanov/airflow-pytest-plugin/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/IKrysanov/airflow-pytest-plugin/releases/tag/v0.1.0
