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

import os

from airflow_pytest_plugin.layout import ReportLayout
from airflow_pytest_plugin.models import ReportRef


def test_dir_for_plain_task():
    layout = ReportLayout()
    ref = ReportRef("dag", "run1", "task", 1)
    d = layout.dir_for("/root", ref)
    assert d == os.path.join("/root", "dag", "run1", "task", "t1")
    assert layout.report_path("/root", ref).endswith(os.path.join("t1", "junit.xml"))


def test_dir_for_mapped_task_adds_map_segment():
    layout = ReportLayout()
    ref = ReportRef("dag", "run1", "task", 1, map_index=5)
    assert layout.dir_for("/root", ref).endswith(os.path.join("t1", "m5"))


def test_unsafe_run_id_is_sanitised_but_deterministic():
    layout = ReportLayout()
    ref = ReportRef("dag", "scheduled__2024-01-01T00:00:00+00:00", "task", 1)
    d1 = layout.dir_for("/root", ref)
    d2 = layout.dir_for("/root", ref)
    assert d1 == d2  # pure function -> reader can relocate from a token
    # ':' (illegal on Windows/NTFS) is mapped away; the path stays usable.
    assert ":" not in d1
