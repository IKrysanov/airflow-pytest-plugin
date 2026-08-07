# Getting started with airflow-pytest-plugin

## Running your first test

Two packages work together. `airflow-pytest-operator` runs pytest inside an Airflow task;
`airflow-pytest-plugin` archives what it produced and shows it in a dashboard.

Give a `PytestOperator` task an `ArchivingResultParser` instead of the operator's default
parser. That one change is what puts a run in the dashboard:

```python
from airflow_pytest_operator import PytestOperator
from airflow_pytest_plugin import ArchivingResultParser

PytestOperator(
    task_id="run_tests",
    test_path="tests/",
    parser=ArchivingResultParser(),   # was JUnitResultParser()
)
```

Then tell both sides where the reports live. The worker writes there and the API server
reads from there, so in a distributed deployment it has to be a **shared volume** both can
see:

```bash
export AIRFLOW_PYTEST_REPORTS_ROOT=/opt/airflow/pytest-reports
```

or in `airflow.cfg`:

```ini
[pytest_reports]
reports_root = /opt/airflow/pytest-reports
```

Run the task once, then open **Browse -> Pytest Reports** in Airflow. The plugin registers
itself through the `airflow.plugins` entry point, so there is nothing else to configure.

## Where reports are stored

One directory per attempt, so a retry never overwrites the run before it:

```
{reports_root}/{dag_id}/{run_id}/{task_id}/t{try_number}/
```

Each directory holds the JUnit report and a `meta.json` index. Nothing is ever deleted
automatically -- see the retention settings if the archive should be pruned.

## Do I need cleanup="never"?

No. In the operator the *parser* owns the report location, and a directory the parser
supplied is never removed by the runner under any cleanup policy. `cleanup="never"` only
matters when the runner uses throwaway temporary directories, which is the fragile path
this plugin replaces.

## Previewing the dashboard without Airflow

```bash
python -m airflow_pytest_plugin.web --root ./pytest-reports --port 8000
```

Useful for looking at an archive copied off a server, or for trying the viewer before
installing anything into Airflow.
