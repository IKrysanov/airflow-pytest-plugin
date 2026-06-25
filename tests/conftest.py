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

import json
import os
from dataclasses import dataclass

import pytest

from airflow_pytest_plugin.layout import ALLURE_DIRNAME, META_FILENAME, ReportLayout
from airflow_pytest_plugin.models import ReportRef


def junit_xml(
    *, passed: int = 1, failed: int = 0, errors: int = 0, skipped: int = 0
) -> str:
    """Build a tiny valid pytest-style JUnit XML document."""
    cases = []
    i = 0
    for _ in range(passed):
        cases.append(
            f'<testcase classname="tests.test_x" name="test_p{i}" time="0.01"/>'
        )
        i += 1
    for _ in range(failed):
        cases.append(
            f'<testcase classname="tests.test_x" name="test_f{i}" time="0.02">'
            f'<failure message="boom {i}">assert False</failure></testcase>'
        )
        i += 1
    for _ in range(errors):
        cases.append(
            f'<testcase classname="tests.test_x" name="test_e{i}" time="0.0">'
            f'<error message="kaboom {i}">RuntimeError</error></testcase>'
        )
        i += 1
    for _ in range(skipped):
        cases.append(
            f'<testcase classname="tests.test_x" name="test_s{i}" time="0.0">'
            f'<skipped message="nope {i}"/></testcase>'
        )
        i += 1
    total = passed + failed + errors + skipped
    body = "".join(cases)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite name="pytest" tests="{total}" '
        f'failures="{failed}" errors="{errors}" skipped="{skipped}" time="0.123">'
        f"{body}</testsuite></testsuites>"
    )


def write_report(
    root: str,
    ref: ReportRef,
    *,
    passed: int = 1,
    failed: int = 0,
    errors: int = 0,
    skipped: int = 0,
    created_at: str = "2026-06-21T10:00:00+00:00",
) -> str:
    """Materialise a report (junit.xml + meta.json) under ``root`` for ``ref``."""
    layout = ReportLayout()
    out_dir = layout.dir_for(root, ref)
    os.makedirs(out_dir, exist_ok=True)
    with open(layout.report_path(root, ref), "w", encoding="utf-8") as fh:
        fh.write(
            junit_xml(passed=passed, failed=failed, errors=errors, skipped=skipped)
        )
    meta = {
        "schema_version": 1,
        "dag_id": ref.dag_id,
        "run_id": ref.run_id,
        "task_id": ref.task_id,
        "try_number": ref.try_number,
        "map_index": ref.map_index,
        "logical_date": None,
        "created_at": created_at,
        "report_file": "junit.xml",
        "summary": {
            "total": passed + failed + errors + skipped,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "duration": 0.123,
            "exit_code": 0 if (failed + errors) == 0 else 1,
            "success": (failed + errors) == 0,
            "failed_node_ids": [],
        },
    }
    with open(os.path.join(out_dir, META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    return out_dir


def write_allure(root: str, ref: ReportRef, files: dict | None = None) -> str:
    """Add an allure-results dir (+ flag meta['allure']) to an existing report."""
    files = files or {"abc-result.json": '{"name": "t", "status": "passed"}'}
    out_dir = ReportLayout().dir_for(root, ref)
    allure_dir = os.path.join(out_dir, ALLURE_DIRNAME)
    os.makedirs(allure_dir, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(allure_dir, name), "w", encoding="utf-8") as fh:
            fh.write(content)
    meta_path = os.path.join(out_dir, META_FILENAME)
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        meta["allure"] = True
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
    return allure_dir


def write_tests(
    root: str,
    ref: ReportRef,
    rows: list,
    *,
    created_at: str = "2026-06-21T10:00:00+00:00",
) -> str:
    """Write a report whose meta carries a per-test outcomes map (no junit needed)."""
    out_dir = ReportLayout().dir_for(root, ref)
    os.makedirs(out_dir, exist_ok=True)
    tests = [[r[0], r[1], r[2] if len(r) > 2 else 0.0] for r in rows]
    meta = {
        "schema_version": 1,
        "dag_id": ref.dag_id,
        "run_id": ref.run_id,
        "task_id": ref.task_id,
        "try_number": ref.try_number,
        "map_index": ref.map_index,
        "logical_date": None,
        "created_at": created_at,
        "report_file": "junit.xml",
        "summary": {},
        "tests": tests,
    }
    with open(os.path.join(out_dir, META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    return out_dir


def write_report_xml(
    root: str,
    ref: ReportRef,
    xml: str,
    *,
    created_at: str = "2026-06-21T10:00:00+00:00",
    summary: dict | None = None,
) -> str:
    """Materialise a report with a caller-supplied JUnit XML body."""
    layout = ReportLayout()
    out_dir = layout.dir_for(root, ref)
    os.makedirs(out_dir, exist_ok=True)
    with open(layout.report_path(root, ref), "w", encoding="utf-8") as fh:
        fh.write(xml)
    meta = {
        "schema_version": 1,
        "dag_id": ref.dag_id,
        "run_id": ref.run_id,
        "task_id": ref.task_id,
        "try_number": ref.try_number,
        "map_index": ref.map_index,
        "logical_date": None,
        "created_at": created_at,
        "report_file": "junit.xml",
        "summary": summary or {},
    }
    with open(os.path.join(out_dir, META_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    return out_dir


@dataclass
class FakeTI:
    dag_id: str
    task_id: str
    run_id: str
    try_number: int = 1
    map_index: int = -1


@pytest.fixture
def reports_root(tmp_path) -> str:
    return str(tmp_path / "pytest-reports")
