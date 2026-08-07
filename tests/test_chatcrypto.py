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

"""Encryption at rest for the stored transcript.

The risky part of encrypting an existing table is not the cipher, it is everything
around it: rows written before the feature existed, a key that changes, a key that goes
away, and a deployment that has no key at all. Each of those has a test here, because
each of them is a way to lose somebody's chat history.
"""

from __future__ import annotations

import pytest

from airflow_pytest_plugin import chatcrypto

pytest.importorskip("cryptography")

from cryptography.fernet import Fernet  # noqa: E402

RUSSIAN = "почему упал test_login и что с этим делать?"


@pytest.fixture(autouse=True)
def _clear_cache():
    chatcrypto._cached = None
    yield
    chatcrypto._cached = None


@pytest.fixture
def key(monkeypatch):
    value = Fernet.generate_key().decode()
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", value)
    return value


def test_a_round_trip_returns_exactly_what_went_in(key):
    stored = chatcrypto.encrypt(RUSSIAN)

    assert stored != RUSSIAN
    assert RUSSIAN not in stored
    assert chatcrypto.decrypt(stored) == RUSSIAN


def test_nothing_is_encrypted_without_a_key(monkeypatch):
    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)

    assert chatcrypto.enabled() is False
    assert chatcrypto.encrypt(RUSSIAN) == RUSSIAN
    assert chatcrypto.decrypt(RUSSIAN) == RUSSIAN


def test_rows_written_before_this_existed_still_read(key):
    """The whole design rests on this: no marker, no migration, no flag day."""
    assert chatcrypto.decrypt("почему упал тест?") == "почему упал тест?"
    assert chatcrypto.decrypt("") == ""
    assert chatcrypto.decrypt(None) == ""


def test_a_rotated_key_still_reads_what_the_old_one_wrote(monkeypatch):
    """Airflow rotates by listing keys; the first writes and any of them reads."""
    old = Fernet.generate_key().decode()
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", old)
    stored = chatcrypto.encrypt(RUSSIAN)

    new = Fernet.generate_key().decode()
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", f"{new},{old}")

    assert chatcrypto.decrypt(stored) == RUSSIAN
    assert chatcrypto.decrypt(chatcrypto.encrypt("новый вопрос")) == "новый вопрос"


def test_a_key_that_is_gone_costs_one_message_not_the_chat(monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    stored = chatcrypto.encrypt(RUSSIAN)
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())

    assert chatcrypto.decrypt(stored) == chatcrypto.UNREADABLE


def test_a_key_removed_entirely_does_not_hand_back_ciphertext(monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    stored = chatcrypto.encrypt(RUSSIAN)
    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY")

    assert chatcrypto.decrypt(stored) == chatcrypto.UNREADABLE


def test_a_broken_key_falls_back_to_plain_text_rather_than_failing(monkeypatch, caplog):
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", "not-a-valid-fernet-key")

    assert chatcrypto.enabled() is False
    assert chatcrypto.encrypt(RUSSIAN) == RUSSIAN
    assert "unavailable" in caplog.text.lower()


def test_an_operator_can_switch_it_off(key, monkeypatch):
    monkeypatch.setenv(chatcrypto.ENCRYPT_ENV, "0")

    assert chatcrypto.enabled() is False
    assert chatcrypto.encrypt(RUSSIAN) == RUSSIAN


def test_switching_it_off_still_reads_what_was_already_encrypted(key, monkeypatch):
    """Otherwise the knob is a way to lose every chat written before it was turned."""
    stored = chatcrypto.encrypt(RUSSIAN)
    monkeypatch.setenv(chatcrypto.ENCRYPT_ENV, "0")

    assert chatcrypto.decrypt(stored) == RUSSIAN


@pytest.mark.parametrize(
    "text",
    [
        "gAAAAA",
        "gAAAAAB",
        "gAAAAA short",
        "смотри gAAAAABmZm9vYmFyYmF6cXV1eGNvcmdlZ3JhdWx0Z2FycGx5",
        "a" * 200,
        "-----BEGIN KEY-----",
    ],
)
def test_ordinary_text_is_never_mistaken_for_a_token(text, key):
    """A false positive here would replace someone's message with the placeholder."""
    assert chatcrypto.decrypt(text) == text


def test_two_encryptions_of_the_same_text_differ(key):
    """Fernet includes a random IV; equal ciphertexts would leak repeated questions."""
    assert chatcrypto.encrypt(RUSSIAN) != chatcrypto.encrypt(RUSSIAN)


def test_the_status_says_which_of_the_two_it_is(key, monkeypatch):
    assert chatcrypto.status() == {
        "history_encrypted": True,
        "fernet_key_configured": True,
    }

    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY")

    assert chatcrypto.status() == {
        "history_encrypted": False,
        "fernet_key_configured": False,
    }


def test_a_typed_lookalike_is_not_destroyed_on_a_server_with_no_key(monkeypatch):
    """Someone pasting "why does gAAAAAB… fail?" must get their message back.

    Shape alone is not enough to call a value ciphertext. A Fernet token has a
    structure -- version byte 0x80 and at least 73 bytes once base64 is undone -- and a
    string that merely starts the same way does not, so it is returned as typed instead
    of being replaced by the placeholder.
    """
    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY", raising=False)
    lookalike = "gAAAAAB" + "x" * 60

    assert chatcrypto.decrypt(lookalike) == lookalike


def test_a_structurally_real_token_still_reports_itself_unreadable(monkeypatch):
    """The case the placeholder exists for: the key is gone and the row is genuinely ours."""
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    stored = chatcrypto.encrypt(RUSSIAN)
    chatcrypto._cached = None
    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY")

    assert chatcrypto.decrypt(stored) == chatcrypto.UNREADABLE


def test_a_token_shaped_string_that_is_not_base64_is_left_alone(key):
    assert chatcrypto.decrypt("gAAAAAB" + "!" * 60) == "gAAAAAB" + "!" * 60
