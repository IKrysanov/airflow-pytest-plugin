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

"""Tests for the test×run heatmap: pure ``build_heatmap`` + the ``/api/heatmap`` route."""

from __future__ import annotations

import pytest

from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.web.routes import reports as reports_mod
from airflow_pytest_plugin.web.routes.reports import build_heatmap

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from airflow_pytest_plugin.sources import FileSystemReportSource  # noqa: E402
from airflow_pytest_plugin.web import create_app  # noqa: E402
from conftest import write_tests  # noqa: E402


def _run(run_id, created_at, **outcomes):
    return {"run_id": run_id, "created_at": created_at, "outcomes": outcomes}


def _app(reports_root, *, read_authorizer=None):
    return create_app(
        FileSystemReportSource(report_root=reports_root),
        authorizer=lambda d, u: True,
        read_authorizer=read_authorizer or (lambda d, u: True),
        user_dependency=lambda: object(),
    )


# --- build_heatmap (pure) -----------------------------------------------------
def test_build_heatmap_aligns_cells_and_marks_missing():
    runs = [
        _run("r1", "2026-06-01", a="passed", b="passed"),
        _run("r2", "2026-06-02", a="failed"),  # b didn't run -> "-"
        _run("r3", "2026-06-03", a="passed", b="error"),
    ]
    hm = build_heatmap(runs)
    assert [r["run_id"] for r in hm["runs"]] == ["r1", "r2", "r3"]
    cells = {t["node_id"]: t["cells"] for t in hm["tests"]}
    assert cells["a"] == ["p", "f", "p"]
    assert cells["b"] == ["p", "-", "e"]  # missing middle run
    assert hm["total_tests"] == 2 and hm["truncated"] is False


def test_build_heatmap_sorts_most_broken_first():
    runs = [
        _run("r1", "1", green="passed", reg="passed", flaky="failed"),
        _run("r2", "2", green="passed", reg="failed", flaky="passed"),
        _run("r3", "3", green="passed", reg="failed", flaky="failed"),
    ]
    order = [t["node_id"] for t in build_heatmap(runs)["tests"]]
    # reg (2 fails) before flaky (2 fails but... tie) ... green (0) is last
    assert order[-1] == "green"
    assert set(order[:2]) == {"reg", "flaky"}


def test_build_heatmap_caps_rows_and_flags_truncated():
    runs = [_run("r1", "1", **{f"t{i:03d}": "passed" for i in range(20)})]
    hm = build_heatmap(runs, max_rows=5)
    assert len(hm["tests"]) == 5
    assert hm["total_tests"] == 20 and hm["truncated"] is True


def test_build_heatmap_empty():
    hm = build_heatmap([])
    assert hm["runs"] == [] and hm["tests"] == []
    assert hm["total_tests"] == 0 and hm["truncated"] is False


def test_build_heatmap_unknown_outcome_is_marked():
    hm = build_heatmap([_run("r1", "1", x="weird")])
    assert hm["tests"][0]["cells"] == ["?"]


# --- /api/heatmap endpoint ----------------------------------------------------
def _seed_group(root, dag="dag", task="t"):
    for i, (a, b) in enumerate(
        [("passed", "passed"), ("failed", "passed"), ("passed", "failed")]
    ):
        write_tests(
            root,
            ReportRef(dag, f"r{i}", task, 1),
            [["a", a], ["b", b]],
            created_at=f"2026-06-0{i + 1}T00:00:00+00:00",
        )


def test_heatmap_endpoint_returns_matrix(reports_root):
    _seed_group(reports_root)
    d = TestClient(_app(reports_root)).get("/api/heatmap?dag_id=dag&task_id=t").json()
    assert d["dag_id"] == "dag" and d["task_id"] == "t" and d["window"] == 30
    assert [r["run_id"] for r in d["runs"]] == ["r0", "r1", "r2"]  # oldest -> newest
    cells = {t["node_id"]: t["cells"] for t in d["tests"]}
    assert cells["a"] == ["p", "f", "p"] and cells["b"] == ["p", "p", "f"]


def test_heatmap_endpoint_forbidden_when_read_denied(reports_root):
    _seed_group(reports_root)
    c = TestClient(_app(reports_root, read_authorizer=lambda d, u: False))
    assert c.get("/api/heatmap?dag_id=dag&task_id=t").status_code == 403


def test_heatmap_endpoint_clamps_window(reports_root):
    _seed_group(reports_root)
    c = TestClient(_app(reports_root))
    assert (
        c.get("/api/heatmap?dag_id=dag&task_id=t&window=1000").json()["window"] == 100
    )
    assert c.get("/api/heatmap?dag_id=dag&task_id=t&window=1").json()["window"] == 2


def test_heatmap_endpoint_requires_dag_and_task(reports_root):
    c = TestClient(_app(reports_root))
    assert c.get("/api/heatmap?dag_id=dag").status_code == 422  # task_id missing


def test_heatmap_endpoint_scopes_to_one_dag_task(reports_root):
    _seed_group(reports_root, dag="dag", task="t")
    write_tests(reports_root, ReportRef("other", "r0", "t", 1), [["z", "passed"]])
    d = TestClient(_app(reports_root)).get("/api/heatmap?dag_id=dag&task_id=t").json()
    nodes = {t["node_id"] for t in d["tests"]}
    assert nodes == {"a", "b"}  # "other" dag's test excluded


def test_heatmap_endpoint_row_cap(reports_root, monkeypatch):
    monkeypatch.setattr(reports_mod, "_HEATMAP_MAX_ROWS", 2)
    write_tests(
        reports_root,
        ReportRef("dag", "r0", "t", 1),
        [[f"n{i}", "passed"] for i in range(5)],
    )
    d = TestClient(_app(reports_root)).get("/api/heatmap?dag_id=dag&task_id=t").json()
    assert len(d["tests"]) == 2 and d["total_tests"] == 5 and d["truncated"] is True
