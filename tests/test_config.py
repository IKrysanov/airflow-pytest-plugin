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

from airflow_pytest_plugin import config


def test_reports_root_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_VAR, str(tmp_path))
    assert config.get_reports_root() == os.path.abspath(str(tmp_path))


def test_reports_root_blank_env_falls_through(monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, "   ")
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_reports_root() == os.path.abspath(config.DEFAULT_ROOT)


def test_reports_root_from_conf(monkeypatch):
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: "/conf/reports")
    assert config.get_reports_root() == os.path.abspath("/conf/reports")


def test_reports_root_default(monkeypatch):
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_reports_root() == os.path.abspath(config.DEFAULT_ROOT)
