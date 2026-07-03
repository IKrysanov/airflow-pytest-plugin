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

"""The report-source interface the web app depends on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import ReportDetail, ReportRef, ReportSummary


class ReportSource(ABC):
    """Access to archived pytest reports."""

    @abstractmethod
    def list_summaries(
        self,
        *,
        dag_id: str | None = None,
        run_id: str | None = None,
    ) -> list[ReportSummary]:
        """Return summaries, newest first; ``dag_id``/``run_id`` filter by substring."""
        raise NotImplementedError

    @abstractmethod
    def get_detail(self, ref: ReportRef) -> ReportDetail | None:
        """Return the full detail for one report, or ``None`` if it is gone."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, ref: ReportRef) -> bool:
        """Permanently remove the report for ``ref``; ``True`` if one was removed."""
        raise NotImplementedError

    def allure_archive(self, ref: ReportRef) -> bytes | None:
        """A zip of the report's raw Allure results, or ``None`` if it has none.

        Optional capability (default: unsupported) for exporting to Allure TestOps.
        """
        return None

    def test_outcomes(self, ref: ReportRef) -> dict[str, dict[str, Any]] | None:
        """Map ``node_id -> {"outcome", "duration"}`` for one run, or ``None``.

        Powers cross-run views (compare/flaky/history). Optional capability
        (default: unsupported).
        """
        return None

    def report_size(self, ref: ReportRef) -> int:
        """Bytes one report occupies on the backing store (``0`` if unknown).

        Used by size-based retention. Optional capability (default: ``0``, which
        leaves the size policy inert for sources that can't measure themselves).
        """
        return 0

    def record_alert(self, ref: ReportRef, entry: dict[str, Any]) -> bool:
        """Append one email-notification record to the run's stored history.

        ``entry`` carries ``at``/``kind``/``recipients``/``ok``/``manual``; the history
        surfaces in :class:`~..models.ReportDetail.alerts`. Optional capability
        (default: unsupported -> ``False``); implementations must be best-effort and
        never raise for ordinary storage problems.
        """
        return False
