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

"""View airflow-pytest-operator results in the Airflow 3 web UI.

A producer-side parser archives each JUnit report plus a ``meta.json`` sidecar;
a reader-side source and a FastAPI plugin serve a viewer over them.

Public API:
    ArchivingJUnitResultParser -- producer-side parser (use as ``parser=``)
    ReportSource / FileSystemReportSource -- reader interface + default source
    ReportRef / ReportSummary / ReportDetail / CaseView -- view models
    ReportLayout       -- the shared on-disk layout
    get_reports_root   -- resolve the report root (env/conf/default)
    create_app         -- build the FastAPI app (lazy; needs FastAPI)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config import get_reports_root
from .layout import ReportLayout
from .models import CaseView, ReportDetail, ReportRef, ReportSummary
from .producer import ArchivingJUnitResultParser
from .sources import FileSystemReportSource, ReportSource
from .version import __version__ as __version__

if TYPE_CHECKING:
    # Exposed lazily via __getattr__ so importing the package never eagerly
    # imports FastAPI (the producer-side parser must import cleanly on a worker
    # that has no web stack).
    from .web import create_app as create_app

__all__ = [
    "ArchivingJUnitResultParser",
    "ReportSource",
    "FileSystemReportSource",
    "ReportRef",
    "ReportSummary",
    "ReportDetail",
    "CaseView",
    "ReportLayout",
    "get_reports_root",
    "create_app",
    "__version__",
]


def __getattr__(name: str) -> object:
    if name == "create_app":
        from .web import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
