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

"""Minimal DAG wiring the archiving parser into a PytestOperator.

The only change from a plain operator setup is the ``parser=`` argument: swap
``JUnitResultParser`` for ``ArchivingResultParser`` and every run is
archived where the Pytest Reports UI can find it. No ``cleanup`` tuning needed
-- a parser-supplied directory is never removed by the runner.
"""

from __future__ import annotations

import pendulum
from airflow import DAG
from airflow_pytest_operator import PytestOperator

from airflow_pytest_plugin import ArchivingResultParser

with DAG(
    dag_id="pytest_reports_example",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["pytest", "example"],
):
    PytestOperator(
        task_id="run_tests",
        test_path="tests/",
        # report_root defaults to AIRFLOW_PYTEST_REPORTS_ROOT / the
        # [pytest_reports] reports_root config / /opt/airflow/pytest-reports.
        parser=ArchivingResultParser(allure=False),
        # Tests failing should not abort the pipeline here; the outcome is in
        # XCom and in the reports UI either way.
        fail_on_test_failure=False,
    )
