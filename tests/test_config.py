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


def test_retention_settings_from_env(monkeypatch):
    monkeypatch.setenv(config.RETENTION_MAX_RUNS_ENV, "25")
    assert config.get_retention_max_runs() == 25


def test_retention_settings_invalid_or_non_positive_are_none(monkeypatch):
    for val in ("abc", "0", "-4", "  "):
        monkeypatch.setenv(config.RETENTION_MAX_AGE_DAYS_ENV, val)
        monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
        assert config.get_retention_max_age_days() is None, val


def test_retention_settings_fall_back_to_cfg(monkeypatch):
    monkeypatch.delenv(config.RETENTION_MAX_TOTAL_MB_ENV, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: "50")
    assert config.get_retention_max_total_mb() == 50


def test_flaky_window_default_and_env(monkeypatch):
    monkeypatch.delenv(config.FLAKY_WINDOW_ENV, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_flaky_window() == config.DEFAULT_FLAKY_WINDOW
    monkeypatch.setenv(config.FLAKY_WINDOW_ENV, "50")
    assert config.get_flaky_window() == 50


def test_flaky_quarantine_score_default_env_and_clamp(monkeypatch):
    monkeypatch.delenv(config.FLAKY_QUARANTINE_SCORE_ENV, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_flaky_quarantine_score() == config.DEFAULT_FLAKY_QUARANTINE_SCORE
    monkeypatch.setenv(config.FLAKY_QUARANTINE_SCORE_ENV, "0.8")
    assert config.get_flaky_quarantine_score() == 0.8
    for bad in ("abc", "1.5", "-0.2"):  # invalid / out of 0–1 -> default
        monkeypatch.setenv(config.FLAKY_QUARANTINE_SCORE_ENV, bad)
        assert (
            config.get_flaky_quarantine_score() == config.DEFAULT_FLAKY_QUARANTINE_SCORE
        )


def test_flaky_min_score_default_env_and_clamp(monkeypatch):
    monkeypatch.delenv(config.FLAKY_MIN_SCORE_ENV, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_flaky_min_score() == config.DEFAULT_FLAKY_MIN_SCORE
    monkeypatch.setenv(config.FLAKY_MIN_SCORE_ENV, "0.25")
    assert config.get_flaky_min_score() == 0.25
    for bad in ("x", "2", "-1"):  # invalid / out of 0–1 -> default
        monkeypatch.setenv(config.FLAKY_MIN_SCORE_ENV, bad)
        assert config.get_flaky_min_score() == config.DEFAULT_FLAKY_MIN_SCORE


def test_success_threshold_default_env_and_clamp(monkeypatch):
    monkeypatch.delenv(config.SUCCESS_THRESHOLD_ENV, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_success_threshold() == config.DEFAULT_SUCCESS_THRESHOLD == 0.85
    monkeypatch.setenv(config.SUCCESS_THRESHOLD_ENV, "0.9")
    assert config.get_success_threshold() == 0.9
    monkeypatch.setenv(config.SUCCESS_THRESHOLD_ENV, "1")  # strict legacy mode
    assert config.get_success_threshold() == 1.0
    for bad in ("x", "1.5", "-0.1"):  # invalid / out of 0–1 -> default
        monkeypatch.setenv(config.SUCCESS_THRESHOLD_ENV, bad)
        assert config.get_success_threshold() == config.DEFAULT_SUCCESS_THRESHOLD


def test_slow_factor_default_env_and_floor(monkeypatch):
    monkeypatch.delenv(config.SLOW_FACTOR_ENV, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_slow_factor() == config.DEFAULT_SLOW_FACTOR == 1.3
    monkeypatch.setenv(config.SLOW_FACTOR_ENV, "2.5")
    assert config.get_slow_factor() == 2.5
    for bad in ("x", "0.5", "0"):  # invalid / below the 1.0 floor -> default
        monkeypatch.setenv(config.SLOW_FACTOR_ENV, bad)
        assert config.get_slow_factor() == config.DEFAULT_SLOW_FACTOR
    for bad in ("inf", "Infinity", "-inf", "nan", "1e400"):  # non-finite -> default
        monkeypatch.setenv(config.SLOW_FACTOR_ENV, bad)
        assert config.get_slow_factor() == config.DEFAULT_SLOW_FACTOR


def test_slow_min_delta_default_env_and_floor(monkeypatch):
    monkeypatch.delenv(config.SLOW_MIN_DELTA_ENV, raising=False)
    monkeypatch.setattr(config, "get_conf_value", lambda s, k: None)
    assert config.get_slow_min_delta() == config.DEFAULT_SLOW_MIN_DELTA == 0.5
    monkeypatch.setenv(config.SLOW_MIN_DELTA_ENV, "1.5")
    assert config.get_slow_min_delta() == 1.5
    monkeypatch.setenv(config.SLOW_MIN_DELTA_ENV, "0")  # zero is allowed (no floor)
    assert config.get_slow_min_delta() == 0.0
    for bad in ("x", "-1"):  # invalid / negative -> default
        monkeypatch.setenv(config.SLOW_MIN_DELTA_ENV, bad)
        assert config.get_slow_min_delta() == config.DEFAULT_SLOW_MIN_DELTA
