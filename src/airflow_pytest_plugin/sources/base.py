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
from collections.abc import Iterator
from typing import Any

from ..models import ReportDetail, ReportRef, ReportSummary, Verdict


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

    def verdicts(self, ref: ReportRef) -> dict[str, Verdict]:
        """One run's AI verdicts, keyed by canonical node id (``{}`` when it has none).

        Split out from :meth:`get_detail` because the cross-run views want the judgement
        without the JUnit parse: the heatmap marks a cell as a regression by reading this
        for each run in its window, measured at +8 ms over a 100-run window of 300-test
        runs -- cheap precisely because it touches neither ``junit.xml`` nor ``meta.json``.
        Optional; default empty.
        """
        return {}

    def allure_archive(
        self, ref: ReportRef, *, max_bytes: int | None = None
    ) -> bytes | None:
        """A zip of the report's raw Allure results, or ``None`` if it has none.

        ``max_bytes`` bounds peak memory: when set, a raw-results tree larger than the
        budget yields ``None`` instead of building a huge zip in RAM (the email path uses
        this). Optional; default unsupported. Feeds export to Allure TestOps.

        Prefer :meth:`allure_stream` for downloads -- this one holds the whole archive in
        memory, which does not scale to several concurrent requests.
        """
        return None

    def allure_stream(
        self, ref: ReportRef, *, chunk_size: int = 65536
    ) -> Iterator[bytes] | None:
        """The same zip as :meth:`allure_archive`, yielded in chunks, or ``None``.

        For serving downloads: the zip is compressed straight into the response and
        drained a chunk at a time -- never staged whole, on disk or in RAM -- so peak
        memory stays flat no matter how large the results are or how many downloads run at
        once. Optional; default unsupported.
        """
        return None

    def test_outcomes(self, ref: ReportRef) -> dict[str, dict[str, Any]] | None:
        """Map ``node_id -> {"outcome", "duration"}`` for one run, or ``None``.

        Powers cross-run views (compare/flaky/history). Optional; default unsupported.
        """
        return None

    def exists(self, ref: ReportRef) -> bool:
        """Whether this run is still stored, without reading or parsing it.

        Lets a caller tell "already gone" from "the store refused to remove it" after a
        failed delete -- the two need different words in front of a user, and asking
        :meth:`get_detail` would parse a whole report to answer a yes/no question.
        Default falls back to that parse for sources that can't answer cheaply.
        """
        return self.get_detail(ref) is not None

    def report_too_large(self, ref: ReportRef) -> bool:
        """Whether this run is stored but past the size this source will parse.

        Only reason a stored run can refuse to open. Lets the API say that instead of
        "not found", which sends the person who archived it looking for a run that is
        right there in the list. Default ``False``: a source with no such limit never
        has this problem.
        """
        return False

    def report_size(self, ref: ReportRef) -> int:
        """Bytes one report occupies on the backing store (``0`` if unknown).

        Drives size-based retention. Optional; default ``0`` leaves that policy
        inert for sources that can't measure themselves.
        """
        return 0

    def record_alert(self, ref: ReportRef, entry: dict[str, Any]) -> bool:
        """Append one email-notification record to the run's stored history.

        ``entry`` carries ``at``/``kind``/``recipients``/``ok``/``manual``; the history
        surfaces in :class:`~..models.ReportDetail.alerts`. Optional; default returns
        ``False``. Must be best-effort: never raise on ordinary storage problems.
        """
        return False

    def record_coverage(self, ref: ReportRef, coverage: float) -> bool:
        """Persist a run's overall coverage fraction (0-1) into the report.

        Lets the reader bake the operator's XCom coverage into the run so it becomes a
        stable part of the report (:attr:`~..models.ReportDetail.coverage`). Optional;
        default returns ``False``. Best-effort: never raise on ordinary storage problems.
        """
        return False
