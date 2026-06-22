# airflow-pytest-plugin

View [`airflow-pytest-operator`](https://github.com/IKrysanov/airflow-pytest-operator)
results in the **Airflow 3** web UI.

**Package**

| Badge | What it tells you |
|:------|:------------------|
| [![PyPI version](https://img.shields.io/pypi/v/airflow-pytest-plugin.svg)](https://pypi.org/project/airflow-pytest-plugin/) | Latest release on PyPI — `pip install airflow-pytest-plugin` |
| [![Python versions](https://img.shields.io/pypi/pyversions/airflow-pytest-plugin.svg)](https://pypi.org/project/airflow-pytest-plugin/) | Supported Python versions (3.10+) |
| [![Airflow](https://img.shields.io/badge/Airflow-3.x-017CEE.svg?logo=apacheairflow)](https://airflow.apache.org/) | Targets Airflow 3.x (FastAPI plugin UI) |
| [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) | Distributed under the Apache-2.0 licence |

**Quality &amp; build**

| Badge | What it tells you |
|:------|:------------------|
| [![CI](https://github.com/IKrysanov/airflow-pytest-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/IKrysanov/airflow-pytest-plugin/actions/workflows/ci.yml) | Build & test suite (lint, types, unit, integration) on `main` |
| [![codecov](https://codecov.io/gh/IKrysanov/airflow-pytest-plugin/branch/main/graph/badge.svg)](https://codecov.io/gh/IKrysanov/airflow-pytest-plugin) | Test coverage of the package |
| [![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/) | Fully type-checked with mypy `--strict` |
| [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) | Linted & formatted with Ruff |
| [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/IKrysanov/airflow-pytest-plugin/badge)](https://scorecard.dev/viewer/?uri=github.com/IKrysanov/airflow-pytest-plugin) | OpenSSF supply-chain security score |

The operator runs a `pytest` suite as an Airflow task and parses the JUnit
report into a structured result. This plugin archives each of those reports —
keyed by `dag_id / run_id / task_id / try` — and serves a small web UI to browse
them: pass/fail counts per run, durations, and the per-test breakdown (with
failure messages) for any run.

It has two halves that share one on-disk layout:

| Side | Where it runs | What it is |
| --- | --- | --- |
| **Producer** | the worker | `ArchivingResultParser`, a drop-in `parser=` for `PytestOperator` |
| **Reader** | the API server | a FastAPI app + single-page viewer, registered as an Airflow plugin |

## Contents

- [Screenshots](#screenshots)
- [Install](#install)
- [Quickstart](#quickstart)
- [Do I need `cleanup="never"`?](#do-i-need-cleanupnever)
- [How it works](#how-it-works)
- [HTTP API](#http-api)
- [Access control (RBAC)](#access-control-rbac)
- [Configuration](#configuration)
- [Architecture (SOLID)](#architecture-solid)
- [Development](#development)
- [License](#license)

## Screenshots

**Overview** — the run list with the historical chart (per-status legend
toggles, run numbers, and a carousel beyond 30 runs), KPI cards, and Airflow-
matched colours and font:

![Pytest Reports — overview](https://raw.githubusercontent.com/IKrysanov/airflow-pytest-plugin/main/docs/screenshots/overview.png)

**A single run** — a clickable success donut (pass-rate in the centre; click a
slice to filter by status), the counts, and every test's captured output on
expand:

![Pytest Reports — a single run](https://raw.githubusercontent.com/IKrysanov/airflow-pytest-plugin/main/docs/screenshots/detail.png)

---

## Install

```bash
pip install airflow-pytest-plugin          # producer side (workers)
pip install 'airflow-pytest-plugin[web]'   # reader side (API server)
```

On Airflow 3 the API server already provides FastAPI, so the bare install is
enough there too; the `[web]` extra only adds the standalone dev server.

## Quickstart

**1. Point your operator at the archiving parser** — the only DAG change:

```python
from airflow_pytest_operator import PytestOperator
from airflow_pytest_plugin import ArchivingResultParser

PytestOperator(
    task_id="run_tests",
    test_path="tests/",
    parser=ArchivingResultParser(),   # was JUnitResultParser()
)
```

**2. Tell both sides where reports live** (one place, read by producer and
reader alike):

```bash
export AIRFLOW_PYTEST_REPORTS_ROOT=/opt/airflow/pytest-reports
```

or in `airflow.cfg`:

```ini
[pytest_reports]
reports_root = /opt/airflow/pytest-reports
```

In a distributed deployment this should be a **shared volume** that both the
workers (writing) and the API server (reading) can see.

**3. Open the UI.** The plugin registers itself via the `airflow.plugins` entry
point — no config. The app mounts on the API server at `/pytest-reports`, with a
**Pytest Reports** entry under *Browse* in the nav.

### Preview locally, without Airflow

```bash
python -m airflow_pytest_plugin.web --root ./pytest-reports --port 8000
# open http://127.0.0.1:8000/
```

---

## Do I need `cleanup="never"`?

**No.** In the operator, the *parser* owns the report location, and a
**parser-supplied directory is never deleted by the runner under any cleanup
policy**. `ArchivingResultParser` supplies its own directory, so reports
always survive regardless of the runner's `cleanup` setting. `cleanup="never"`
only matters when you let the runner use throwaway temp dirs — which is exactly
the fragile path (random names, no `dag/run/task` association, not visible to
other workers) this plugin replaces.

## How it works

```
worker                              shared volume                 API server
──────                              ─────────────                 ──────────
PytestOperator                      {root}/{dag}/{run}/           FastAPI app
  └─ ArchivingResultParser ──▶   {task}/t{try}/        ◀──── FileSystemReportSource
       report_request() → path          ├─ junit.xml              └─ lists meta.json,
       parse()          → meta.json     └─ meta.json                 parses junit.xml
```

* `report_request()` reads the live Airflow context (`get_current_context()`,
  available because the parser runs inside the task's `execute()`), computes the
  archive directory, and hands it to the operator's JUnit parser.
* `parse()` reuses the operator's JUnit parsing, then drops a `meta.json`
  sidecar carrying the Airflow coordinates + the summary. That sidecar makes
  each report **self-describing**, so the reader needs no database access.
* The reader lists by scanning `meta.json` files (fast) and parses `junit.xml`
  on demand for the per-case detail.

The directory is a human-friendly container; the authoritative identity always
lives in `meta.json` (and the API's opaque, reversible report token), so awkward
`run_id` characters like `:` are sanitised in the path without losing anything.

## HTTP API

The app is mountable under any prefix; the viewer derives its API base at
runtime. Endpoints (relative to the mount):

| Method & path | Returns |
| --- | --- |
| `GET /` | the single-page viewer (HTML) |
| `GET /api/reports?dag_id=&run_id=` | summaries, newest first |
| `GET /api/reports/{report_id}` | one report with per-case rows |
| `DELETE /api/reports/{report_id}` | delete a report (RBAC-gated) |
| `GET /api/reports/{report_id}/allure.zip` | raw Allure results as a zip (if any) |
| `GET /api/health` | `{"status": "ok"}` |
| `GET /api/docs` | OpenAPI docs |

The reads (`GET`) and the delete are gated by Airflow RBAC — see below.

## Access control (RBAC)

Access is enforced the way Airflow 3 enforces it: every check goes through
Airflow's **auth manager** (`is_authorized_dag(...)`) — the same call Airflow's
own DAG-run endpoints make — keyed by the report's `dag_id` and the
authenticated user. Two permissions are checked:

| Action | Airflow 3.x check | Airflow 2.x (FAB) equivalent |
| --- | --- | --- |
| **See / open a report** | `is_authorized_dag(method="GET", access_entity=RUN)` | `can_read` on the DAG |
| **Delete a report** | `is_authorized_dag(method="POST", access_entity=RUN)` (may trigger the DAG) | trigger / `can_create` on the DAG |

The report list is filtered to the DAGs you may read, opening a report you can't
read returns `403`, and deleting one requires permission to **trigger** its DAG.
Every check **fails closed**: if the auth manager can't be consulted, access is
denied.

**Airflow 2 → 3 mapping.** Airflow 2's FAB used `(action, resource)` pairs —
`can_read` / `can_edit` / `can_delete` / `can_create` on a resource such as
`DAG:<id>`. Airflow 3 replaced these with the auth manager's `method`: `GET` ↔
read, `POST` ↔ create, `PUT` ↔ edit, `DELETE` ↔ delete, `MENU` ↔ menu access.
This plugin maps **read → `GET`** and **delete → `POST`** (trigger), so it
inherits your existing per-DAG roles with no extra configuration.

**Plugin visibility.** The nav entry is an Airflow `external_views` item, which
has no per-permission gate, so the menu link is visible to every signed-in user;
access is enforced on the **content** (a user who may read no DAG sees an empty
list and `403` on direct links). The standalone dev server (no Airflow auth)
allows everything.

## Allure / TestOps export

Opt in per task and install [`allure-pytest`](https://pypi.org/project/allure-pytest/)
on the worker:

```python
parser=ArchivingResultParser(allure=True)
```

The parser then adds `--alluredir` (pytest errors with *unrecognized arguments*
if `allure-pytest` is missing), so the **raw Allure results** are archived next to
the report, with an `executor.json` linking the launch back to the Airflow run.
Download them from a report's detail view, or `GET
/api/reports/{id}/allure.zip` — then upload to [Allure TestOps](https://qameta.io/)
(`allurectl upload …`). The JUnit viewer is unaffected; both artifacts coexist.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `AIRFLOW_PYTEST_REPORTS_ROOT` (env) | — | report root (highest precedence) |
| `[pytest_reports] reports_root` (cfg) | — | report root |
| built-in default | `/opt/airflow/pytest-reports` | fallback |

## Architecture (SOLID)

Mirrors the operator's layering — each piece has one reason to change:

| Module | Responsibility |
| --- | --- |
| `layout.ReportLayout` | the single `ReportRef → directory` mapping, shared by both sides |
| `producer.ArchivingResultParser` | write JUnit XML + `meta.json` (extends the operator's parser) |
| `sources.ReportSource` / `FileSystemReportSource` | read/index reports behind an interface (Dependency Inversion) |
| `web.create_app` | map HTTP onto a `ReportSource` — knows nothing about the filesystem |
| `plugin.PytestReportsPlugin` | register the app with Airflow |
| `compat` | the only module that imports Airflow; version differences resolved once |
| `models` | JSON-serializable view types; the web layer never sees operator types |

Adding a different backing store (e.g. an `XComReportSource` reading the
metadata DB) is a new `ReportSource`, not an edit of the web app (Open/Closed).

## Development

```bash
pip install -e '.[dev,web]'
pytest -q
ruff check src tests && ruff format --check src tests
mypy src
```

## License

Apache-2.0. See [LICENSE](LICENSE).
