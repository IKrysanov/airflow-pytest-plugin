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
