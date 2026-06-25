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


def test_plugin_enabled_by_default(monkeypatch):
    monkeypatch.delenv(config.ENABLE_ENV_VAR, raising=False)
    assert config.is_plugin_enabled() is True


def test_plugin_enabled_blank_is_default(monkeypatch):
    monkeypatch.setenv(config.ENABLE_ENV_VAR, "   ")
    assert config.is_plugin_enabled() is True


def test_plugin_disabled_by_falsey(monkeypatch):
    for val in ("0", "false", "False", "no", "off", "N", " f "):
        monkeypatch.setenv(config.ENABLE_ENV_VAR, val)
        assert config.is_plugin_enabled() is False, val


def test_plugin_enabled_by_truthy(monkeypatch):
    for val in ("1", "true", "yes", "on", "anything"):
        monkeypatch.setenv(config.ENABLE_ENV_VAR, val)
        assert config.is_plugin_enabled() is True, val


def test_scan_cache_ttl_default(monkeypatch):
    monkeypatch.delenv(config.SCAN_TTL_ENV_VAR, raising=False)
    assert config.get_scan_cache_ttl() == config.DEFAULT_SCAN_TTL


def test_scan_cache_ttl_from_env(monkeypatch):
    monkeypatch.setenv(config.SCAN_TTL_ENV_VAR, "5")
    assert config.get_scan_cache_ttl() == 5.0
    monkeypatch.setenv(config.SCAN_TTL_ENV_VAR, "0")
    assert config.get_scan_cache_ttl() == 0.0


def test_scan_cache_ttl_invalid_or_negative_falls_back(monkeypatch):
    for val in ("abc", "-1", "  "):
        monkeypatch.setenv(config.SCAN_TTL_ENV_VAR, val)
        assert config.get_scan_cache_ttl() == config.DEFAULT_SCAN_TTL, val
