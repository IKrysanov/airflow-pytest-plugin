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

"""The on-disk layout: maps a report to its directory, shared by producer and reader."""

from __future__ import annotations

import os
import re

from .models import ReportRef

#: JUnit XML the producer writes and the reader parses.
REPORT_FILENAME = "junit.xml"
#: Sidecar identity+summary file; its presence marks a stored report.
META_FILENAME = "meta.json"
#: Report subdir holding raw Allure results, for Allure TestOps export.
ALLURE_DIRNAME = "allure-results"
#: pytest-cov JSON report the producer asks for with ``coverage=True``, so the run's
#: coverage travels WITH the archive instead of only through the operator's XCom.
COVERAGE_FILENAME = "coverage.json"
#: pytest-triage's failure report, requested with ``triage=True``. Read at archive time,
#: distilled into the two files below, and then REMOVED -- it is the largest file a run
#: produces, repeats tracebacks junit.xml already holds, and is owner-only (it may carry
#: residual secrets even after redaction) so the reader could never open it. Kept only when
#: it could not be parsed, where it is the sole record of what went wrong.
TRIAGE_FILENAME = "triage.json"
#: The distilled per-test AI verdicts. Deliberately NOT part of ``meta.json``: every summary
#: endpoint pays a tree scan that parses each run's meta in full, so verdicts stored there
#: would be read by every dashboard load. Measured A/B at 3000 runs x 200 verdicts -- cold
#: scan 300ms -> 1325ms (4.4x), scanned corpus 48MB -> 1.3GB. Only views that read ONE run
#: at a time open this file: the run detail, and the heatmap over its window.
VERDICTS_FILENAME = "verdicts.json"

# Lossy on purpose: exact identity lives in meta.json / the ReportRef token,
# never recovered from the path.
_UNSAFE = re.compile(r"[^A-Za-z0-9._=+-]")


def _safe(component: str) -> str:
    cleaned = _UNSAFE.sub("_", component)
    # Reject empty / dot-only components so a traversal segment can't escape the root.
    if not cleaned or set(cleaned) <= {"."}:
        return "_"
    return cleaned


class ReportLayout:
    """Maps a :class:`ReportRef` to its directory under a report root::

    {root}/{dag_id}/{run_id}/{task_id}/t{try_number}[/m{map_index}]
    """

    def dir_for(self, root: str, ref: ReportRef) -> str:
        parts = [
            os.path.abspath(root),
            _safe(ref.dag_id),
            _safe(ref.run_id),
            _safe(ref.task_id),
            f"t{ref.try_number}",
        ]
        if ref.map_index >= 0:
            parts.append(f"m{ref.map_index}")
        return os.path.join(*parts)

    def report_path(self, root: str, ref: ReportRef) -> str:
        """Path to the JUnit XML for ``ref``."""
        return os.path.join(self.dir_for(root, ref), REPORT_FILENAME)

    def meta_path(self, root: str, ref: ReportRef) -> str:
        """Path to the ``meta.json`` for ``ref``."""
        return os.path.join(self.dir_for(root, ref), META_FILENAME)
