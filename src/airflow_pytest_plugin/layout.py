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

"""The on-disk layout -- the one place that knows where a report lives.

Shared by the producer (which asks where to write) and the reader (where to read
a report, and how to discover all of them via :data:`META_FILENAME`), so the two
can never drift. The directory is a human-friendly container; the authoritative
identity lives in ``meta.json`` / the :class:`ReportRef` token, so the path
sanitisation below can be lossy without losing information.
"""

from __future__ import annotations

import os
import re

from .models import ReportRef

#: The JUnit XML filename the producer writes and the reader parses.
REPORT_FILENAME = "junit.xml"
#: The sidecar identity+summary file. Its presence marks a stored report.
META_FILENAME = "meta.json"

# Filesystem-safe component encoder. Airflow ``run_id`` values routinely carry
# ``:`` and ``+`` (e.g. ``scheduled__2024-01-01T00:00:00+00:00``), which are
# awkward or illegal on some filesystems. We map anything outside a conservative
# safe set to ``_``. This is intentionally lossy: the true, exact identity is
# preserved in meta.json / the ReportRef token, never recovered from the path.
_UNSAFE = re.compile(r"[^A-Za-z0-9._=+-]")


def _safe(component: str) -> str:
    cleaned = _UNSAFE.sub("_", component)
    # Guard against empty / dot components producing a path that escapes root.
    return cleaned or "_"


class ReportLayout:
    """Maps a :class:`ReportRef` to its directory under a report root::

        {root}/{dag_id}/{run_id}/{task_id}/t{try_number}[/m{map_index}]

    The ``m{map_index}`` segment is added only for mapped tasks. A pure function
    of its inputs, so the reader can locate a report from a token without
    scanning the filesystem.
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
        """Absolute path to the JUnit XML for ``ref``."""
        return os.path.join(self.dir_for(root, ref), REPORT_FILENAME)

    def meta_path(self, root: str, ref: ReportRef) -> str:
        """Absolute path to the ``meta.json`` for ``ref``."""
        return os.path.join(self.dir_for(root, ref), META_FILENAME)
