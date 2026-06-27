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

from __future__ import annotations

import pytest

from airflow_pytest_plugin.models import ReportRef


def test_token_round_trips():
    ref = ReportRef(
        dag_id="my_dag",
        run_id="scheduled__2024-01-01T00:00:00+00:00",
        task_id="run_tests",
        try_number=2,
        map_index=3,
    )
    assert ReportRef.from_token(ref.token) == ref


def test_token_is_url_safe():
    ref = ReportRef("d", "r+with/odd:chars", "t", 1)
    token = ref.token
    assert "/" not in token and "+" not in token and "=" not in token


def test_from_token_rejects_garbage():
    with pytest.raises(ValueError):
        ReportRef.from_token("!!!not-base64!!!")


def test_summary_to_dict_includes_has_allure():
    from airflow_pytest_plugin.models import ReportRef, ReportSummary

    ref = ReportRef("d", "r", "t", 1)
    base = ReportSummary(ref, 1, 1, 0, 0, 0, 0.1, True)
    assert base.to_dict()["has_allure"] is False
    with_allure = ReportSummary(ref, 1, 1, 0, 0, 0, 0.1, True, has_allure=True)
    assert with_allure.to_dict()["has_allure"] is True


def test_run_succeeds_pass_rate_threshold():
    from airflow_pytest_plugin.models import run_succeeds

    # 85% pass over executed tests is the boundary at the default 0.85.
    assert run_succeeds(passed=17, failed=3, errors=0, threshold=0.85) is True  # 0.85
    assert run_succeeds(passed=16, failed=4, errors=0, threshold=0.85) is False  # 0.80
    # Skipped tests are excluded from the rate (denominator = executed only).
    assert run_succeeds(passed=8, failed=0, errors=0, threshold=0.85) is True
    # Errors count against the rate just like failures.
    assert run_succeeds(passed=9, failed=0, errors=1, threshold=0.85) is True  # 0.90
    assert run_succeeds(passed=8, failed=0, errors=2, threshold=0.85) is False  # 0.80


def test_run_succeeds_edges():
    from airflow_pytest_plugin.models import run_succeeds

    # threshold 1.0 == strict "no failures or errors" (the legacy behaviour).
    assert run_succeeds(10, 0, 0, 1.0) is True
    assert run_succeeds(10, 1, 0, 1.0) is False
    # nothing executed (empty run / all skipped) is a pass.
    assert run_succeeds(0, 0, 0, 0.85) is True
