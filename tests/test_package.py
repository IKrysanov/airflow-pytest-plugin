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

import pytest

import airflow_pytest_plugin as pkg


def test_create_app_is_lazily_exported():
    # __getattr__ imports web.create_app lazily, keeping FastAPI off the parser import path.
    pytest.importorskip("fastapi")
    assert callable(pkg.create_app)


def test_unknown_attribute_raises():
    with pytest.raises(AttributeError):
        pkg.does_not_exist  # noqa: B018
