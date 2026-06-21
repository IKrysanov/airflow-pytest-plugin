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

"""Run the viewer standalone, without Airflow -- handy for local development.

    python -m airflow_pytest_plugin.web --root ./pytest-reports --port 8000

Then open http://127.0.0.1:8000/. Requires the ``[web]`` extra
(``pip install 'airflow-pytest-plugin[web]'``).
"""

from __future__ import annotations

import argparse

from ..sources import FileSystemReportSource
from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="airflow_pytest_plugin.web")
    parser.add_argument(
        "--root", default=None, help="report root (defaults to the resolved config)"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on extra
        raise SystemExit(
            "uvicorn is required to run the dev server: "
            "pip install 'airflow-pytest-plugin[web]'"
        ) from exc

    app = create_app(FileSystemReportSource(report_root=args.root))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
