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

"""What the storage layer does when the database stops cooperating.

"Absence is normal" is the layer's stated contract: no database, no driver, or tables
that are not there yet all fall back to the in-process behaviour instead of failing a
request. The paths that *deliver* that promise are the exception handlers, and they are
the ones a happy-path test never reaches -- so they are exercised here directly, by
taking the table away underneath a live store.

The CLI half is the same argument from the operator's side: every branch that prints a
diagnosis and exits non-zero is a branch somebody meets on their worst day.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

import pytest

from airflow_pytest_plugin import db

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa  # noqa: E402, I001


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv(db.DB_URL_ENV, f"sqlite:///{tmp_path / 'plugin.db'}")
    db.reset_engine()
    yield
    db.reset_engine()


def cli(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = db.main(list(args)) or 0
    return code, out.getvalue()


def drop(table: str) -> None:
    """Take a table away from underneath a store that is already using it."""
    with db.engine().begin() as connection:
        connection.execute(sa.text(f"DROP TABLE {table}"))


# =========================================================================================
# The table disappears while the store is live
# =========================================================================================


def test_reading_a_chat_survives_the_table_going_away():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "вопрос", "ответ", [], 1, conversation="c")
    assert len(store.load("alice", limit=9, conversation="c")) == 2

    drop(db.MESSAGE_TABLE)

    assert store.load("alice", limit=9, conversation="c") == []
    assert store.latest_conversation("alice") is None
    assert store.conversations("alice", limit=9) == []


def test_writing_a_chat_survives_the_table_going_away():
    db.upgrade()
    store = db.history_store()
    drop(db.MESSAGE_TABLE)

    # No exception reaches the request: the answer was already given, and losing the
    # transcript must not turn a served answer into a 500.
    store.append("alice", "вопрос", "ответ", [], 1, conversation="c")

    assert store.clear("alice", conversation="c") == 0


def test_renaming_survives_the_names_table_going_away():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "вопрос", "ответ", [], 1, conversation="c")

    drop(db.CONVERSATION_TABLE)

    assert store.rename("alice", "c", "Имя") == 0
    # The messages are still there; only the label could not be written.
    assert len(store.load("alice", limit=9, conversation="c")) == 2


def test_the_quota_store_survives_its_table_going_away():
    db.upgrade()
    quota = db.quota_store()
    quota.charge("alice", 20_000, 100)

    drop(db.USAGE_TABLE)

    assert quota.spent("alice", 20_000) == 0
    quota.charge("alice", 20_000, 100)  # must not raise


def test_the_rate_store_survives_its_table_going_away():
    db.upgrade()
    rate = db.rate_store()
    rate.charge("alice", 1)

    drop(db.RATE_TABLE)

    assert rate.spent("alice", 1) == 0
    rate.charge("alice", 1)  # must not raise


def test_re_keying_a_missing_table_is_reported_not_raised():
    """Every other statement here degrades; this one used to raise through the CLI.

    An operator running `rotate-key` against a database whose table is missing or
    unreadable got a SQLAlchemy traceback rather than a sentence -- on the one command
    they run when they are already worried about their data.
    """
    db.upgrade()
    drop(db.MESSAGE_TABLE)

    code, printed = cli("rotate-key")

    assert code == 1
    assert "could not" in printed.lower(), printed


def test_a_message_whose_evidence_is_not_json_still_reads():
    """The column is written by us, but a database is a shared thing.

    A row edited by hand -- or written by an older build -- must cost that message its
    buttons, not the whole chat.
    """
    db.upgrade()
    store = db.history_store()
    store.append("alice", "вопрос", "ответ", [{"report_id": "r"}], 1, conversation="c")

    with db.engine().begin() as connection:
        connection.execute(
            sa.text(
                f"UPDATE {db.MESSAGE_TABLE} SET evidence = :bad WHERE role = 'assistant'"
            ),
            {"bad": "{not json"},
        )

    restored = store.load("alice", limit=9, conversation="c")
    assert [item["content"] for item in restored] == ["вопрос", "ответ"]
    assert restored[1]["evidence"] == []


# =========================================================================================
# The CLI on somebody's worst day
# =========================================================================================


def test_doctor_stops_at_the_missing_tables():
    code, printed = cli("doctor")

    assert code == 1
    assert "upgrade" in printed


def test_purge_says_there_is_nothing_to_purge_yet():
    code, printed = cli("purge")

    assert code == 1
    assert "do not exist" in printed


def test_status_asks_for_the_upgrade_a_newer_build_needs(monkeypatch):
    db.upgrade()
    monkeypatch.setattr(db, "SCHEMA_VERSION", db.SCHEMA_VERSION + 1)

    code, printed = cli("status")

    assert code == 1
    assert "Run: python -m airflow_pytest_plugin.db upgrade" in printed


def test_upgrade_reports_a_database_that_refuses_the_tables(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("permission denied for schema public")

    monkeypatch.setattr(db, "upgrade", explode)

    code, printed = cli("upgrade")

    assert code == 1
    assert "Could not create the tables" in printed
    assert "permission denied" in printed


def test_doctor_reports_a_write_it_cannot_perform(monkeypatch):
    """The probe is the difference between "configured" and "actually works"."""
    db.upgrade()
    monkeypatch.setattr(db.ChatHistoryStore, "append", lambda *a, **k: None)

    code, printed = cli("doctor")

    assert code == 1
    assert "Write probe" in printed


# =========================================================================================
# What one request costs the metadata database
# =========================================================================================


def _count_statements(matching: str):
    """Record every statement this engine runs that contains ``matching``."""
    seen: list[str] = []

    def note(conn, cursor, statement, *rest):
        flat = " ".join(statement.split())
        if matching in flat:
            seen.append(flat)

    sa.event.listen(db.engine(), "before_cursor_execute", note)
    return seen, lambda: sa.event.remove(db.engine(), "before_cursor_execute", note)


def test_the_status_endpoint_probes_the_schema_version_once():
    """Every opened panel hits this, on Airflow's own metadata database.

    The probe answers "which version is in the database" -- something that changes only
    when somebody runs `upgrade` -- and it is not cached, so each readiness check pays a
    round trip. Reporting the daily spend added two more of them to a call that used to
    cost one.
    """
    from airflow_pytest_plugin.assistant import AssistantRuntime, PassthroughReducer
    from airflow_pytest_plugin.assistant.providers.fake import FakeAssistant

    db.upgrade()
    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=8_192,
        max_output_tokens=64,
        max_concurrent=2,
        history=db.history_store(),
        history_days=30,
        quota_store=db.quota_store(),
        daily_token_quota=100_000,
    )
    seen, stop = _count_statements("pytest_assistant_schema.version")
    try:
        runtime.status({"id": 1})
    finally:
        stop()

    assert len(seen) <= 1, f"{len(seen)} version probes for one status call"


def test_a_fresh_upgrade_is_seen_at_once():
    """Caching the probe must not leave a feature switched off after it was fixed.

    The dangerous staleness is the negative one: an operator runs `upgrade` and the
    workers keep answering "no tables" from a cached answer.
    """
    assert db.recorded_version() is None

    db.upgrade()

    assert db.recorded_version() == db.SCHEMA_VERSION
    assert db.table_ready(db.MESSAGE_TABLE) is True
