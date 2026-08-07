# Deleting old reports

## Nothing is deleted automatically

Reports are kept forever until someone prunes them. The plugin never deletes on its own,
because the archive is the only copy of what a run produced.

Turn on any of the limits below and schedule the cleanup from a maintenance DAG:

| Setting | Default | Meaning |
| --- | --- | --- |
| `AIRFLOW_PYTEST_RETENTION_MAX_AGE_DAYS` | unset | delete runs older than N days |
| `AIRFLOW_PYTEST_RETENTION_MAX_RUNS` | unset | keep only the N newest runs of each DAG and task |
| `AIRFLOW_PYTEST_RETENTION_MAX_TOTAL_MB` | unset | keep the whole archive under N megabytes, deleting oldest first |

## A maintenance DAG

```python
from airflow_pytest_plugin import prune_reports

with DAG("pytest_reports_retention", schedule="@daily", catchup=False):
    PythonOperator(task_id="prune", python_callable=prune_reports)
```

## Size limits when reading

| Setting | Default | Meaning |
| --- | --- | --- |
| `AIRFLOW_PYTEST_MAX_REPORT_MIB` | `64` | largest report the viewer opens. A larger run stays in the list with its real numbers, but opening it says so instead. `0` removes the limit |
| `AIRFLOW_PYTEST_MAX_META_MIB` | `16` | largest run index decoded whole, about a quarter of a million tests. Past it the run still lists, opens and is pruned as usual; only its per-test data is read from the report instead |
