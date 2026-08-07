# ArchivingResultParser parameters

## What the parser does

`ArchivingResultParser()` with no arguments already archives the run and its captured
output. Everything below is optional.

Options marked **worker-side** need their package installed where the tests actually run,
or pytest stops on an unknown argument.

## The full parameter list

| Name | Default | Meaning |
| --- | --- | --- |
| `report_root` | from settings | where reports are archived; overrides `AIRFLOW_PYTEST_REPORTS_ROOT` for this task |
| `layout` | built-in | how the archive directory is laid out |
| `logs` | `True` | archive the captured stdout/stderr of each test |
| `logs_only_fail` | `False` | keep captured output only for failing tests |
| `allure` | `False` | archive an Allure result directory alongside the JUnit report (worker-side) |
| `coverage` | `False` | collect and archive coverage (worker-side) |
| `coverage_source` | unset | the package or directory coverage is measured over, e.g. `"src"` |
| `coverage_threshold` | unset | fail the task when coverage falls below this percentage |
| `triage` | `False` | run AI failure triage on the worker and archive the verdict (worker-side) |
| `triage_provider` | unset | which provider triage uses, e.g. `"anthropic"` |
| `triage_budget` | unset | maximum number of failures triage will spend a model call on |
| `triage_timeout` | unset | seconds a single triage call may take |
| `email` | `False` | send an email about this run |
| `email_only_fail` | `False` | send it only when the suite did not pass |

## A fully equipped task

```python
ArchivingResultParser(
    logs_only_fail=True,
    allure=True,
    coverage=True,
    coverage_source="src",
    triage_provider="anthropic",
    triage_budget=20,
    email_only_fail=True,
)
```

## Captured output is archived verbatim

Whatever a test prints or logs is stored exactly as the run produced it. The plugin does
not mask secrets on this path, so a test that prints a token archives that token. Keep
credentials out of test output, or archive with `logs=False`. Who may read it is decided
by the same Airflow DAG permissions as the run itself.
