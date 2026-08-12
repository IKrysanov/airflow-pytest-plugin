# The Pytest Reports dashboard

## What the dashboard shows

The list is one row per archived attempt: the DAG, the run, the task, the try number, when
it was archived, and the pass/fail/skip mix. Filters narrow it by DAG, task, run and
outcome; selecting rows scopes everything else -- including the assistant -- to just those
runs.

Opening a run shows every test case with its outcome, how long it took, its error and
traceback, plus whatever the test printed if captured output was archived.

## Reading a failing test

A failing case carries three things worth reading in order: the assertion or exception
message, the traceback frame in your own code, and the captured output leading up to it.
If AI triage ran on the worker, the archived verdict appears alongside as a **hypothesis**
-- it was produced without running anything, so it is a lead, not a diagnosis.

## Flaky tests

A test that alternates between pass and fail across runs of the same DAG and task is
reported as flaky. The dashboard shows the pass/fail split rather than a single verdict,
because "flaky" is a statement about several runs and never about one.

Quarantining is a decision for a person: `@pytest.mark.flaky` reruns it, `skip` stops
running it at all, and the dashboard's own quarantine hides it from the headline numbers.
Each of those hides a different thing, and none of them fixes the test.

## Coverage and Allure

When the parser archived coverage, the run shows its percentage and the per-file
breakdown. When it archived an Allure result directory, the run offers it for download.
Both are off by default and both are worker-side: the package has to be installed where
the tests run.

## Access

Every request re-checks Airflow's DAG read permissions on the server, so a run is visible
only to someone who may already read that DAG. That applies to the API, the dashboard and
the assistant alike -- there is no separate permission model to configure.
