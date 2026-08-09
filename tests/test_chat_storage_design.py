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

"""Stored chat, tested to a method rather than to a hunch.

The tests beside this file were each written for one defect somebody hit. That leaves
the spaces *between* the defects untested, and the storage layer is full of numbers --
a batch size, an id length, a title cap, a token's byte layout -- where the interesting
value is the one nobody thought to type.

Four techniques, one section each:

* **Boundary value analysis.** Every bound gets ``n-1``, ``n`` and ``n+1``. An
  off-by-one in a batch loop skips a row, and a skipped row here is a message that
  quietly stops being re-encrypted.
* **Decision table.** ``rotate-key`` reads four conditions and has to pick one of three
  behaviours. The table below enumerates every reachable combination instead of the two
  or three that happened to come up.
* **State transition.** One stored row moves through plain, encrypted, orphaned and
  recovered as an operator turns keys on, rotates them and drops them. The transitions
  worth testing are the ones an operator reaches by accident.
* **Error guessing.** Content chosen to collide with the implementation: a message whose
  text *is* the "cannot read this" placeholder, a title shaped exactly like ciphertext.
"""

from __future__ import annotations

import base64
import io
from contextlib import redirect_stdout

import pytest

from airflow_pytest_plugin import chatcrypto, db
from airflow_pytest_plugin.assistant import (
    AssistantRuntime,
    PassthroughReducer,
)
from airflow_pytest_plugin.assistant.providers.fake import FakeAssistant
from airflow_pytest_plugin.models import ReportRef
from conftest import write_report

pytest.importorskip("sqlalchemy")
pytest.importorskip("cryptography")

from cryptography.fernet import Fernet  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """A throwaway database and a known key, forgotten again afterwards."""
    monkeypatch.setenv(db.DB_URL_ENV, f"sqlite:///{tmp_path / 'plugin.db'}")
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv(chatcrypto.ENCRYPT_ENV, raising=False)
    db.reset_engine()
    chatcrypto._cached = None
    yield
    db.reset_engine()
    chatcrypto._cached = None


def key(monkeypatch, value: str | None) -> None:
    """Restart the process's view of the Fernet setting."""
    if value is None:
        monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY", raising=False)
    else:
        monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", value)
    chatcrypto._cached = None


def cli(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = db.main(list(args)) or 0
    return code, out.getvalue()


# =========================================================================================
# Boundary value analysis
# =========================================================================================


@pytest.mark.parametrize("length", [63, 64, 65])
def test_a_conversation_id_at_the_column_width(length):
    """64 is the column. At 65 the id must be replaced, not silently cut to fit."""
    given = "a" * length
    cleaned = db.clean_conversation(given)

    assert len(cleaned) <= 64
    assert db.clean_conversation(cleaned) == cleaned
    if length <= 64:
        assert cleaned == given
    else:
        # Replaced, and the replacement still says which original it came from.
        assert cleaned != given
        assert cleaned.endswith("~" + cleaned.rsplit("~", 1)[1])
        assert db.clean_conversation("a" * 66) != cleaned


@pytest.mark.parametrize("length", [199, 200, 201])
def test_a_derived_title_at_the_title_cap(length):
    """The cap applies to the title the list shows, however it was arrived at."""
    db.upgrade()
    store = db.history_store()
    question = "q" * length

    store.append("alice", question, "ответ", [], 1, conversation="c")

    title = store.conversations("alice", limit=5)[0]["title"]
    assert len(title) == min(length, db.MAX_TITLE)
    assert title == question[: db.MAX_TITLE]


@pytest.mark.parametrize("length", [199, 200, 201])
def test_a_chosen_title_at_the_title_cap(length):
    db.upgrade()
    store = db.history_store()
    store.append("alice", "вопрос", "ответ", [], 1, conversation="c")

    store.rename("alice", "c", "t" * length)

    assert len(store.conversations("alice", limit=5)[0]["title"]) == min(
        length, db.MAX_TITLE
    )


@pytest.mark.parametrize("count", [19, 20, 21])
def test_the_chat_list_at_its_limit(count, reports_root):
    """The flag has to flip exactly at the boundary: one chat over, not one under."""
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    store = db.history_store()
    for index in range(count):
        store.append(
            "id:1", f"вопрос {index}", "ответ", [], 1, conversation=f"c{index:03d}"
        )

    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
        history=store,
        history_days=30,
    )
    body = runtime.history({"id": 1})

    assert len(body["conversations"]) == min(count, db.MAX_CONVERSATIONS)
    assert body["conversations_truncated"] is (count > db.MAX_CONVERSATIONS)


@pytest.mark.parametrize("batch", [1, 2, 3])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_rotation_moves_every_row_around_a_batch_edge(batch, offset, monkeypatch):
    """A cursor that fails to advance loops; one that over-advances drops a row.

    Neither shows up with a single batch, so the row count is walked across the edge in
    both directions for several batch sizes.
    """
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    key(monkeypatch, old_key)
    monkeypatch.setattr(db, "_ROTATE_BATCH", batch)
    db.upgrade()
    store = db.history_store()
    pairs = max(1, batch + offset)
    for index in range(pairs):
        store.append(
            "id:1", f"в{index}", f"о{index}", [], 1, conversation=f"c{index:03d}"
        )
        store.rename("id:1", f"c{index:03d}", f"Имя {index}")

    key(monkeypatch, f"{new_key},{old_key}")
    moved = db.rotate_history_key()

    assert moved == {"messages": pairs * 2, "titles": pairs, "unreadable": 0}

    key(monkeypatch, new_key)
    for index in range(pairs):
        assert [
            item["content"]
            for item in store.load("id:1", limit=5, conversation=f"c{index:03d}")
        ] == [f"в{index}", f"о{index}"]


def test_rotation_at_the_real_batch_size(monkeypatch):
    """One run at the shipped constant, so the default is not merely assumed."""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    key(monkeypatch, old_key)
    db.upgrade()
    store = db.history_store()
    rows = db._ROTATE_BATCH + 1
    for index in range(rows):
        store.append(
            "id:1", f"в{index}", f"о{index}", [], 1, conversation=f"c{index:04d}"
        )

    key(monkeypatch, f"{new_key},{old_key}")
    moved = db.rotate_history_key()

    assert moved["messages"] == rows * 2
    key(monkeypatch, new_key)
    last = f"c{rows - 1:04d}"
    assert [
        item["content"] for item in store.load("id:1", limit=5, conversation=last)
    ] == [f"в{rows - 1}", f"о{rows - 1}"]


@pytest.mark.parametrize("payload", [72, 73, 74])
def test_the_structural_token_check_at_its_byte_boundary(payload, monkeypatch):
    """73 bytes is the shortest a real Fernet token can be.

    Below it the value cannot be ciphertext however much it looks like it, and returning
    the placeholder would delete a message somebody typed.
    """
    raw = bytes([0x80]) + bytes(payload - 1)
    lookalike = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    decrypted = chatcrypto.decrypt(lookalike)

    if payload < 73:
        assert decrypted == lookalike
    else:
        # Structurally a token, but not one this key made: reported, never returned raw.
        assert decrypted == chatcrypto.UNREADABLE


# =========================================================================================
# Decision table -- `rotate-key`
# =========================================================================================
#
#  tables | key set | key usable | encryption | exit | what it does
#  -------|---------|------------|------------|------|--------------------------------
#  no     | -       | -          | -          | 1    | refuses, nothing touched
#  yes    | no      | no         | off        | 0    | rewrites as plain text, says so
#  yes    | yes     | no         | off        | 1    | refuses, nothing touched
#  yes    | yes     | yes        | off (env)  | 0    | rewrites as plain text, says so
#  yes    | yes     | yes        | on         | 0    | re-encrypts
#
# The unlisted rows are unreachable: a key that is not set cannot be usable, and a key
# that is not usable cannot leave encryption on.


def _seed() -> None:
    db.history_store().append("id:1", "вопрос", "ответ", [], 1, conversation="c")


def test_rotate_key_refuses_before_the_tables_exist():
    code, printed = cli("rotate-key")

    assert code == 1
    assert "do not exist" in printed


def test_rotate_key_with_no_key_rewrites_as_plain_text(monkeypatch):
    db.upgrade()
    # Seeded with no key: this row is the one the command can act on. A row written
    # under a key it no longer has is the separate "unreadable" case below.
    key(monkeypatch, None)
    _seed()

    code, printed = cli("rotate-key")

    assert code == 0
    assert "PLAIN TEXT" in printed
    assert "Rewrote in plain text 2 message(s)" in printed


def test_rotate_key_with_an_unusable_key_refuses(monkeypatch):
    db.upgrade()
    _seed()
    key(monkeypatch, "please-encrypt-my-chat")

    code, printed = cli("rotate-key")

    assert code == 1
    assert "cannot be used" in printed


def test_rotate_key_with_encryption_switched_off_says_so(monkeypatch):
    db.upgrade()
    _seed()
    monkeypatch.setenv(chatcrypto.ENCRYPT_ENV, "0")

    code, printed = cli("rotate-key")

    assert code == 0
    assert "PLAIN TEXT" in printed
    assert chatcrypto.ENCRYPT_ENV in printed


def test_rotate_key_with_a_working_key_re_encrypts():
    db.upgrade()
    _seed()

    code, printed = cli("rotate-key")

    assert code == 0
    assert "Re-encrypted 2 message(s)" in printed
    assert "PLAIN TEXT" not in printed


# =========================================================================================
# State transition -- one row through an operator's whole year
# =========================================================================================


def test_one_row_through_every_key_state(monkeypatch):
    """plain -> encrypted -> rotated -> orphaned -> recovered -> re-encrypted.

    Each arrow is something an operator does deliberately; the value is in the order,
    because every state has to survive being entered from the one before it.
    """
    first = Fernet.generate_key().decode()
    second = Fernet.generate_key().decode()
    store = db.history_store()

    # 1. No key at all: plain text, readable.
    key(monkeypatch, None)
    db.upgrade()
    store.append("id:1", "вопрос", "ответ", [], 1, conversation="c")
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")] == [
        "вопрос",
        "ответ",
    ]

    # 2. A key appears. Old plain rows stay readable; the command encrypts them.
    key(monkeypatch, first)
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")][
        0
    ] == "вопрос"
    assert db.rotate_history_key()["messages"] == 2

    # 3. Rotation with both keys listed.
    key(monkeypatch, f"{second},{first}")
    assert db.rotate_history_key() == {"messages": 2, "titles": 0, "unreadable": 0}

    # 4. The old key is dropped -- still readable, because step 3 ran.
    key(monkeypatch, second)
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")][
        0
    ] == "вопрос"

    # 5. A key nobody planned for: orphaned, but not lost.
    third = Fernet.generate_key().decode()
    key(monkeypatch, third)
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")] == [
        chatcrypto.UNREADABLE,
        chatcrypto.UNREADABLE,
    ]
    assert db.rotate_history_key()["unreadable"] == 2

    # 6. Recovered by listing the key again, and moved across for good.
    key(monkeypatch, f"{third},{second}")
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")][
        0
    ] == "вопрос"
    assert db.rotate_history_key() == {"messages": 2, "titles": 0, "unreadable": 0}
    key(monkeypatch, third)
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")][
        0
    ] == "вопрос"


# =========================================================================================
# Error guessing -- content chosen to collide with the implementation
# =========================================================================================


def test_a_message_that_is_the_placeholder_is_still_re_encrypted(monkeypatch):
    """Somebody pastes the "cannot read this" sentence into the chat to ask about it.

    Rotation decided a row was unreadable by comparing the decrypted text to that
    sentence, so this row was skipped -- left under the old key while every other row
    moved, and then genuinely lost when the operator dropped it. It also told the
    operator rows had been left behind when none had.
    """
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    key(monkeypatch, old_key)
    db.upgrade()
    store = db.history_store()
    store.append("id:1", chatcrypto.UNREADABLE, "ответ", [], 1, conversation="c")
    store.rename("id:1", "c", chatcrypto.UNREADABLE)

    key(monkeypatch, f"{new_key},{old_key}")
    moved = db.rotate_history_key()

    assert moved == {"messages": 2, "titles": 1, "unreadable": 0}

    key(monkeypatch, new_key)
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")] == [
        chatcrypto.UNREADABLE,
        "ответ",
    ]
    assert store.conversations("id:1", limit=5)[0]["title"] == chatcrypto.UNREADABLE


def test_a_message_shaped_like_ciphertext_survives_rotation(monkeypatch):
    """ "why does gAAAAAB… fail?" is a question, not a token."""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    key(monkeypatch, old_key)
    db.upgrade()
    store = db.history_store()
    typed = "gAAAAA" + "B" * 60
    store.append("id:1", typed, "ответ", [], 1, conversation="c")

    key(monkeypatch, f"{new_key},{old_key}")
    db.rotate_history_key()
    key(monkeypatch, new_key)

    assert [i["content"] for i in store.load("id:5", limit=5, conversation="c")] == []
    assert [i["content"] for i in store.load("id:1", limit=5, conversation="c")][
        0
    ] == typed


def test_rotation_is_idempotent(monkeypatch):
    """An operator who is unsure whether it ran will run it again."""
    db.upgrade()
    _seed()

    first = db.rotate_history_key()
    second = db.rotate_history_key()

    assert first == second
    assert [
        i["content"] for i in db.history_store().load("id:1", limit=5, conversation="c")
    ] == ["вопрос", "ответ"]


def test_rotation_on_an_empty_table_reports_nothing(monkeypatch):
    db.upgrade()

    assert db.rotate_history_key() == {"messages": 0, "titles": 0, "unreadable": 0}
