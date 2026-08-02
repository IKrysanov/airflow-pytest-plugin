# UI regression tests (Playwright)

End-to-end checks that the viewer dashboard renders and behaves correctly in a real
browser. They guard against the frontend "разъезжается" (layout/logic drift) on changes to
the single-page app in `web/templates.py`.

These are **opt-in** (pytest marker `ui`) and excluded from the default `pytest` run, so the
unit suite stays fast and browser-free.

## Run locally

```bash
pip install -e '.[web,ui-test]'     # fastapi + uvicorn + pytest-playwright
playwright install chromium         # one-time browser download
pytest -m ui                        # or: pytest -m ui tests/ui
```

Headed / debugging:

```bash
pytest -m ui --headed --slowmo 300
PWDEBUG=1 pytest -m ui tests/ui/test_ui_regression.py::test_donut_small_slices_do_not_overlap
```

## Embedded in real Airflow (`ui_airflow`)

A second suite boots a **real Airflow 3 api-server** with the plugin registered, and drives
Playwright against the embedded app at `/pytest-reports/` — proving the plugin mounts and
serves the working UI under Airflow's own runtime + auth manager (`simple_auth_manager_all_admins`
keeps it login-free so the test is about *our* UI, not Airflow's auth chrome).

```bash
pip install "apache-airflow==3.2.1" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.2.1/constraints-3.12.txt"
pip install -e '.[web,ui-test]' && playwright install chromium
pytest -m ui_airflow            # skips automatically if Airflow isn't installed
```

## How it works

`conftest.py` seeds a small, deterministic report tree (3 dag·tasks × 6 runs, hand-tuned to
light up every panel — flaky tests, current failures, a duration regression, and a run with
tiny donut slices), then boots the standalone dev server
(`python -m airflow_pytest_plugin.web --root <tmp>`) once per session. Each test loads a
fresh page (selection/scroll state resets on reload) and asserts on **stable hooks** (ids,
`data-*`, SVG geometry) rather than translatable text, so copy/locale changes don't break
them.

Several seeds share that generator, one dashboard (and dev server) each, so a test picks the
world it needs instead of building one:

| Fixture | World | What it is for |
|:--|:--|:--|
| `dash` | the small seed | precise assertions on every panel |
| `large_dash` | 40 dag·tasks × 80 runs | layout at scale (carousel, long lists) |
| `green_dash` | all-passing | the flaky UI must disappear entirely |
| `declining_dash` | health declining over time | the run-health trend must slope down |
| `email_dash` | server with an SMTP host | the ✉ button appears |
| `triage_dash` | all three triage states at once: `alpha` judged by a model (its newest run's pass broke), `gamma` report-only with no provider, `beta` never triaged | `test_ui_triage.py`: the card, the category filter, the per-failure panel, and the three run-list mark states |
| `assistant_dash` | report chat enabled with the offline fake provider | resizable dialog settings, evidence navigation, focus return, and 375 px full-screen layout |
| `empty_base_url` | no reports yet | localized first-run guidance and the mount-aware `/help` action |
| `evil_dash` | XSS payloads in test names, messages **and verdict prose**, plus a rerun selector carrying `;` | everything must render as inert text, and the copy line must be shell-quoted |

## CI

The `ui` job in `.github/workflows/ci.yml` installs the `ui-test` extra + the Chromium
browser and runs `pytest -m ui tests/ui` on its own runner.
