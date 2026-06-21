# Contributing

## Table of Contents

- [Getting started](#getting-started)
- [Quality gates](#quality-gates)
- [Design principles](#design-principles)
- [License headers on new files](#license-headers-on-new-files)
- [Tests](#tests)
- [Branching and pull requests](#branching-and-pull-requests)
- [Developer Certificate of Origin (DCO)](#developer-certificate-of-origin-dco)
- [Reviewing and merging (for maintainers)](#reviewing-and-merging-for-maintainers)
- [License](#license)

Thanks for your interest in improving **airflow-pytest-plugin**! This guide
covers the dev setup, the checks your change must pass, and how to submit it.

## Getting started

The package targets Python 3.10+ and Airflow 3.x. You do **not** need Airflow
installed to run the test suite — the plugin degrades cleanly without it
(`compat` returns `None`, the plugin base falls back to `object`).

```bash
git clone https://github.com/IKrysanov/airflow-pytest-plugin
cd airflow-pytest-plugin
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quality gates

Every change must pass all three checks. They run in CI; run them locally first:

```bash
ruff check src tests     # lint + import order
mypy src                 # strict static type checking
pytest -q                # full test suite
```

`ruff format src tests` applies formatting. Coverage is opt-in:
`pytest --cov=airflow_pytest_plugin --cov-report=term-missing` (CI enforces the
`fail_under` gate in `pyproject.toml`).

### pre-commit (optional but recommended)

`.pre-commit-config.yaml` mirrors CI: ruff + file hygiene on commit, `mypy` and
the test suite on push. Install once per clone:

```bash
pip install -e ".[dev]"
pip install pre-commit          # or: pipx install pre-commit
pre-commit install              # wires both the pre-commit and pre-push stages
```

### CI dependency locks

CI installs a **hash-pinned** toolchain from `requirements/` (for the OpenSSF
Scorecard Pinned-Dependencies check), not the `[dev]` extra directly:

- `requirements/dev.txt` — the lint + unit jobs (also pins the runtime dep, so
  they install the package with `-e . --no-deps`).
- `requirements/build.txt` — the release / TestPyPI build jobs (from `build.in`).

Regenerate after changing dependencies (the exact command is in each file's
header), e.g. for the dev lock:

```bash
uv pip compile pyproject.toml --extra dev --universal --generate-hashes \
  --python-version 3.10 --no-annotate --no-header -o requirements/dev.txt
```

Local development still uses `pip install -e ".[dev]"`.

## Design principles

This project follows SOLID deliberately; keep new code consistent with it.

- **One layout, shared.** `layout.ReportLayout` is the single `ReportRef →
  directory` mapping. The producer writes through it and the reader reads
  through it, so they can never drift. Don't compute report paths anywhere else.
- **Extend, don't modify.** A new backing store is a new `ReportSource`
  subclass (e.g. an `XComReportSource`), not a branch in the web app. A new
  report format is a new parser, not an edit of an existing one.
- **`compat/airflow.py` is the only module that imports Airflow**, and it does
  so lazily inside functions. Supporting a new Airflow release is a change
  confined to that file.
- **The web app stays thin.** It maps HTTP onto a `ReportSource` and nothing
  else — no filesystem access, no XML parsing, no layout knowledge.
- **Domain models stay framework-free.** `models.py` must not import Airflow,
  FastAPI, or pytest.
- **Reuse the operator.** Parse JUnit with the operator's `JUnitResultParser`;
  don't reimplement parsing.

## License headers on new files

Every source file carries the project's Apache-2.0 header with a **collective**
copyright line — it names the project's contributors, not any individual. Copy
it verbatim into new files; do not add your own name (your authorship is
recorded by your `Signed-off-by` line and the Git history).

```python
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
```

In Python files this goes **below** the module docstring, as in the existing
modules.

## Tests

- Add tests for any behaviour change; bug fixes come with a regression test.
- Prefer testing a `ReportSource` against a temp directory and the web app via
  FastAPI's `TestClient` over spinning up Airflow.
- Test the producer parser by monkeypatching `get_current_context` (see
  `tests/test_archiving_parser.py`).

## Branching and pull requests

This project uses **GitHub Flow**: `main` is the only long-lived branch and is
always releasable. Releases are tags (`vX.Y.Z`) on `main`.

1. **Fork** the repository.
2. **Create a topic branch from `main`** (`feat/xcom-source`, `fix/meta-race`,
   `docs/readme`).
3. **Open a pull request into `IKrysanov/airflow-pytest-plugin:main`.**
4. **Rebase, don't merge `main`** if it moves: `git fetch upstream && git rebase
   upstream/main`, then `git push --force-with-lease`.
5. Keep each PR **focused on one concern**.

Unreleased work accumulates under `[Unreleased]` in `CHANGELOG.md`.

## Developer Certificate of Origin (DCO)

This project tracks provenance with the
[DCO](https://developercertificate.org/) rather than a CLA. Sign off every
commit:

```bash
git commit -s -m "Your message"
```

This appends a `Signed-off-by: Your Name <you@example.com>` line. Fix a missing
sign-off before pushing:

```bash
git commit --amend -s --no-edit          # last commit
git rebase --signoff main                # a whole branch
```

The sign-off is checked on every PR by `.github/workflows/dco.yml`, which blocks
merge until all commits are signed.

## Reviewing and merging (for maintainers)

A pull request is ready to approve when:

1. **Targets `main`.**
2. **CI is green** — lint, type-check, the unit matrix, and the Airflow 3
   integration jobs pass.
3. **DCO check passes** — every commit is signed off.
4. **Coverage holds** — the `fail_under` gate is satisfied; new behaviour comes
   with new tests.
5. **License header present** on any new file (collective header, no names).
6. **Design principles respected** — one shared layout, new backends as new
   `ReportSource`s, only `compat/airflow.py` imports Airflow, the web app stays
   thin.
7. **Docs updated** — `README.md` and `CHANGELOG.md` reflect any behaviour or
   public-API change.

Use **rebase-merge** for a clean commit series, **squash-merge** for a single
concern spread across fixups. Tag a release only from a green `main`.

## License

By contributing, you agree that your contributions are licensed under the
Apache License 2.0.
