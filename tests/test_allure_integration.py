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

"""End-to-end against the REAL allure-pytest.

Unit tests fake the results directory, which cannot show whether ``--alluredir`` actually
lands where the archive expects it. This drives a real pytest run through the flags the
parser splices, then follows the results all the way to the viewer's download: results in
the run's own directory, the ``has_allure`` flag the button is drawn from, and a zip that
opens.

Skipped when allure-pytest isn't installed (it is an optional integration), so the default
suite is unaffected.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import textwrap
import zipfile

import pytest

from airflow_pytest_plugin.layout import ALLURE_DIRNAME, META_FILENAME
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.producer import ArchivingResultParser, archiving_parser
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import FakeTI

pytest.importorskip("allure_pytest", reason="allure-pytest is an optional integration")


def _project(tmp_path):
    proj = tmp_path / "suite"
    proj.mkdir()
    (proj / "test_allure_demo.py").write_text(
        textwrap.dedent("""
            import pytest

            def test_passes():
                print("hello")

            def test_fails():
                assert 1 == 2

            @pytest.mark.skip(reason="demo")
            def test_skipped():
                pass
        """),
        encoding="utf-8",
    )
    return proj


def _archive(proj, root, monkeypatch, *, extra_args=()):
    """Run pytest through the parser's own flags and archive the result."""
    ti = FakeTI(dag_id="al_dag", task_id="pytest", run_id="run1", try_number=1)
    monkeypatch.setattr(
        archiving_parser, "get_current_context", lambda: {"ti": ti, "run_id": "run1"}
    )
    parser = ArchivingResultParser(report_root=str(root), allure=True)
    req = parser.report_request(str(proj))
    os.makedirs(os.path.dirname(req.report_path), exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test_allure_demo.py",
            "-p",
            "no:cacheprovider",
            "-q",
            *req.pytest_args,
            *extra_args,
        ],
        cwd=proj,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, f"expected one failing test:\n{proc.stdout}"
    parser.parse(req.report_path, exit_code=proc.returncode)
    return os.path.dirname(req.report_path)


def test_allure_results_land_in_the_run_directory_and_reach_the_download(
    tmp_path, monkeypatch
):
    root = tmp_path / "reports"
    run_dir = _archive(_project(tmp_path), root, monkeypatch)

    # Inside the run's own directory, beside junit.xml -- not in a temp dir the archive
    # would lose, and not shared with the next run.
    results = os.listdir(os.path.join(run_dir, ALLURE_DIRNAME))
    assert [r for r in results if r.endswith("-result.json")]
    # executor.json links the TestOps launch back to this Airflow run.
    assert "executor.json" in results
    meta = json.load(open(os.path.join(run_dir, META_FILENAME), encoding="utf-8"))
    assert meta["allure"] is True

    src = FileSystemReportSource(report_root=str(root), scan_cache_ttl=0)
    summary = src.list_summaries()[0]
    assert summary.has_allure is True  # what the download button is drawn from

    ref = ReportRef("al_dag", "run1", "pytest", 1, -1)
    blob = b"".join(src.allure_stream(ref) or [])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.testzip() is None
        assert sorted(zf.namelist()) == sorted(results)


def test_a_task_that_sets_its_own_alluredir_leaves_the_archive_without_results(
    tmp_path, monkeypatch, caplog
):
    # The runner splices the task's pytest_args AFTER the parser's, and the last
    # --alluredir wins: the results are real but land outside the archive, so the run
    # honestly has no download. What must not happen is silence about it.
    root = tmp_path / "reports"
    elsewhere = tmp_path / "somewhere-else"

    with caplog.at_level("WARNING"):
        run_dir = _archive(
            _project(tmp_path),
            root,
            monkeypatch,
            extra_args=(f"--alluredir={elsewhere}",),
        )

    assert os.listdir(elsewhere)  # allure did run
    assert not os.path.exists(os.path.join(run_dir, ALLURE_DIRNAME))
    meta = json.load(open(os.path.join(run_dir, META_FILENAME), encoding="utf-8"))
    assert meta["allure"] is False
    assert "--alluredir" in caplog.text  # the task log says which of the two happened
