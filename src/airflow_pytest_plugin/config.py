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

"""Resolve the report root (env, then Airflow config, then default)."""

from __future__ import annotations

import math
import os

from .compat import get_conf_value

ENV_VAR = "AIRFLOW_PYTEST_REPORTS_ROOT"
CONF_SECTION = "pytest_reports"
CONF_KEY = "reports_root"
DEFAULT_ROOT = "/opt/airflow/pytest-reports"

#: Toggles whether the reader plugin (UI + API) registers with Airflow. Default on.
ENABLE_ENV_VAR = "AIRFLOW_PYTEST_PLUGIN_ENABLE"
_FALSEY = frozenset({"0", "false", "no", "off", "n", "f"})


def is_plugin_enabled() -> bool:
    """Whether the reader plugin should register with Airflow.

    Reads ``AIRFLOW_PYTEST_PLUGIN_ENABLE`` -- ``True`` (the default when unset/empty)
    registers the UI + API; a falsey value (``0``/``false``/``no``/``off``) disables
    it. Only gates the reader; the producer-side parser is unaffected.
    """
    raw = os.environ.get(ENABLE_ENV_VAR)
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in _FALSEY


#: How long (seconds) the filesystem source may reuse a directory scan. A short
#: window lets the several summary-driven endpoints on one page load (list + flaky +
#: unique-tests, plus filter typing) share one tree walk instead of rescanning each.
SCAN_TTL_ENV_VAR = "AIRFLOW_PYTEST_SCAN_CACHE_TTL"
DEFAULT_SCAN_TTL = 2.0


def get_scan_cache_ttl() -> float:
    """Resolve the directory-scan cache TTL in seconds (``0`` disables caching).

    Reads ``AIRFLOW_PYTEST_SCAN_CACHE_TTL``; falls back to ``DEFAULT_SCAN_TTL``.
    A malformed or negative value falls back to the default.
    """
    raw = os.environ.get(SCAN_TTL_ENV_VAR)
    if raw is None or not raw.strip():
        return DEFAULT_SCAN_TTL
    try:
        ttl = float(raw.strip())
    except ValueError:
        return DEFAULT_SCAN_TTL
    return ttl if ttl >= 0 else DEFAULT_SCAN_TTL


#: Retention knobs (all opt-in; unset = keep everything). Each reads its env var,
#: then the matching ``[pytest_reports]`` cfg key. Non-positive/invalid -> unset.
RETENTION_MAX_AGE_DAYS_ENV = "AIRFLOW_PYTEST_RETENTION_MAX_AGE_DAYS"
RETENTION_MAX_RUNS_ENV = "AIRFLOW_PYTEST_RETENTION_MAX_RUNS"
RETENTION_MAX_TOTAL_MB_ENV = "AIRFLOW_PYTEST_RETENTION_MAX_TOTAL_MB"


def _positive_int_setting(env_var: str, conf_key: str) -> int | None:
    raw = os.environ.get(env_var)
    if raw is None or not raw.strip():
        raw = get_conf_value(CONF_SECTION, conf_key)
    if raw is None or not str(raw).strip():
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    return value if value > 0 else None


def get_retention_max_age_days() -> int | None:
    """Delete runs older than this many days (``None`` = no age limit)."""
    return _positive_int_setting(RETENTION_MAX_AGE_DAYS_ENV, "retention_max_age_days")


def get_retention_max_runs() -> int | None:
    """Keep at most this many newest runs per dag·task (``None`` = unlimited)."""
    return _positive_int_setting(RETENTION_MAX_RUNS_ENV, "retention_max_runs")


def get_retention_max_total_mb() -> int | None:
    """Total report-tree budget in MB (``None`` = unlimited)."""
    return _positive_int_setting(RETENTION_MAX_TOTAL_MB_ENV, "retention_max_total_mb")


#: Flaky-detector defaults (overridable per request via the ``window`` query param).
FLAKY_WINDOW_ENV = "AIRFLOW_PYTEST_FLAKY_WINDOW"
DEFAULT_FLAKY_WINDOW = 30
FLAKY_QUARANTINE_SCORE_ENV = "AIRFLOW_PYTEST_FLAKY_QUARANTINE_SCORE"
DEFAULT_FLAKY_QUARANTINE_SCORE = 0.5
#: Flakiness-score floor: below it a test is too steady to count as flaky, so a lone
#: blip in a long history (a near-zero flip rate) drops off the list.
FLAKY_MIN_SCORE_ENV = "AIRFLOW_PYTEST_FLAKY_MIN_SCORE"
DEFAULT_FLAKY_MIN_SCORE = 0.1


def get_flaky_window() -> int:
    """Default number of recent runs the flaky detector looks at per dag·task."""
    return (
        _positive_int_setting(FLAKY_WINDOW_ENV, "flaky_window") or DEFAULT_FLAKY_WINDOW
    )


def _unit_float_setting(env_var: str, conf_key: str, default: float) -> float:
    """A 0–1 float from env, then cfg; default on missing/invalid/out-of-range."""
    raw = os.environ.get(env_var)
    if raw is None or not raw.strip():
        raw = get_conf_value(CONF_SECTION, conf_key)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    return value if 0.0 <= value <= 1.0 else default


def get_flaky_quarantine_score() -> float:
    """Flakiness score (0–1) at/above which a test is flagged for quarantine."""
    return _unit_float_setting(
        FLAKY_QUARANTINE_SCORE_ENV,
        "flaky_quarantine_score",
        DEFAULT_FLAKY_QUARANTINE_SCORE,
    )


def get_flaky_min_score() -> float:
    """Flakiness score (0–1) below which a test is NOT counted as flaky."""
    return _unit_float_setting(
        FLAKY_MIN_SCORE_ENV, "flaky_min_score", DEFAULT_FLAKY_MIN_SCORE
    )


#: Duration-regression detector. A test is flagged "slower" when its recent-half
#: average duration is at least ``SLOW_FACTOR``× its older-half average AND the
#: absolute increase clears ``SLOW_MIN_DELTA`` seconds (the delta filters noise on
#: fast tests, where a tiny jitter can still beat the ratio). Shares the flaky window.
SLOW_FACTOR_ENV = "AIRFLOW_PYTEST_SLOW_FACTOR"
DEFAULT_SLOW_FACTOR = 1.3
SLOW_MIN_DELTA_ENV = "AIRFLOW_PYTEST_SLOW_MIN_DELTA"
DEFAULT_SLOW_MIN_DELTA = 0.5


def _positive_float_setting(
    env_var: str, conf_key: str, default: float, *, minimum: float
) -> float:
    """A float ≥ ``minimum`` from env, then cfg; default on missing/invalid/below."""
    raw = os.environ.get(env_var)
    if raw is None or not raw.strip():
        raw = get_conf_value(CONF_SECTION, conf_key)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    # Reject NaN/inf: they'd serialize to non-spec JSON ("NaN"/"Infinity") downstream.
    if not math.isfinite(value):
        return default
    return value if value >= minimum else default


def get_slow_factor() -> float:
    """Multiplier a test's recent-half avg duration must reach to count as a regression."""
    return _positive_float_setting(
        SLOW_FACTOR_ENV, "slow_factor", DEFAULT_SLOW_FACTOR, minimum=1.0
    )


def get_slow_min_delta() -> float:
    """Minimum absolute slowdown (seconds) for a duration regression to register."""
    return _positive_float_setting(
        SLOW_MIN_DELTA_ENV, "slow_min_delta", DEFAULT_SLOW_MIN_DELTA, minimum=0.0
    )


#: Pass-rate (0–1) at/above which a run counts as successful ("Passing runs"). The
#: rate is over executed tests, so a run can carry a few failures and still pass.
#: At 1.0 a run is successful only with zero failures/errors (the strict default of
#: older versions). 0.85 is a common "good enough" bar (ISTQB defines no fixed number).
SUCCESS_THRESHOLD_ENV = "AIRFLOW_PYTEST_SUCCESS_THRESHOLD"
DEFAULT_SUCCESS_THRESHOLD = 0.85


def get_success_threshold() -> float:
    """Pass-rate (0–1) at/above which a run counts as successful."""
    return _unit_float_setting(
        SUCCESS_THRESHOLD_ENV, "success_threshold", DEFAULT_SUCCESS_THRESHOLD
    )


def get_reports_root() -> str:
    """Resolve the report root directory (absolute path)."""
    env = os.environ.get(ENV_VAR)
    if env and env.strip():
        return os.path.abspath(env.strip())

    conf = get_conf_value(CONF_SECTION, CONF_KEY)
    if conf and conf.strip():
        return os.path.abspath(conf.strip())

    return os.path.abspath(DEFAULT_ROOT)
