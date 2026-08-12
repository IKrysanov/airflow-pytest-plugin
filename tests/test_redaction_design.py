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

"""The scrubber and the byte budgets, tested to a method.

The scrubber is the security boundary of this feature: everything the reports contain
crosses it on the way to somebody else's API, and everything the model writes crosses it
on the way back. It is also a pile of heuristics tuned to numbers -- a minimum secret
length, two word-shape ratios, a token length -- and a heuristic is exactly the kind of
code where the untested case is the one that matters.

Three techniques:

* **Equivalence partitioning, two-sided.** Every class of secret must be removed and
  every class of ordinary report text must survive. Both halves are failures: a leak on
  one side, and on the other the deletion of the identifier the answer was asked about.
* **Boundary value analysis.** Each tuned number gets the values either side of it.
* **Decision table.** Which "no evidence" block is chosen is a function of two inputs;
  the table below fixes every combination rather than the two that had bugs.
"""

from __future__ import annotations

import pytest

from airflow_pytest_plugin.assistant.common import MAX_QUESTION_CHARS
from airflow_pytest_plugin.assistant.prompts import SKILLS, no_evidence_text
from airflow_pytest_plugin.assistant.redaction import (
    _ENV_WORD_SHAPE_RATIO,
    _MIN_ENV_SECRET,
    _WORD_SHAPE_RATIO,
    redact_text,
    safe_node_id,
)

# =========================================================================================
# Equivalence partitioning -- must be removed
# =========================================================================================

SECRETS = {
    "openai key": "sk-proj-" + "A1b2C3d4E5f6G7h8" * 3,
    "anthropic key": "sk-ant-api03-" + "Zx9" * 14,
    "github token": "ghp_" + "aB3" * 9,
    "github pat": "github_pat_" + "1A2b3C4d5E" * 3,
    "gitlab token": "glpat-" + "xY7z" * 6,
    "slack token": "xoxb-1234567890-abcdefghijkl",
    "stripe key": "sk_live_" + "4Kq9" * 6,
    "google api key": "AIza" + "Bc7dE9fG1h" * 3 + "Jk5lM",
    "google oauth": "GOCSPX-" + "mN4pQ" * 5,
    "google token": "ya29." + "a0Af" * 8,
    "sendgrid": "SG." + "aB3dE7" * 4 + "." + "9zY8xW7v" * 5,
    "pypi token": "pypi-" + "AgEIcHl" * 8,
    "huggingface": "hf_" + "QwErTyUiOp" * 3,
    "docker pat": "dckr_pat_" + "3fG7h" * 5,
    "databricks": "dapi" + "0123456789abcdef" * 2,
    "aws access key": "AKIAIOSFODNN7EXAMPLE",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVP",
    "url credential": "postgresql://apx:hunter2pass@db.internal:5432/reports",
    "bearer header": "Authorization: Bearer abcdef1234567890abcdef",
    "assignment": "password=Tr0ub4dor&3xtra",
    "assignment colon": "api_key: 9f8e7d6c5b4a3210",
    "hex blob": "9c1f2a7b4d6e8f0a1b2c3d4e5f607182",
}


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_every_class_of_secret_is_removed(name):
    secret = SECRETS[name]

    scrubbed = redact_text(f"the run failed: {secret} was rejected")

    assert secret not in scrubbed, scrubbed


# Where the two partitions meet. Deciding which side these fall on is the point of
# partitioning them: each is defensible, and neither should be an accident.


def test_an_identifier_is_a_secret_only_once_somebody_configures_it(monkeypatch):
    """A UUID in a report is a run id. The same UUID in the environment is a setting.

    Shape cannot separate them, so the environment does: a value the deployment sets is
    matched literally whatever it looks like, and everything else is judged on shape
    alone.
    """
    value = "550e8400-e29b-41d4-a716-446655440000"
    assert value in redact_text(f"run {value} failed")

    monkeypatch.setenv("REQUEST_ID", value)
    assert value not in redact_text(f"run {value} failed")


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("full git sha", "commit 4f2a1b9c8d3e5f7a9b1c3d5e7f9a1b3c5d7e9f1a broke it"),
        ("checksum", "checksum 9c1f2a7b4d6e8f0a1b2c3d4e5f607182 mismatch"),
    ],
)
def test_a_long_hex_run_is_treated_as_a_key(label, text):
    """Accepted collateral, pinned so it stays a decision rather than a surprise.

    Nothing tells a 40-character hex SHA apart from a 40-character hex API key, and the
    bias is stated in the module it lives in: a false positive costs an identifier in one
    answer, a false negative sends a live credential to somebody else's API. Short SHAs,
    UUIDs and dag run ids all survive, so the usual references still read.
    """
    assert "[REDACTED]" in redact_text(text)


def test_a_private_key_block_is_removed():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA3Tz2mr7SZiAMfQyuvBjM9Oi\n"
        "-----END RSA PRIVATE KEY-----"
    )

    assert "MIIEowIBAAKCAQEA" not in redact_text(f"deploy failed\n{pem}\ndone")


# =========================================================================================
# Equivalence partitioning -- must survive
# =========================================================================================

ORDINARY = {
    "node id": "tests/test_auth.py::test_login",
    "dotted node id": "tests.auth::test_login",
    "parametrised node id": "tests/test_api.py::test_call[endpoint-v2]",
    "camel class": "TestReportArchiveIntegration",
    "assertion": "AssertionError: assert 401 == 200",
    "traceback line": "tests/checkout.py:88: in test_total",
    "airflow words": "test_dag_import failed on the airflow scheduler",
    "executor": "running under LocalExecutor with 4 slots",
    "provider name": "provider 'anthropic' is selected",
    "russian prose": "тест падает из-за неверного округления суммы",
    "russian test name": "tests.suite::test_проверка_платежа",
    "duration": "test_invoice took 9.8 seconds",
    "dag run id": "manual__2026-08-09T10:00:00+00:00",
    "path": "/opt/airflow/dags/reports/checkout/run_a",
    "url no credential": "https://airflow.internal:8080/api/reports",
    "short sha": "commit 4f2a1b9 broke it",
    "uuid": "run 550e8400-e29b-41d4-a716-446655440000 failed",
    "version": "pandas 2.2.1 and pytest 8.3.2",
}


@pytest.mark.parametrize("name", sorted(ORDINARY))
def test_every_class_of_report_text_survives(name):
    text = ORDINARY[name]

    assert redact_text(text) == text, redact_text(text)


# =========================================================================================
# Boundary value analysis
# =========================================================================================


@pytest.mark.parametrize(
    "length", [_MIN_ENV_SECRET - 1, _MIN_ENV_SECRET, _MIN_ENV_SECRET + 1]
)
def test_an_environment_value_at_the_minimum_length(length, monkeypatch):
    """Below the minimum an environment value is left alone whatever it is named.

    The stock Airflow compose file ships `POSTGRES_PASSWORD=airflow`, and deleting every
    occurrence of a short common word from a plugin *for* Airflow costs more than it
    protects. At and above it, a secret-named value goes.
    """
    value = "q" * length
    monkeypatch.setenv("SOME_SERVICE_PASSWORD", value)

    scrubbed = redact_text(f"connection refused with {value} in the pool")

    if length < _MIN_ENV_SECRET:
        assert value in scrubbed
    else:
        assert value not in scrubbed


@pytest.mark.parametrize("ratio_name", ["free text", "environment value"])
def test_the_word_shape_ratio_separates_words_from_credentials(ratio_name, monkeypatch):
    """The ratio decides "is this a word or a credential" and the two sides differ.

    Straddling it deliberately: a string just wordy enough must be kept, one just
    opaque enough must go.
    """
    ratio = _WORD_SHAPE_RATIO if ratio_name == "free text" else _ENV_WORD_SHAPE_RATIO
    # 24 characters, of which `covered` read as words.
    wordy = "Report" * 4  # entirely word-shaped
    opaque = "X7q2Zk9Lm4Rt8Wv3Nb6Hs1Yd"  # camel humps of one or two letters

    if ratio_name == "environment value":
        monkeypatch.setenv("SETTING_A", wordy)
        monkeypatch.setenv("SETTING_B", opaque)
        assert wordy in redact_text(f"configured as {wordy}")
        assert opaque not in redact_text(f"configured as {opaque}")
    else:
        assert wordy in redact_text(f"class {wordy} failed")
        assert opaque not in redact_text(f"token {opaque} rejected")
    assert 0 < ratio < 1


@pytest.mark.parametrize("length", [3_999, 4_000, 4_001])
def test_a_question_at_the_length_cap(length, reports_root):
    """The wire contract bounds the question; the runtime must agree with it."""
    from airflow_pytest_plugin.assistant.common import AssistantQuery, clip_utf8

    question = "я" * length
    clipped = clip_utf8(question, MAX_QUESTION_CHARS)

    assert len(clipped.encode("utf-8")) <= MAX_QUESTION_CHARS
    assert AssistantQuery(question=question).question == question


@pytest.mark.parametrize("extra", [-1, 0, 1])
def test_a_node_id_at_its_byte_bound(extra, reports_root):
    """A node id longer than the bound is clipped and the record says it was."""
    from airflow_pytest_plugin.assistant.context import (
        _MAX_NODE_ID_BYTES,
        _bounded_node_id,
    )

    node_id = "t" * (_MAX_NODE_ID_BYTES + extra)

    cleaned, truncated = _bounded_node_id(node_id)

    assert len(cleaned.encode("utf-8")) <= _MAX_NODE_ID_BYTES
    assert truncated is (extra > 0)


# =========================================================================================
# Decision table -- which "no evidence" block an empty scope gets
# =========================================================================================
#
#  needs-evidence skill | any skill | documentation matched | block
#  ---------------------|-----------|-----------------------|-------------------
#  yes                  | yes       | either                | plain  ("widen your filters")
#  no                   | yes       | either                | optional
#  no                   | no        | yes                   | optional
#  no                   | no        | no                    | plain
#
# "plain" tells the reader nothing matched, which is right for a question about their
# runs and wrong for anything else -- it reads as a refusal.

PLAIN = "no report matched"
OPTIONAL = "no report was needed"


@pytest.mark.parametrize("skill", sorted(SKILLS))
@pytest.mark.parametrize("has_documentation", [False, True])
def test_the_no_evidence_block_for_every_skill(skill, has_documentation):
    block = no_evidence_text(
        commands=(SKILLS[skill].command,) if SKILLS[skill].command else (),
        question="",
        has_documentation=has_documentation,
    )

    expected = PLAIN if SKILLS[skill].needs_evidence else OPTIONAL
    assert expected in block, block


@pytest.mark.parametrize("has_documentation", [False, True])
def test_the_no_evidence_block_with_no_skill_at_all(has_documentation):
    block = no_evidence_text(
        commands=(), question="", has_documentation=has_documentation
    )

    assert (OPTIONAL if has_documentation else PLAIN) in block, block


def test_a_needs_evidence_skill_outranks_a_documentation_match():
    """A manual for a testing tool has a section on flaky tests.

    So "which tests are flaky?" matches documentation while being entirely a question
    about this week's runs, and must still be told that nothing matched.
    """
    flaky = next(name for name in SKILLS if SKILLS[name].needs_evidence)

    block = no_evidence_text(
        commands=(SKILLS[flaky].command,), question="", has_documentation=True
    )

    assert PLAIN in block


# =========================================================================================
# Error guessing -- text shaped like the plugin's own formats
# =========================================================================================


@pytest.mark.parametrize(
    "text",
    [
        "[REDACTED]",
        "the answer was [REDACTED] already",
        'CASE {"report":"R1","node_id":"x","outcome":"failed"}',
        "[R1] [R2] [R3]",
        "| fenced line",
    ],
)
def test_text_that_imitates_the_scrubbers_own_output_is_left_alone(text):
    """Scrubbing must be idempotent, and must not react to its own vocabulary."""
    once = redact_text(text)

    assert redact_text(once) == once


def test_a_secret_inside_a_parametrised_node_id_goes_but_the_selector_stays(
    monkeypatch,
):
    secret = "sk-ant-api03-" + "Zx9" * 14
    node_id = f"tests/test_api.py::test_call[key={secret}]"

    safe = safe_node_id(node_id)

    assert secret not in safe
    assert safe.startswith("tests/test_api.py::test_call[")
