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

"""The plugin's own tables: creation, versioning, and graceful absence."""

from __future__ import annotations

import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace

import pytest
import sqlalchemy as sa

from airflow_pytest_plugin import db
from airflow_pytest_plugin.assistant import (
    AssistantProviderError,
    AssistantProviderResponse,
    AssistantQuery,
    AssistantQuotaError,
    AssistantRuntime,
    AssistantTokenUsage,
    PassthroughReducer,
    audit,
)
from airflow_pytest_plugin.assistant.limits import UserLimits
from airflow_pytest_plugin.assistant.providers.fake import FakeAssistant
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import write_report, write_report_xml

pytest.importorskip("sqlalchemy")


#: Set this to a real PostgreSQL or MySQL URL to run the whole file against that engine.
#: The portable-upsert and grouping queries here are exactly the dialect-sensitive parts,
#: and SQLite alone does not prove them.
_OTHER_ENGINE = os.environ.get("AIRFLOW_PYTEST_TEST_DB_URL")


@pytest.fixture(autouse=True)
def _isolated_engine(monkeypatch, tmp_path):
    """Point the layer at a throwaway database and forget any cached engine."""
    monkeypatch.setenv(
        db.DB_URL_ENV, _OTHER_ENGINE or f"sqlite:///{tmp_path / 'plugin.db'}"
    )
    db.reset_engine()
    if _OTHER_ENGINE:
        _drop_everything()
    yield
    if _OTHER_ENGINE:
        _drop_everything()
    db.reset_engine()


def _drop_everything() -> None:
    """A shared server keeps its tables between tests; the SQLite file does not.

    Best effort: a test that repoints the layer at a deliberately unreachable URL leaves
    nothing to drop, and that is the test doing its job, not a failure to clean up.
    """
    try:
        metadata = db._build_metadata()
        active = db.engine()
        if metadata is not None and active is not None:
            metadata.drop_all(active)
    except Exception:
        pass
    db.reset_engine()


def test_upgrade_creates_the_tables_and_records_the_schema_version():
    assert db.status()["ready"] is False

    result = db.upgrade()

    assert result["created"] is True
    assert result["version"] == db.SCHEMA_VERSION
    state = db.status()
    assert state["ready"] is True and state["version"] == db.SCHEMA_VERSION
    assert state["url"].startswith(
        (_OTHER_ENGINE or "sqlite://").split("://")[0] + "://"
    )


def test_upgrade_is_idempotent():
    first = db.upgrade()
    second = db.upgrade()

    assert first["created"] is True and second["created"] is False
    assert second["version"] == db.SCHEMA_VERSION


def test_tables_are_prefixed_so_they_cannot_collide_in_airflows_database():
    db.upgrade()

    for table in db.METADATA.tables:
        assert table.startswith("pytest_assistant_"), table


def test_nothing_is_configured_when_there_is_no_url(monkeypatch):
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.setattr(db, "_airflow_url", lambda: None)
    db.reset_engine()

    state = db.status()

    assert state["configured"] is False and state["ready"] is False
    assert db.engine() is None


def test_quota_survives_a_restart_and_is_shared_between_workers():
    """The point of the table: one budget, not one per process."""
    db.upgrade()
    worker_a = UserLimits(daily_token_quota=1_000, store=db.quota_store())
    worker_b = UserLimits(daily_token_quota=1_000, store=db.quota_store())

    worker_a.charge("alice", 600)

    # A different process sees the spend immediately...
    assert worker_b.spent_today("alice") == 600
    worker_b.charge("alice", 400)
    assert worker_a.spent_today("alice") == 1_000
    assert worker_a.check("alice").allowed is False
    assert worker_b.check("alice").allowed is False

    # ...and so does a freshly started one.
    restarted = UserLimits(daily_token_quota=1_000, store=db.quota_store())
    assert restarted.check("alice").allowed is False
    assert restarted.check("bob").allowed is True


def test_concurrent_charges_do_not_lose_tokens():
    db.upgrade()
    limits = UserLimits(daily_token_quota=10_000_000, store=db.quota_store())
    errors: list[BaseException] = []

    def spend():
        try:
            for _ in range(20):
                limits.charge("alice", 5)
        except BaseException as error:  # noqa: BLE001 - surfaced below
            errors.append(error)

    threads = [threading.Thread(target=spend) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert limits.spent_today("alice") == 8 * 20 * 5


def test_quota_falls_back_in_process_when_the_tables_are_missing():
    """An operator who never ran the CLI still gets the old guard rail, not a crash."""
    limits = UserLimits(daily_token_quota=100, store=db.quota_store())

    limits.charge("alice", 100)

    assert limits.check("alice").allowed is False
    assert limits.check("bob").allowed is True


def test_a_new_day_starts_a_new_row():
    db.upgrade()
    store = db.quota_store()
    limits = UserLimits(daily_token_quota=100, store=store)
    day = [20_000]
    limits.today = lambda: day[0]

    limits.charge("alice", 100)
    assert limits.check("alice").allowed is False

    day[0] += 1
    assert limits.check("alice").allowed is True
    assert limits.spent_today("alice") == 0


def test_purge_removes_only_rows_older_than_the_cutoff():
    db.upgrade()
    store = db.quota_store()
    store.charge("alice", 20_000, 10)
    store.charge("alice", 20_009, 10)

    removed = db.purge_usage(before_day=20_005)

    assert removed == 1
    assert store.spent("alice", 20_000) == 0
    assert store.spent("alice", 20_009) == 10


def test_cli_reports_status_and_upgrades(capsys):
    assert db.main(["status"]) == 1
    assert "not initialised" in capsys.readouterr().out

    assert db.main(["upgrade"]) == 0
    assert "created" in capsys.readouterr().out

    assert db.main(["status"]) == 0
    output = capsys.readouterr().out
    assert f"version {db.SCHEMA_VERSION}" in output


def test_cli_explains_itself_when_no_database_is_configured(monkeypatch, capsys):
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.setattr(db, "_airflow_url", lambda: None)
    db.reset_engine()

    assert db.main(["upgrade"]) == 1
    assert db.DB_URL_ENV in capsys.readouterr().out


def test_two_api_servers_share_one_budget_end_to_end(tmp_path, reports_root):
    """The whole point, exercised through the runtime rather than the store."""
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    source = FileSystemReportSource(report_root=reports_root)

    class Provider:
        name = "capture"
        model = "capture-1"

        def answer(self, *, system: str, prompt: str, max_tokens: int):
            del system, prompt, max_tokens
            return AssistantProviderResponse(
                text="Answered [R1].",
                token_usage=AssistantTokenUsage(
                    input_tokens=400, output_tokens=100, total_tokens=500
                ),
            )

        def close(self) -> None:
            return None

    def worker():
        return AssistantRuntime(
            provider_factory=Provider,
            reducer_factory=PassthroughReducer,
            provider_name="capture",
            model_name="capture-1",
            context_model_name=None,
            max_context_bytes=16_384,
            max_output_tokens=256,
            max_concurrent=1,
            daily_token_quota=1_000,
            quota_store=db.quota_store(),
        )

    def ask(runtime):
        return runtime.ask(
            source=source,
            can_read=lambda dag, user: True,
            user={"username": "alice"},
            query=AssistantQuery(question="What failed?"),
        )

    first, second = worker(), worker()
    assert first.status()["quota_shared"] is True

    ask(first)  # 500 spent on worker one
    ask(second)  # 1000 spent, charged to the same row from worker two

    # Neither worker will serve Alice again today, and a third one agrees.
    for runtime in (first, second, worker()):
        with pytest.raises(AssistantQuotaError):
            ask(runtime)
    # A different principal is unaffected.
    assert second.ask(
        source=source,
        can_read=lambda dag, user: True,
        user={"username": "bob"},
        query=AssistantQuery(question="What failed?"),
    ).answer


def test_quota_is_not_shared_without_the_tables(reports_root):
    """Without the CLI step the runtime still works, just per process."""
    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        daily_token_quota=1_000,
        quota_store=db.quota_store(),
    )

    assert runtime.status()["quota_shared"] is False


def test_history_is_scoped_to_its_owner():
    """The security property: a query for one principal can never see another's."""
    db.upgrade()
    store = db.history_store()

    store.append("alice", "alice question", "alice answer", [], 10)
    store.append("bob", "bob question", "bob answer", [], 10)

    alice = store.load("alice", limit=12)
    assert [item["content"] for item in alice] == ["alice question", "alice answer"]
    assert all("bob" not in item["content"] for item in alice)
    assert [item["content"] for item in store.load("bob", limit=12)] == [
        "bob question",
        "bob answer",
    ]


def test_history_is_not_written_for_an_unidentifiable_principal():
    """Two users behind one unknown auth type must not share a transcript."""
    db.upgrade()
    store = db.history_store()

    store.append("unidentified", "who am i", "no idea", [], 10)

    assert store.load("unidentified", limit=12) == []


def test_history_keeps_only_the_newest_window():
    db.upgrade()
    store = db.history_store()
    for index in range(20):
        store.append("alice", f"question {index}", f"answer {index}", [], 1)

    restored = store.load("alice", limit=6)

    assert len(restored) == 6
    assert restored[0]["content"] == "question 17"
    assert restored[-1]["content"] == "answer 19"


def test_history_round_trips_evidence_and_tokens():
    db.upgrade()
    store = db.history_store()
    evidence = [
        {
            "key": "R1",
            "report_id": "token",
            "dag_id": "etl",
            "run_id": "r1",
            "task_id": "suite",
            "created_at": None,
        }
    ]

    store.append("alice", "what failed?", "this did [R1]", evidence, 150)
    restored = store.load("alice", limit=12)

    assert restored[1]["evidence"] == evidence
    assert restored[1]["total_tokens"] == 150
    assert restored[0]["evidence"] == []


def test_clearing_history_removes_only_the_callers_rows():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q", "a", [], 1)
    store.append("bob", "q", "a", [], 1)

    removed = store.clear("alice")

    assert removed == 2
    assert store.load("alice", limit=12) == []
    assert len(store.load("bob", limit=12)) == 2


def test_history_purge_drops_only_rows_past_retention():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "old", "old answer", [], 1)
    old_cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    store.append("alice", "new", "new answer", [], 1)

    # Everything written so far is older than tomorrow.
    assert db.purge_history(before=old_cutoff) == 4
    store.append("alice", "kept", "kept answer", [], 1)
    assert db.purge_history(before=datetime.now(timezone.utc) - timedelta(days=1)) == 0
    assert len(store.load("alice", limit=12)) == 2


def test_history_is_unavailable_without_the_tables():
    store = db.history_store()

    store.append("alice", "q", "a", [], 1)

    assert store.available is False
    assert store.load("alice", limit=12) == []


def _history_client(reports_root, *, user, history_days=30):
    from airflow_pytest_plugin.web import create_app

    fastapi = pytest.importorskip("fastapi")
    del fastapi
    from fastapi.testclient import TestClient

    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        history=db.history_store(),
        history_days=history_days,
    )
    return TestClient(
        create_app(
            FileSystemReportSource(report_root=reports_root),
            authorizer=lambda dag, u: True,
            read_authorizer=lambda dag, u: True,
            user_dependency=lambda: user,
            assistant=runtime,
        )
    )


def test_history_endpoint_returns_only_the_callers_transcript(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    alice = _history_client(reports_root, user={"username": "alice"})
    bob = _history_client(reports_root, user={"username": "bob"})

    alice.post("/api/assistant/query", json={"question": "alice asks"})
    bob.post("/api/assistant/query", json={"question": "bob asks"})

    body = alice.get("/api/assistant/history").json()
    assert body["available"] is True
    assert [item["role"] for item in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "alice asks"
    assert "bob" not in str(body)

    other = bob.get("/api/assistant/history").json()
    assert other["messages"][0]["content"] == "bob asks"


def test_history_survives_a_new_browser_and_a_new_server(reports_root):
    """The point of server-side history: it is not tied to one tab."""
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    _history_client(reports_root, user={"username": "alice"}).post(
        "/api/assistant/query", json={"question": "remember me"}
    )

    fresh = _history_client(reports_root, user={"username": "alice"})

    messages = fresh.get("/api/assistant/history").json()["messages"]
    assert messages[0]["content"] == "remember me"


def test_deleting_history_removes_only_the_callers_rows(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    alice = _history_client(reports_root, user={"username": "alice"})
    bob = _history_client(reports_root, user={"username": "bob"})
    alice.post("/api/assistant/query", json={"question": "alice asks"})
    bob.post("/api/assistant/query", json={"question": "bob asks"})

    response = alice.delete("/api/assistant/history")

    assert response.status_code == 200 and response.json()["removed"] == 2
    assert alice.get("/api/assistant/history").json()["messages"] == []
    assert bob.get("/api/assistant/history").json()["messages"] != []


def test_history_is_unavailable_when_switched_off(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"}, history_days=0)

    client.post("/api/assistant/query", json={"question": "not stored"})

    body = client.get("/api/assistant/history").json()
    assert body["available"] is False and body["messages"] == []
    assert client.get("/api/assistant/status").json()["history_server_side"] is False


def test_status_announces_server_side_history(reports_root):
    db.upgrade()
    body = (
        _history_client(reports_root, user={"username": "alice"})
        .get("/api/assistant/status")
        .json()
    )

    assert body["history_server_side"] is True and body["history_days"] == 30


def test_the_stored_answer_never_carries_the_report_evidence(reports_root):
    """Tracebacks and captured output must not land in the database."""
    db.upgrade()
    write_report_xml(
        reports_root,
        ReportRef("dag", "run", "task", 1),
        '<?xml version="1.0"?><testsuites><testsuite name="p" tests="1" failures="1" '
        'errors="0" skipped="0" time="0.1">'
        '<testcase classname="tests/test_a.py" name="test_x" time="0.1">'
        "<failure message='boom'>AssertionError: super-secret-trace</failure>"
        "</testcase></testsuite></testsuites>",
        summary={"total": 1, "failed": 1},
    )
    client = _history_client(reports_root, user={"username": "alice"})

    client.post("/api/assistant/query", json={"question": "what failed?"})

    assert "super-secret-trace" not in str(client.get("/api/assistant/history").json())


def test_a_connection_id_resolves_through_airflows_secrets_backend(monkeypatch):
    """Credentials belong in Airflow's secrets backend, not in our environment."""
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.setenv(db.DB_CONN_ID_ENV, "pytest_assistant_db")
    asked: list[str] = []

    class Connection:
        @staticmethod
        def get_connection_from_secrets(conn_id: str):
            asked.append(conn_id)
            return SimpleNamespace(
                get_uri=lambda: "postgres://svc:s3cret@db.internal:5432/assistant"
            )

    module = ModuleType("airflow.models")
    module.Connection = Connection
    monkeypatch.setitem(sys.modules, "airflow.models", module)
    db.reset_engine()

    url = db.configured_url()

    assert asked == ["pytest_assistant_db"]
    # Airflow emits the legacy 'postgres' scheme; SQLAlchemy 2 only accepts 'postgresql'.
    assert url == "postgresql://svc:s3cret@db.internal:5432/assistant"
    # And the password never reaches a status payload or a log line.
    assert db.status()["url"] == "postgresql://db.internal:5432/assistant"


def test_an_explicit_url_wins_over_a_connection_id(monkeypatch, tmp_path):
    # An absolute path: a relative one resolves against the working directory and drops a
    # stray database file in whatever directory the suite was started from.
    url = f"sqlite:///{tmp_path / 'explicit.db'}"
    monkeypatch.setenv(db.DB_URL_ENV, url)
    monkeypatch.setenv(db.DB_CONN_ID_ENV, "ignored")
    db.reset_engine()

    assert db.configured_url() == url


def test_an_unresolvable_connection_id_is_reported_not_guessed(monkeypatch, capsys):
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.setenv(db.DB_CONN_ID_ENV, "missing_conn")
    monkeypatch.setattr(db, "_airflow_url", lambda: "sqlite:///airflow-metadata.db")
    module = ModuleType("airflow.models")

    class Connection:
        @staticmethod
        def get_connection_from_secrets(conn_id: str):
            raise KeyError(conn_id)

    module.Connection = Connection
    monkeypatch.setitem(sys.modules, "airflow.models", module)
    db.reset_engine()

    # It must not silently fall through to Airflow's own database: the operator asked for
    # a specific one, and quietly writing somewhere else is worse than refusing.
    assert db.configured_url() is None
    assert db.main(["status"]) == 1
    assert db.DB_CONN_ID_ENV in capsys.readouterr().out


def test_airflows_configured_database_is_used_when_nothing_is_overridden(monkeypatch):
    """The default path: whatever AIRFLOW__DATABASE__SQL_ALCHEMY_CONN resolves to."""
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.delenv(db.DB_CONN_ID_ENV, raising=False)
    module = ModuleType("airflow.configuration")
    module.conf = SimpleNamespace(
        get=lambda section, key, **kw: (
            "postgresql://airflow:airflow@postgres/airflow"
            if (section, key) == ("database", "sql_alchemy_conn")
            else None
        )
    )
    monkeypatch.setitem(sys.modules, "airflow.configuration", module)
    db.reset_engine()

    assert db.configured_url() == "postgresql://airflow:airflow@postgres/airflow"
    # Credentials are stripped everywhere they could be printed.
    assert db.status()["url"] == "postgresql://postgres/airflow"


def test_an_unreadable_airflow_config_explains_itself(monkeypatch, capsys):
    """ "No database configured" would be a lie when Airflow's own lookup blew up."""
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.delenv(db.DB_CONN_ID_ENV, raising=False)
    module = ModuleType("airflow.configuration")

    def explode(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'psycopg2'")

    module.conf = SimpleNamespace(get=explode)
    monkeypatch.setitem(sys.modules, "airflow.configuration", module)
    monkeypatch.setitem(sys.modules, "airflow.settings", ModuleType("airflow.settings"))
    db.reset_engine()

    assert db.configured_url() is None
    state = db.status()
    assert state["configured"] is False
    assert "psycopg2" in (state["reason"] or "")

    assert db.main(["status"]) == 1
    assert "psycopg2" in capsys.readouterr().out


def test_status_distinguishes_an_unreachable_database_from_missing_tables(
    monkeypatch, capsys
):
    """ "Reachable but not initialised" must not be printed when nothing was reached."""
    monkeypatch.setenv(
        db.DB_URL_ENV, "postgresql://airflow:airflow@nonexistent-host-xyz:5432/airflow"
    )
    db.reset_engine()

    state = db.status()

    assert state["configured"] is True
    assert state["reachable"] is False and state["ready"] is False
    assert state["reason"]

    assert db.main(["status"]) == 1
    output = capsys.readouterr().out
    assert "could not be reached" in output
    assert "not initialised" not in output
    # The password never appears, even in a connection error.
    assert "airflow:airflow" not in output


def test_status_says_initialised_is_missing_when_the_database_answers(tmp_path):
    """A reachable database with no tables is a different, actionable state."""
    state = db.status()

    assert state["configured"] is True and state["reachable"] is True
    assert state["ready"] is False and state["reason"] is None


def test_the_anonymous_sentinel_matches_the_one_identities_are_built_with():
    """If these drift, an unidentified user silently gains a stored transcript."""
    from airflow_pytest_plugin.assistant import audit

    assert db.ANONYMOUS_PRINCIPAL == audit.ANONYMOUS


def test_rate_counter_is_shared_between_workers():
    """Two API-server processes must not each grant a full allowance."""
    db.upgrade()
    store = db.rate_store()

    assert store.spent("alice", 4_100) == 0
    store.charge("alice", 4_100)
    store.charge("alice", 4_100)

    assert db.rate_store().spent("alice", 4_100) == 2
    assert store.spent("alice", 4_101) == 0, "a new window starts empty"
    assert store.spent("bob", 4_100) == 0, "another principal is unaffected"


def test_rate_counter_survives_concurrent_writers():
    db.upgrade()
    store = db.rate_store()

    def hit(_):
        db.rate_store().charge("alice", 7_000)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(hit, range(80)))

    assert store.spent("alice", 7_000) == 80


def test_rate_counter_is_unavailable_without_the_tables():
    store = db.rate_store()

    assert store.available is False
    assert store.spent("alice", 1) == 0
    store.charge("alice", 1)  # must not raise


def test_purging_drops_stale_rate_windows_but_keeps_the_live_one():
    db.upgrade()
    store = db.rate_store()
    store.charge("alice", 100)
    store.charge("alice", 101)

    removed = db.purge_rate_windows(before=101)

    assert removed == 1
    assert store.spent("alice", 100) == 0
    assert store.spent("alice", 101) == 1


def test_old_rate_windows_are_swept_without_an_operator(reports_root):
    """Every question writes a rate row; nothing else would ever delete them."""
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    store = db.rate_store()
    for window in range(1_000, 1_010):
        store.charge("ancient", window)
    assert store.spent("ancient", 1_000) == 1

    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        rate_limit=60,
        rate_window_seconds=3_600.0,
        rate_store=store,
    )
    runtime.ask(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, user: True,
        user={"username": "alice"},
        query=AssistantQuery(question="What failed?"),
    )

    assert store.spent("ancient", 1_000) == 0, "stale windows must not accumulate"


def test_the_first_sweep_does_not_wait_for_the_host_to_have_been_up_an_hour(
    reports_root,
):
    """The hour is a rate limit on sweeping, not a delay before the first one.

    ``time.monotonic()`` counts from boot, so comparing it against a zero start meant a
    freshly booted API server swept nothing for its first hour -- and made this suite pass
    or fail on how long the developer's machine had been awake.
    """
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    store = db.rate_store()
    store.charge("ancient", 1_000)

    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        rate_limit=60,
        rate_window_seconds=3_600.0,
        rate_store=store,
    )
    ticks = iter([12.0, 13.0, 14.0])
    runtime._clock = lambda: next(ticks)  # a host that booted twelve seconds ago

    runtime.ask(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, user: True,
        user={"username": "alice"},
        query=AssistantQuery(question="What failed?"),
    )

    assert store.spent("ancient", 1_000) == 0


def test_the_cli_purge_also_sweeps_rate_windows():
    db.upgrade()
    db.rate_store().charge("alice", 1)

    db.main(["purge"])

    assert db.rate_store().spent("alice", 1) == 0


def _record_version(version: int) -> None:
    """Pretend the database was created by an older build of the plugin."""
    from sqlalchemy import update

    active = db.engine()
    schema = db.METADATA.tables[db.SCHEMA_TABLE]
    with active.begin() as connection:
        connection.execute(update(schema).values(version=version))


def test_a_database_from_an_older_build_does_not_claim_features_it_lacks():
    """A v2 database has no rate table; reporting the limit as shared would be a lie."""
    db.upgrade()
    _record_version(2)

    assert db.rate_store().available is False
    assert db.history_store().available is True, "history existed at version 2"
    assert db.quota_store().available is True


def test_status_tells_an_operator_that_an_upgrade_is_due():
    db.upgrade()
    _record_version(2)

    state = db.status()

    assert state["ready"] is False
    assert state["version"] == 2 and state["expected_version"] == db.SCHEMA_VERSION


def test_the_cli_asks_for_the_upgrade_it_needs(capsys):
    db.upgrade()
    _record_version(2)

    code = db.main(["status"])

    printed = capsys.readouterr().out
    assert code == 1
    assert "upgrade" in printed and "2" in printed


def test_messages_belong_to_a_named_conversation():
    db.upgrade()
    store = db.history_store()

    store.append("alice", "first q", "first a", [], 1, conversation="chat-1")
    store.append("alice", "second q", "second a", [], 1, conversation="chat-2")

    one = store.load("alice", limit=12, conversation="chat-1")
    two = store.load("alice", limit=12, conversation="chat-2")

    assert [m["content"] for m in one] == ["first q", "first a"]
    assert [m["content"] for m in two] == ["second q", "second a"]


def test_conversations_are_listed_newest_first_with_a_title():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "why is etl_daily red?", "because…", [], 1, conversation="a")
    store.append("alice", "and the slow test?", "because…", [], 1, conversation="b")

    listed = store.conversations("alice", limit=10)

    assert [item["id"] for item in listed] == ["b", "a"]
    assert listed[1]["title"] == "why is etl_daily red?"
    assert listed[0]["messages"] == 2


def test_a_derived_title_is_bounded_like_a_chosen_one():
    """The chat list is a sidebar of one-line labels, not a copy of the questions.

    A title the user types is normalised and clipped; a title derived from the opening
    question was neither, so a chat list of long questions came back as 142 KiB of JSON
    for twenty rows the panel renders forty characters of -- on the endpoint every
    opened panel and every cross-tab signal hits.
    """
    db.upgrade()
    store = db.history_store()
    store.append("alice", "почему " * 800, "ответ", [], 1, conversation="long")
    store.append(
        "alice", "первая строка\nвторая\tстрока", "ответ", [], 1, conversation="lines"
    )

    listed = {
        item["id"]: item["title"] for item in store.conversations("alice", limit=10)
    }

    assert len(listed["long"]) <= db.MAX_TITLE
    assert listed["long"].startswith("почему почему")
    assert listed["lines"] == "первая строка вторая строка"


def test_one_user_cannot_read_or_delete_another_conversation():
    """Guessing an id must not be enough: rows are filtered by principal as well."""
    db.upgrade()
    store = db.history_store()
    store.append("alice", "private", "secret", [], 1, conversation="shared-id")

    assert store.load("mallory", limit=12, conversation="shared-id") == []
    assert store.clear("mallory", conversation="shared-id") == 0
    assert store.conversations("mallory", limit=10) == []
    assert len(store.load("alice", limit=12, conversation="shared-id")) == 2


def test_clearing_one_conversation_keeps_the_others():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q1", "a1", [], 1, conversation="keep")
    store.append("alice", "q2", "a2", [], 1, conversation="drop")

    removed = store.clear("alice", conversation="drop")

    assert removed == 2
    assert len(store.load("alice", limit=12, conversation="keep")) == 2
    assert [item["id"] for item in store.conversations("alice", limit=10)] == ["keep"]


def test_clearing_without_a_conversation_still_removes_everything():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q1", "a1", [], 1, conversation="one")
    store.append("alice", "q2", "a2", [], 1, conversation="two")

    assert store.clear("alice") == 4
    assert store.conversations("alice", limit=10) == []


def test_the_conversation_list_is_bounded():
    """A user who never deletes must not turn the picker into an unbounded query."""
    db.upgrade()
    store = db.history_store()
    for index in range(40):
        store.append("alice", f"q{index}", "a", [], 1, conversation=f"chat-{index:02d}")

    listed = store.conversations("alice", limit=10)

    assert len(listed) == 10
    assert listed[0]["id"] == "chat-39"


@pytest.mark.parametrize(
    "given",
    [
        "../../etc/passwd",
        "' OR 1=1 --",
        "<script>x</script>",
        "!!!",
        "a" * 200,
        "\u0000\u0007",
        "chat\nid",
    ],
)
def test_a_browser_supplied_conversation_id_is_never_trusted(given):
    """Whatever arrives, what is stored is a short token of safe characters."""
    cleaned = db.clean_conversation(given)

    assert re.fullmatch(r"[A-Za-z0-9._~-]{1,64}", cleaned), cleaned
    assert db.clean_conversation(given) == cleaned, "and it is stable"


def test_a_hostile_conversation_id_cannot_reach_another_principal():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "private", "secret", [], 1, conversation="alice-chat")

    store.append("mallory", "probe", "answer", [], 1, conversation="' OR 1=1 --")

    assert "private" not in str(store.load("mallory", limit=12))
    assert store.clear("mallory") == 2, "only mallory's own two rows"
    assert len(store.load("alice", limit=12, conversation="alice-chat")) == 2


def test_the_api_keeps_separate_chats_for_one_user(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})

    client.post(
        "/api/assistant/query", json={"question": "why red?", "conversation": "work"}
    )
    client.post(
        "/api/assistant/query", json={"question": "why slow?", "conversation": "perf"}
    )

    work = client.get("/api/assistant/history", params={"conversation": "work"}).json()
    perf = client.get("/api/assistant/history", params={"conversation": "perf"}).json()

    assert work["messages"][0]["content"] == "why red?"
    assert perf["messages"][0]["content"] == "why slow?"
    assert [item["id"] for item in work["conversations"]] == ["perf", "work"]
    assert work["conversations"][1]["title"] == "why red?"


def test_opening_the_panel_lands_on_the_newest_chat(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})
    client.post("/api/assistant/query", json={"question": "old", "conversation": "a"})
    client.post("/api/assistant/query", json={"question": "new", "conversation": "b"})

    body = client.get("/api/assistant/history").json()

    assert body["conversation"] == "b"
    assert body["messages"][0]["content"] == "new"


def test_deleting_one_chat_leaves_the_others(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})
    client.post("/api/assistant/query", json={"question": "keep", "conversation": "a"})
    client.post("/api/assistant/query", json={"question": "drop", "conversation": "b"})

    response = client.delete("/api/assistant/history", params={"conversation": "b"})

    assert response.json()["removed"] == 2
    remaining = client.get("/api/assistant/history").json()
    assert [item["id"] for item in remaining["conversations"]] == ["a"]
    assert remaining["messages"][0]["content"] == "keep"


def test_a_chat_id_belonging_to_someone_else_returns_nothing(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    alice = _history_client(reports_root, user={"username": "alice"})
    mallory = _history_client(reports_root, user={"username": "mallory"})
    alice.post(
        "/api/assistant/query", json={"question": "private", "conversation": "secret"}
    )

    stolen = mallory.get(
        "/api/assistant/history", params={"conversation": "secret"}
    ).json()

    assert stolen["messages"] == [] and stolen["conversations"] == []
    assert (
        mallory.delete(
            "/api/assistant/history", params={"conversation": "secret"}
        ).json()["removed"]
        == 0
    )
    assert len(alice.get("/api/assistant/history").json()["messages"]) == 2


def test_restored_history_hides_evidence_for_dags_since_revoked(reports_root):
    """Permissions change after an answer is stored.

    The transcript keeps `[R1]` links naming DAG, task and run. Replaying them to a user
    who has since lost access hands back report identifiers they may no longer read -- and
    gives them buttons that will only 403.
    """
    db.upgrade()
    write_report(reports_root, ReportRef("secret_dag", "run", "task", 1), failed=1)
    allowed = {"value": True}

    from airflow_pytest_plugin.web import create_app

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        history=db.history_store(),
        history_days=30,
    )
    client = TestClient(
        create_app(
            FileSystemReportSource(report_root=reports_root),
            authorizer=lambda dag, u: True,
            read_authorizer=lambda dag, u: allowed["value"],
            user_dependency=lambda: {"username": "alice"},
            assistant=runtime,
        )
    )
    client.post("/api/assistant/query", json={"question": "what failed?"})
    stored = client.get("/api/assistant/history").json()
    assert "secret_dag" in str(stored), "the link was stored while access was allowed"

    allowed["value"] = False

    body = client.get("/api/assistant/history").json()

    assert "secret_dag" not in str(body), "a revoked DAG must not come back in history"
    assert body["messages"], "the conversation itself is still the user's own"


def test_a_secret_typed_into_a_question_is_not_persisted_verbatim(
    reports_root, monkeypatch
):
    """Redaction keeps server secrets out of what leaves the process.

    The stored transcript is the one place a value the model was never allowed to see
    would survive: the question is written to Airflow's metadata database and replayed
    for thirty days. What is too sensitive to send is too sensitive to keep.
    """
    monkeypatch.setenv("PROD_API_TOKEN", "sk-live-9f3c2b7a1d0e4f5a6b8c")
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})

    client.post(
        "/api/assistant/query",
        json={"question": "why does sk-live-9f3c2b7a1d0e4f5a6b8c fail?"},
    )

    stored = client.get("/api/assistant/history").json()
    assert "sk-live-9f3c2b7a1d0e4f5a6b8c" not in str(stored)


def test_a_deployment_without_authentication_gets_no_shared_transcript():
    """With no auth manager every visitor is the same principal.

    That is the same argument that already denies storage to an unidentifiable user:
    several real people collapse onto one identity, and a shared transcript there is a
    cross-account leak. "standalone" is that case, not an exemption from it.
    """
    store = db.history_store()

    assert store.storable("standalone") is False
    assert store.storable(db.ANONYMOUS_PRINCIPAL) is False
    assert store.storable("alice") is True


def test_history_is_not_written_for_a_standalone_viewer(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user=None)

    client.post("/api/assistant/query", json={"question": "not stored"})

    body = client.get("/api/assistant/history").json()
    assert body["available"] is False and body["messages"] == []


def test_status_does_not_promise_saved_chats_to_a_viewer_who_cannot_own_them(
    reports_root,
):
    """The Chats button appears from this flag; promising it to a standalone viewer gives
    them a list that can only ever be empty."""
    db.upgrade()
    named = _history_client(reports_root, user={"username": "alice"})
    anonymous = _history_client(reports_root, user=None)

    assert named.get("/api/assistant/status").json()["history_server_side"] is True
    assert anonymous.get("/api/assistant/status").json()["history_server_side"] is False


def test_a_streamed_answer_is_stored_like_a_blocking_one(reports_root):
    """The browser only ever uses /stream; /query is for API clients.

    If storage rode on the blocking path alone, server-side history would be dead in the
    product while every test that posts to /query kept passing.
    """
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})

    response = client.post(
        "/api/assistant/stream", json={"question": "what failed?", "conversation": "c1"}
    )
    assert response.status_code == 200

    body = client.get("/api/assistant/history", params={"conversation": "c1"}).json()
    assert [item["role"] for item in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "what failed?"


def test_a_streamed_answer_the_browser_stops_reading_is_still_stored(reports_root):
    """A browser closes the connection as soon as it sees `done`."""
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})

    with client.stream(
        "POST",
        "/api/assistant/stream",
        json={"question": "read then leave", "conversation": "c2"},
    ) as live:
        for line in live.iter_lines():
            if "event: done" in line:
                break

    body = client.get("/api/assistant/history", params={"conversation": "c2"}).json()
    assert body["messages"], "the completed exchange must survive an early disconnect"


def test_doctor_names_the_first_broken_precondition(capsys, monkeypatch):
    """ "Nothing is written" has five possible causes; an operator needs to be told which."""
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.setenv(db.DB_URL_ENV, "postgresql://user:pw@nowhere.invalid:5432/db")
    db.reset_engine()

    code = db.main(["doctor"])

    printed = capsys.readouterr().out
    assert code == 1
    assert "could not be reached" in printed
    assert "pw" not in printed and "user:pw" not in printed


def test_doctor_reports_uninitialised_tables():
    assert db.main(["doctor"]) == 1


def test_doctor_confirms_a_working_setup(capsys, monkeypatch):
    db.upgrade()
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS", "30")

    code = db.main(["doctor"])

    printed = capsys.readouterr().out
    assert code == 0, printed
    assert "wrote and read back" in printed
    assert "30 day" in printed


def test_doctor_says_when_history_is_switched_off(capsys, monkeypatch):
    db.upgrade()
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS", "0")

    code = db.main(["doctor"])

    printed = capsys.readouterr().out
    assert code == 1
    assert "HISTORY_DAYS" in printed


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (None, "off: no Fernet key"),
        ("please-encrypt-my-chat", "cannot be used"),
    ],
)
def test_doctor_says_what_encryption_is_doing(key, expected, capsys, monkeypatch):
    """A mistyped key was invisible in the one command built to explain a broken setup.

    Nothing else surfaces it either: the transcript quietly falls back to plain text and
    the only trace is one warning in the API server's log, which is not where anyone
    looks when the question is "is our chat encrypted?".
    """
    from airflow_pytest_plugin import chatcrypto

    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)
    if key is not None:
        monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", key)
    chatcrypto._cached = None
    db.upgrade()

    assert db.main(["doctor"]) == 0
    printed = capsys.readouterr().out

    assert "Encryption" in printed
    assert expected in printed


def test_status_reports_encryption(capsys, monkeypatch):
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    chatcrypto._cached = None
    db.upgrade()

    db.main(["status"])

    assert "Encryption: on" in capsys.readouterr().out


def test_rotate_key_states_the_ordering_that_makes_it_safe(capsys, monkeypatch):
    """The one hazard the command cannot detect, so it has to name it.

    Run before the API servers restart on the new key and a server still writing with the
    old one keeps inserting rows behind the walking cursor. Those rows read perfectly
    while the old key is listed -- so the command cannot tell them from rows it has
    already moved, and reports a clean pass -- and then die at the step where the
    operator drops the old key, exactly as the procedure tells them to.

    Nothing in the database distinguishes the two cases, so the output has to carry the
    rule: restart first, and re-run this afterwards.
    """
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    chatcrypto._cached = None
    db.upgrade()
    db.history_store().append("id:1", "вопрос", "ответ", [], 1, conversation="c")

    assert db.main(["rotate-key"]) == 0

    printed = capsys.readouterr().out
    assert "restarted with the new key" in printed, printed
    assert "Re-running" in printed, printed


def test_the_cli_rotates_the_key(capsys, monkeypatch):
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", old_key)
    chatcrypto._cached = None
    db.upgrade()
    db.history_store().append("id:1", "вопрос", "ответ", [], 1, conversation="c")

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", f"{new_key},{old_key}")
    chatcrypto._cached = None
    code = db.main(["rotate-key"])

    printed = capsys.readouterr().out
    assert code == 0, printed
    assert "Re-encrypted 2 message(s)" in printed

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", new_key)
    chatcrypto._cached = None
    assert [
        item["content"]
        for item in db.history_store().load("id:1", limit=5, conversation="c")
    ] == ["вопрос", "ответ"]


def test_the_cli_refuses_to_rotate_onto_an_unusable_key(capsys, monkeypatch):
    """Rotating with a broken key would silently write the whole table in plain text."""
    from airflow_pytest_plugin import chatcrypto

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", "please-encrypt-my-chat")
    chatcrypto._cached = None
    db.upgrade()

    code = db.main(["rotate-key"])

    printed = capsys.readouterr().out
    assert code == 1
    assert "cannot be used" in printed


def test_the_cli_says_out_loud_when_rotation_writes_plain_text(capsys, monkeypatch):
    from airflow_pytest_plugin import chatcrypto

    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)
    chatcrypto._cached = None
    db.upgrade()
    db.history_store().append("id:1", "вопрос", "ответ", [], 1, conversation="c")

    assert db.main(["rotate-key"]) == 0

    printed = capsys.readouterr().out
    assert "PLAIN TEXT" in printed
    assert "Rewrote in plain text 2 message(s)" in printed


def test_doctor_leaves_no_probe_rows_behind():
    db.upgrade()

    db.main(["doctor"])

    store = db.history_store()
    assert store.conversations("airflow-pytest-plugin-doctor", limit=10) == []


def test_switching_history_off_still_lets_an_operator_purge_what_was_stored():
    """Retention must not become "kept forever" the moment the feature is turned off.

    Rows written while history was on outlive it: the CLI is the only way to remove them,
    and it used to refuse to run at all once HISTORY_DAYS was 0.
    """
    db.upgrade()
    store = db.history_store()
    store.append("alice", "written while it was on", "answer", [], 0)

    code = db.main(["purge", "--history-days", "0"])

    assert code == 0
    assert store.load("alice", limit=12) == []


def test_purge_keeps_a_message_exactly_at_the_retention_boundary():
    """Off by one here silently deletes a day of everyone's chats."""
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q", "a", [], 0)
    now = datetime.now(timezone.utc)

    assert db.purge_history(before=now - timedelta(seconds=1)) == 0
    assert len(store.load("alice", limit=12)) == 2

    assert db.purge_history(before=now + timedelta(seconds=1)) == 2
    assert store.load("alice", limit=12) == []


def test_purge_without_a_flag_reports_rows_left_by_a_disabled_feature(
    capsys, monkeypatch
):
    """Deleting them unasked would be worse; saying nothing is what stranded them."""
    db.upgrade()
    db.history_store().append("alice", "q", "a", [], 0)
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS", "0")

    code = db.main(["purge"])

    printed = capsys.readouterr().out
    assert code == 0
    assert "2 message(s)" in printed and "--history-days 0" in printed
    assert db.history_store().load("alice", limit=12) != [], "nothing deleted unasked"


def test_two_different_chat_ids_do_not_collapse_into_one():
    """Sanitising strips characters, so distinct ids can arrive at the same string.

    The browser only ever sends safe ids, but an API client is not the browser, and two
    of its chats merging into one is the same silent data mix-up as a shared principal.
    """
    assert db.clean_conversation("work!") != db.clean_conversation("work?")
    assert db.clean_conversation("a/b") != db.clean_conversation("a\\b")
    # Anything that sanitises away entirely must not land in the default bucket either.
    assert db.clean_conversation("!!!") != db.DEFAULT_CONVERSATION
    assert db.clean_conversation("###") != db.clean_conversation("!!!")


def test_a_clean_id_is_left_exactly_as_it_arrived():
    """The common case must stay readable: the browser's own ids are already safe."""
    for value in ("main", "c1a2b3", "work-2026", "Chat_1.2"):
        assert db.clean_conversation(value) == value


def test_the_default_bucket_is_still_used_when_nothing_was_named():
    assert db.clean_conversation("") == db.DEFAULT_CONVERSATION
    assert db.clean_conversation(None) == db.DEFAULT_CONVERSATION
    assert db.clean_conversation("   ") == db.DEFAULT_CONVERSATION


def _downgrade_to_version_2() -> None:
    """Reshape a current database into what schema 2 actually looked like."""
    from sqlalchemy import text, update

    active = db.engine()
    with active.begin() as connection:
        # The index has to go first: a column an index depends on cannot be dropped.
        connection.execute(
            text(f"DROP INDEX IF EXISTS ix_{db.MESSAGE_TABLE}_principal_chat_id")
        )
        connection.execute(
            text(f"ALTER TABLE {db.MESSAGE_TABLE} DROP COLUMN conversation")
        )
        connection.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_{db.MESSAGE_TABLE}_principal_id "
                f"ON {db.MESSAGE_TABLE} (principal, id)"
            )
        )
        connection.execute(text(f"DROP TABLE IF EXISTS {db.RATE_TABLE}"))
        connection.execute(
            update(db.METADATA.tables[db.SCHEMA_TABLE]).values(version=2)
        )
    db.reset_engine()


def test_upgrading_an_older_database_adds_the_column_it_is_missing():
    """``create_all`` creates missing *tables*; it never alters an existing one.

    A database created by schema 2 therefore kept a message table with no ``conversation``
    column while the version row was updated to 3 -- so every insert failed, the failure
    was swallowed as "history is a convenience", and chats silently stopped being saved.
    """
    db.upgrade()
    db.history_store().append("alice", "written at v2", "answer", [], 0)
    _downgrade_to_version_2()

    result = db.upgrade()

    assert result["version"] == db.SCHEMA_VERSION
    store = db.history_store()
    store.append("alice", "written after the upgrade", "answer", [], 0)
    contents = [item["content"] for item in store.load("alice", limit=12)]
    assert "written after the upgrade" in contents
    assert "written at v2" in contents, "existing rows must survive the migration"


def test_the_migrated_rows_land_in_the_default_conversation():
    """Chats written before the column existed still have to be readable."""
    db.upgrade()
    db.history_store().append("alice", "old chat", "answer", [], 0)
    _downgrade_to_version_2()
    db.upgrade()

    listed = db.history_store().conversations("alice", limit=10)

    assert [item["id"] for item in listed] == [db.DEFAULT_CONVERSATION]


def test_upgrade_refuses_to_record_a_version_the_tables_do_not_match():
    """The recorded number is what every readiness check trusts.

    Recording 3 over a table that is still shaped like 2 is what made this invisible.
    """
    db.upgrade()
    _downgrade_to_version_2()
    from unittest.mock import patch

    with patch.object(db, "_MIGRATIONS", {}):
        with pytest.raises(RuntimeError, match="conversation"):
            db.upgrade()

    assert db.recorded_version() == 2, "the version must not move past the schema"


def test_doctor_catches_a_table_that_does_not_match_its_version(capsys):
    db.upgrade()
    _downgrade_to_version_2()
    from sqlalchemy import update

    active = db.engine()
    with active.begin() as connection:
        connection.execute(
            update(db.METADATA.tables[db.SCHEMA_TABLE]).values(
                version=db.SCHEMA_VERSION
            )
        )
    db.reset_engine()

    code = db.main(["doctor"])

    printed = capsys.readouterr().out
    assert code == 1
    assert "conversation" in printed and "upgrade" in printed


def test_upgrade_can_run_on_every_start_without_losing_anything():
    """The command is wired into a container start, so it runs on every deploy."""
    db.upgrade()
    store = db.history_store()
    store.append("alice", "chat from build 1", "answer", [], 0, conversation="work")

    for _ in range(10):
        result = db.upgrade()
        assert result["version"] == db.SCHEMA_VERSION

    contents = [
        item["content"] for item in store.load("alice", limit=12, conversation="work")
    ]
    assert "chat from build 1" in contents
    assert [item["id"] for item in store.conversations("alice", limit=10)] == ["work"]


def test_two_containers_starting_at_once_do_not_break_each_other():
    """Replicas start together, and each start runs `db upgrade`.

    Both read the same old version and both try the same migration; if the loser raises,
    its `&&` chain aborts and that replica never starts Airflow at all.
    """
    db.upgrade()
    db.history_store().append("alice", "written before", "answer", [], 0)
    _downgrade_to_version_2()

    results: list[object] = []

    def upgrade_now(_):
        try:
            results.append(db.upgrade())
        except Exception as error:  # noqa: BLE001 - the failure is what is under test
            results.append(error)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(upgrade_now, range(4)))

    failures = [item for item in results if isinstance(item, Exception)]
    assert failures == [], f"a concurrent start failed: {failures}"
    assert db.recorded_version() == db.SCHEMA_VERSION
    contents = [item["content"] for item in db.history_store().load("alice", limit=12)]
    assert "written before" in contents


def test_upgrade_repairs_a_schema_whose_recorded_version_is_already_current():
    """The exact state the earlier broken build left behind.

    That build wrote version 3 over a table it had not altered, so the recorded number is
    already current while the column is missing. Keying migrations off "recorded < target"
    then skips the repair and the upgrade only reports the damage instead of fixing it --
    on a container start-up chain, that is a replica that never boots.
    """
    db.upgrade()
    db.history_store().append("alice", "written before the break", "answer", [], 0)
    _downgrade_to_version_2()
    from sqlalchemy import update

    with db.engine().begin() as connection:
        connection.execute(
            update(db.METADATA.tables[db.SCHEMA_TABLE]).values(
                version=db.SCHEMA_VERSION
            )
        )
    db.reset_engine()
    assert db.recorded_version() == db.SCHEMA_VERSION, "version says current"

    result = db.upgrade()

    assert result["version"] == db.SCHEMA_VERSION
    store = db.history_store()
    store.append("alice", "written after the repair", "answer", [], 0)
    contents = [item["content"] for item in store.load("alice", limit=12)]
    assert "written after the repair" in contents
    assert "written before the break" in contents


def test_the_tables_are_created_whether_or_not_a_provider_is_configured(monkeypatch):
    """`db upgrade` is an operator command, not part of the feature.

    Setting the database up before choosing a provider has to work: the two are separate
    decisions, and the tables are empty and harmless until something writes to them.
    """
    monkeypatch.delenv("AIRFLOW_PYTEST_ASSISTANT_PROVIDER", raising=False)

    result = db.upgrade()

    assert result["version"] == db.SCHEMA_VERSION
    assert db.status()["ready"] is True
    assert set(db.METADATA.tables) >= {
        db.MESSAGE_TABLE,
        db.USAGE_TABLE,
        db.RATE_TABLE,
        db.SCHEMA_TABLE,
    }


def test_without_a_provider_the_plugin_never_touches_the_database(monkeypatch):
    """No provider means no feature, so nothing should open a connection for it.

    An empty schema is fine; a viewer that connects to Airflow's metadata database on
    every start-up for a feature nobody enabled is not.
    """
    monkeypatch.delenv("AIRFLOW_PYTEST_ASSISTANT_PROVIDER", raising=False)
    touched: list[str] = []
    monkeypatch.setattr(
        db, "history_store", lambda: touched.append("history") or object()
    )
    monkeypatch.setattr(db, "quota_store", lambda: touched.append("quota") or object())
    monkeypatch.setattr(db, "rate_store", lambda: touched.append("rate") or object())

    from airflow_pytest_plugin.assistant import configured_assistant_runtime

    runtime = configured_assistant_runtime()

    assert runtime.configured is False and runtime.enabled is False
    assert touched == [], (
        f"the database was consulted for a disabled feature: {touched}"
    )


def test_a_connection_that_dies_between_requests_is_replaced_not_reported():
    """Pooled connections outlive an idle API server; a stale one must not fail a read."""
    db.upgrade()
    store = db.history_store()
    store.append("alice", "before", "answer", [], 0)

    # Every pooled connection is closed underneath the engine, the way a database restart
    # or an idle-timeout proxy does it.
    active = db.engine()
    active.dispose()

    assert [item["content"] for item in store.load("alice", limit=12)][0] == "before"
    store.append("alice", "after", "answer", [], 0)
    assert len(store.load("alice", limit=12)) == 4


def test_a_write_that_fails_leaves_no_half_written_exchange():
    """A question with no answer beside it is worse than no record of the exchange."""
    db.upgrade()
    store = db.history_store()

    long_enough_to_break_the_column = "x" * 200
    store.append("alice", "q", "a", [], 0, conversation=long_enough_to_break_the_column)

    rows = store.load("alice", limit=12, conversation=long_enough_to_break_the_column)
    assert len(rows) in (0, 2), f"a half-written exchange: {rows}"


def test_reads_never_take_a_write_lock_on_the_history_table():
    """Two readers and a writer at once must not serialise into a queue.

    SQLite in particular escalates a connection that has begun a transaction, so a read
    that opened `begin()` instead of `connect()` would block every other request.
    """
    db.upgrade()
    store = db.history_store()
    for index in range(50):
        store.append("alice", f"q{index}", "a", [], 0)

    errors: list[BaseException] = []

    def hammer(index: int) -> None:
        try:
            for _ in range(20):
                if index % 3 == 0:
                    db.history_store().append("bob", "q", "a", [], 0)
                else:
                    db.history_store().load("alice", limit=12)
        except BaseException as error:  # noqa: BLE001 - any failure is the finding
            errors.append(error)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(hammer, range(6)))

    assert errors == [], errors


def test_the_engine_is_built_once_and_shared():
    """A new engine per call would open a new pool per request."""
    db.upgrade()

    first = db.engine()
    second = db.engine()

    assert first is second


def test_resetting_the_engine_releases_the_old_pool():
    db.upgrade()
    first = db.engine()

    db.reset_engine()
    second = db.engine()

    assert first is not second
    assert db.status()["ready"] is True


def _break_the_message_table() -> None:
    """Make the table unusable while the recorded version still says it is fine.

    A dropped table is the blunt version. The same state arrives from a half-restored
    backup, a REVOKE on one table, or a search_path that no longer sees it -- and from a
    migration that did not run, which is how this was found in production.
    """
    from sqlalchemy import text

    with db.engine().begin() as connection:
        connection.execute(text(f"DROP TABLE {db.MESSAGE_TABLE}"))


def test_a_store_that_cannot_use_its_table_stops_claiming_it_can():
    """`available` decides whether the UI offers saved chats at all.

    Answering "yes" while every statement fails leaves the user with a chat list that is
    always empty and no hint that anything is wrong.
    """
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q", "a", [], 0)
    assert store.available is True

    _break_the_message_table()
    store.append("alice", "q2", "a2", [], 0)

    assert store.available is False


def test_the_history_endpoint_reports_the_outage(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})
    client.post("/api/assistant/query", json={"question": "stored fine"})

    _break_the_message_table()
    client.post("/api/assistant/query", json={"question": "not stored"})

    body = client.get("/api/assistant/history").json()
    assert body["available"] is False, body
    status = client.get("/api/assistant/status").json()
    assert status["history_server_side"] is False


def test_a_question_is_still_answered_while_storage_is_broken(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})
    _break_the_message_table()

    response = client.post("/api/assistant/query", json={"question": "what failed?"})

    assert response.status_code == 200 and response.json()["answer"]


def test_a_store_recovers_by_itself_once_the_table_is_back():
    """An outage must not need a restart to clear.

    The runtime holds one store for the life of the process, so it is *that* instance
    that has to come back -- not a fresh one built after someone notices.
    """
    db.upgrade()
    store = db.history_store()
    _break_the_message_table()
    store.append("alice", "q", "a", [], 0)
    assert store.available is False, "marked down while the table is unusable"

    db.reset_engine()
    db.upgrade()
    # Standing in for the cooldown lapsing, rather than sleeping through it.
    store.retry_after_seconds = 0.0

    assert store.available is True
    store.append("alice", "after", "answer", [], 0)
    assert [item["content"] for item in store.load("alice", limit=12)] == [
        "after",
        "answer",
    ]


def test_a_store_marked_down_stays_down_for_the_cooldown():
    """Retrying a broken table on every request turns one outage into a stampede."""
    db.upgrade()
    store = db.history_store()
    _break_the_message_table()
    store.append("alice", "q", "a", [], 0)

    assert store.available is False
    assert store.available is False, "and it does not flap back on the next call"


def test_the_quota_and_rate_stores_report_an_outage_too():
    db.upgrade()
    quota = db.quota_store()
    rate = db.rate_store()
    quota.charge("alice", 1, 10)
    rate.charge("alice", 1)
    assert quota.available is True and rate.available is True

    from sqlalchemy import text

    with db.engine().begin() as connection:
        connection.execute(text(f"DROP TABLE {db.USAGE_TABLE}"))
        connection.execute(text(f"DROP TABLE {db.RATE_TABLE}"))
    quota.charge("alice", 1, 10)
    rate.charge("alice", 1)

    assert quota.available is False
    assert rate.available is False


def test_a_chat_can_be_given_a_name_of_its_own():
    """The first question is a decent default and a poor label for a long conversation."""
    db.upgrade()
    store = db.history_store()
    store.append("alice", "why is etl_daily red?", "because…", [], 0, conversation="c1")

    store.rename("alice", "c1", "Friday incident")

    listed = store.conversations("alice", limit=10)
    assert [item["title"] for item in listed] == ["Friday incident"]


def test_clearing_a_name_falls_back_to_the_first_question():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "why is etl_daily red?", "because…", [], 0, conversation="c1")
    store.rename("alice", "c1", "Friday incident")

    store.rename("alice", "c1", "")

    assert store.conversations("alice", limit=10)[0]["title"] == "why is etl_daily red?"


def test_one_user_cannot_rename_another_chat():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "private", "secret", [], 0, conversation="shared-id")

    assert store.rename("mallory", "shared-id", "mine now") == 0

    assert store.conversations("alice", limit=10)[0]["title"] == "private"
    assert store.conversations("mallory", limit=10) == []


def test_a_name_is_bounded_and_never_stored_as_markup():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q", "a", [], 0, conversation="c1")

    store.rename("alice", "c1", "<script>x</script>" + "y" * 500)

    title = store.conversations("alice", limit=10)[0]["title"]
    assert len(title) <= 200
    assert title.startswith("<script>"), "stored verbatim; the UI is what escapes it"


def test_deleting_a_chat_takes_its_name_with_it():
    """Otherwise a new chat reusing the id would inherit a stranger's label."""
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q", "a", [], 0, conversation="c1")
    store.rename("alice", "c1", "Friday incident")

    store.clear("alice", conversation="c1")
    store.append("alice", "a new question", "answer", [], 0, conversation="c1")

    assert store.conversations("alice", limit=10)[0]["title"] == "a new question"


def test_upgrading_from_version_3_adds_the_name_table():
    db.upgrade()
    store = db.history_store()
    store.append("alice", "written at v3", "answer", [], 0, conversation="c1")
    from sqlalchemy import text, update

    with db.engine().begin() as connection:
        connection.execute(text(f"DROP TABLE {db.CONVERSATION_TABLE}"))
        connection.execute(
            update(db.METADATA.tables[db.SCHEMA_TABLE]).values(version=3)
        )
    db.reset_engine()

    db.upgrade()

    fresh = db.history_store()
    fresh.rename("alice", "c1", "Friday incident")
    assert fresh.conversations("alice", limit=10)[0]["title"] == "Friday incident"
    assert [
        item["content"] for item in fresh.load("alice", limit=12, conversation="c1")
    ][0] == "written at v3"


def test_the_api_renames_a_chat(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})
    client.post("/api/assistant/query", json={"question": "why?", "conversation": "c1"})

    response = client.patch(
        "/api/assistant/history",
        params={"conversation": "c1"},
        json={"title": "Friday incident"},
    )

    assert response.status_code == 200 and response.json()["renamed"] == 1
    listed = client.get("/api/assistant/history").json()["conversations"]
    assert [item["title"] for item in listed] == ["Friday incident"]


def test_the_api_will_not_rename_someone_elses_chat(reports_root):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    alice = _history_client(reports_root, user={"username": "alice"})
    mallory = _history_client(reports_root, user={"username": "mallory"})
    alice.post("/api/assistant/query", json={"question": "mine", "conversation": "c1"})

    response = mallory.patch(
        "/api/assistant/history",
        params={"conversation": "c1"},
        json={"title": "mine now"},
    )

    assert response.json()["renamed"] == 0
    assert (
        alice.get("/api/assistant/history").json()["conversations"][0]["title"]
        == "mine"
    )


@pytest.mark.parametrize(
    "title", ["x" * 5_000, "  \n\t ", "<img src=x onerror=alert(1)>", "'; DROP TABLE x"]
)
def test_a_hostile_title_is_bounded_not_rejected_into_a_500(reports_root, title):
    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _history_client(reports_root, user={"username": "alice"})
    client.post("/api/assistant/query", json={"question": "q", "conversation": "c1"})

    response = client.patch(
        "/api/assistant/history", params={"conversation": "c1"}, json={"title": title}
    )

    assert response.status_code in (200, 422), response.text
    stored = client.get("/api/assistant/history").json()["conversations"][0]["title"]
    assert len(stored) <= db.MAX_TITLE


def _peak_connections(engine, call) -> int:
    """Return the most connections one thread held at the same time during ``call``.

    Two at once is a latent deadlock, not a slow query: with a pool of five and enough
    readers, every thread ends up waiting for a connection every other thread is holding,
    and the panel stops answering for the length of the pool timeout.
    """
    import threading

    from sqlalchemy import event

    held = threading.local()
    peak = [0]

    @event.listens_for(engine, "checkout")
    def _out(*_):
        held.depth = getattr(held, "depth", 0) + 1
        peak[0] = max(peak[0], held.depth)

    @event.listens_for(engine, "checkin")
    def _back(*_):
        held.depth = max(0, getattr(held, "depth", 0) - 1)

    try:
        call()
    finally:
        event.remove(engine, "checkout", _out)
        event.remove(engine, "checkin", _back)
    return peak[0]


@pytest.mark.parametrize(
    "name, call",
    [
        ("conversations", lambda store: store.conversations("alice", limit=10)),
        ("load", lambda store: store.load("alice", limit=12)),
        ("clear", lambda store: store.clear("alice", conversation="c1")),
        (
            "append",
            lambda store: store.append("alice", "q", "a", [], 0, conversation="c1"),
        ),
        ("rename", lambda store: store.rename("alice", "c1", "named")),
    ],
)
def test_no_history_call_holds_two_connections_at_once(name, call):
    db.upgrade()
    store = db.history_store()
    store.append("alice", "seed", "answer", [], 0, conversation="c1")

    peak = _peak_connections(db.engine(), lambda: call(store))

    assert peak <= 1, f"{name} held {peak} connections at once"


def test_two_people_get_separate_chats_over_the_whole_http_path(reports_root):
    """The end the user sees: two accounts, one server, one database.

    The store is filtered by principal, but the principal is derived from the acting
    user object at the top of the request, so this exercises the join between the two.
    """
    from fastapi.testclient import TestClient

    from airflow_pytest_plugin.web.app import create_app

    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    alice = {"id": 42, "username": "alice"}
    bob = {"id": 77, "username": "bob"}

    def client_for(user):
        return TestClient(
            create_app(
                FileSystemReportSource(report_root=reports_root),
                authorizer=lambda dag, u: True,
                read_authorizer=lambda dag, u: True,
                user_dependency=lambda: user,
                assistant=AssistantRuntime(
                    provider_factory=FakeAssistant,
                    reducer_factory=PassthroughReducer,
                    provider_name="fake",
                    model_name="offline-fake",
                    context_model_name=None,
                    max_context_bytes=16_384,
                    max_output_tokens=256,
                    max_concurrent=2,
                    history=db.history_store(),
                    history_days=30,
                ),
            )
        )

    for user, question, chat in (
        (alice, "alice asks about test_login", "main"),
        (alice, "alice second thread", "work"),
        (bob, "bob asks about test_billing", "main"),
    ):
        with client_for(user) as client:
            assert (
                client.post(
                    "/api/assistant/query",
                    json={"question": question, "conversation": chat},
                ).status_code
                == 200
            )

    with client_for(alice) as client:
        hers = client.get("/api/assistant/history").json()
    with client_for(bob) as client:
        his = client.get("/api/assistant/history").json()

    assert {chat["id"] for chat in hers["conversations"]} == {"main", "work"}
    assert {chat["id"] for chat in his["conversations"]} == {"main"}
    assert "bob asks" not in str(hers["messages"])
    assert "alice" not in str(his["messages"])


def test_a_renamed_account_keeps_its_chats_and_a_reissued_name_inherits_none():
    """Two sides of the same rule: the identity is the key, not the label."""
    db.upgrade()
    store = db.history_store()
    store.append(
        audit.principal({"id": 42, "username": "ivan"}),
        "q",
        "a",
        [],
        1,
        conversation="main",
    )

    renamed = store.load(
        audit.principal({"id": 42, "username": "ivan.petrov"}),
        limit=12,
        conversation="main",
    )
    reissued = store.load(
        audit.principal({"id": 99, "username": "ivan"}), limit=12, conversation="main"
    )

    assert len(renamed) == 2
    assert reissued == []


def _fernet_key(monkeypatch):
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    chatcrypto._cached = None
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    return chatcrypto


@pytest.mark.parametrize(
    "given",
    [
        "разбор падения",
        "её чат",
        "ЧАТ",
        "chat 1",
        "a" * 80,
        "chat/../../etc",
        "~already-cleaned~",
    ],
)
def test_cleaning_a_conversation_id_twice_changes_nothing(given):
    """The id is cleaned on the way in and cleaned again in the store; they must agree.

    The cleaned form contains `~`, which the cleaner then stripped on a second pass and
    re-hashed. So an id that needed normalising at all -- non-ASCII, a space, over 64
    characters -- was written under `clean(clean(x))` and read under `clean(x)`, and the
    chat disappeared the moment it was written.
    """
    once = db.clean_conversation(given)

    assert db.clean_conversation(once) == once
    assert len(once) <= 64


def test_a_chat_under_a_cyrillic_id_reads_back():
    db.upgrade()
    store = db.history_store()

    store.append("id:1", "вопрос", "ответ", [], 1, conversation="разбор падения")

    assert [
        item["content"]
        for item in store.load("id:1", limit=9, conversation="разбор падения")
    ] == ["вопрос", "ответ"]
    assert store.rename("id:1", "разбор падения", "Имя") == 1
    listed = store.conversations("id:1", limit=9)
    assert [item["title"] for item in listed] == ["Имя"]
    assert store.clear("id:1", conversation="разбор падения") == 2


def test_the_id_the_api_hands_back_can_be_used_to_reopen_the_chat():
    """The browser stores whatever id the list gave it and sends it back next time."""
    db.upgrade()
    store = db.history_store()
    store.append("id:1", "вопрос", "ответ", [], 1, conversation="мой чат")

    listed = store.conversations("id:1", limit=9)[0]["id"]

    assert [
        item["content"] for item in store.load("id:1", limit=9, conversation=listed)
    ] == ["вопрос", "ответ"]


def test_the_documented_airflow_rotation_does_not_destroy_the_chat(monkeypatch):
    """Sharing Airflow's key means inheriting Airflow's rotation procedure.

    That procedure is: put the new key first, run `airflow rotate-fernet-key`, drop the
    old key. The command re-encrypts Airflow's connections and variables and knows
    nothing about a plugin's table, so step three took every stored transcript with it --
    an operator following the documentation exactly, losing data silently.
    """
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", old_key)
    chatcrypto._cached = None
    db.upgrade()
    store = db.history_store()
    store.append("id:1", "вопрос", "ответ", [], 1, conversation="c")
    store.rename("id:1", "c", "Мой чат")

    # Step one and two: the new key leads, the old one is still there to read with.
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", f"{new_key},{old_key}")
    chatcrypto._cached = None
    moved = db.rotate_history_key()
    assert moved["messages"] == 2
    assert moved["titles"] == 1
    assert moved["unreadable"] == 0

    # Step three: the old key is gone, as the procedure says.
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", new_key)
    chatcrypto._cached = None

    assert [
        item["content"] for item in store.load("id:1", limit=9, conversation="c")
    ] == [
        "вопрос",
        "ответ",
    ]
    assert store.conversations("id:1", limit=9)[0]["title"] == "Мой чат"


def test_rotation_leaves_a_row_it_cannot_read_alone(monkeypatch):
    """Re-encrypting a placeholder would make the loss permanent.

    A row whose key is already gone reads as the placeholder. Writing that back is the
    one irreversible thing this command could do -- the original key might still turn up
    in someone's password manager -- so those rows are counted and skipped.
    """
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    lost_key = Fernet.generate_key().decode()
    live_key = Fernet.generate_key().decode()

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", lost_key)
    chatcrypto._cached = None
    db.upgrade()
    store = db.history_store()
    store.append(
        "id:1", "утраченный вопрос", "утраченный ответ", [], 1, conversation="lost"
    )

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", live_key)
    chatcrypto._cached = None
    store.append("id:1", "живой вопрос", "живой ответ", [], 1, conversation="live")

    moved = db.rotate_history_key()

    assert moved["unreadable"] == 2
    assert moved["messages"] == 2
    assert [
        item["content"] for item in store.load("id:1", limit=9, conversation="live")
    ] == [
        "живой вопрос",
        "живой ответ",
    ]

    # The lost rows are untouched, so putting the old key back still recovers them.
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", f"{live_key},{lost_key}")
    chatcrypto._cached = None
    assert [
        item["content"] for item in store.load("id:1", limit=9, conversation="lost")
    ] == [
        "утраченный вопрос",
        "утраченный ответ",
    ]


def test_rotation_walks_every_batch_on_both_tables(monkeypatch):
    """The batch loop never ran: the batch is 500 rows and every other test has two.

    Both the paging cursor and the composite key on the names table are only exercised
    once there is more than one batch, and a cursor that fails to advance re-reads the
    same rows for ever.
    """
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(db, "_ROTATE_BATCH", 3)
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", old_key)
    chatcrypto._cached = None
    db.upgrade()
    store = db.history_store()
    for index in range(7):
        # Two principals, so the names table needs both halves of its key to page.
        for principal in ("id:1", "id:2"):
            store.append(
                principal,
                f"вопрос {index}",
                f"ответ {index}",
                [],
                1,
                conversation=f"c{index:02d}",
            )
            store.rename(principal, f"c{index:02d}", f"Имя {principal} {index}")

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", f"{new_key},{old_key}")
    chatcrypto._cached = None
    moved = db.rotate_history_key()

    assert moved == {"messages": 28, "titles": 14, "unreadable": 0}

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", new_key)
    chatcrypto._cached = None
    for principal in ("id:1", "id:2"):
        assert [
            item["content"]
            for item in store.load(principal, limit=9, conversation="c03")
        ] == ["вопрос 3", "ответ 3"]
        listed = {
            item["id"]: item["title"]
            for item in store.conversations(principal, limit=20)
        }
        assert len(listed) == 7
        assert listed["c06"] == f"Имя {principal} 6"


def test_clearing_with_an_empty_conversation_deletes_nothing():
    """`clear` treats None as "everything"; an empty string must not become a chat id.

    Cleaning the id is what makes a direct call agree with the runtime, but the cleaner
    maps an empty string onto the default conversation -- which would turn a blank
    parameter into "delete the user's main chat".
    """
    db.upgrade()
    store = db.history_store()
    store.append("alice", "q", "a", [], 1, conversation=db.DEFAULT_CONVERSATION)

    assert store.clear("alice", conversation="") == 0
    assert len(store.load("alice", limit=9, conversation=db.DEFAULT_CONVERSATION)) == 2


def test_rotation_encrypts_rows_written_before_encryption_existed(monkeypatch):
    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY", raising=False)
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    chatcrypto._cached = None
    db.upgrade()
    store = db.history_store()
    store.append(
        "id:1", "открытый вопрос", "открытый ответ", [], 1, conversation="plain"
    )

    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    chatcrypto._cached = None
    moved = db.rotate_history_key()

    assert moved["messages"] == 2
    with db.engine().connect() as connection:
        raw = [
            row[0]
            for row in connection.execute(
                sa.text(f"select content from {db.MESSAGE_TABLE} order by id")
            )
        ]
    assert all(value.startswith("gAAAAA") for value in raw), raw
    assert [
        item["content"] for item in store.load("id:1", limit=9, conversation="plain")
    ] == [
        "открытый вопрос",
        "открытый ответ",
    ]


def test_a_stored_chat_is_not_readable_in_the_database(monkeypatch):
    """Anyone with the metadata database gets the transcript otherwise.

    It is the same class of material Airflow already encrypts in connections -- the
    questions name failing tests and the answers quote tracebacks -- so it uses the same
    key.
    """
    _fernet_key(monkeypatch)
    db.upgrade()
    store = db.history_store()
    question = "почему упал test_login на проде?"
    answer = "AssertionError: assert 401 == 200 в tests/test_auth.py:42"

    store.append("id:42", question, answer, [], 7, conversation="main")

    with db.engine().connect() as connection:
        raw = [
            row[0]
            for row in connection.execute(
                sa.text(f"select content from {db.MESSAGE_TABLE} order by id")
            )
        ]

    assert question not in " ".join(raw)
    assert answer not in " ".join(raw)
    assert all(value.startswith("gAAAAA") for value in raw), raw
    restored = store.load("id:42", limit=12, conversation="main")
    assert [item["content"] for item in restored] == [question, answer]


def test_a_chat_title_is_encrypted_too(monkeypatch):
    """The default title *is* the first question, and a chosen one is still the user's."""
    _fernet_key(monkeypatch)
    db.upgrade()
    store = db.history_store()
    store.append("id:42", "секретный вопрос", "ответ", [], 1, conversation="main")
    store.rename("id:42", "main", "мой приватный тред")

    with db.engine().connect() as connection:
        titles = [
            row[0]
            for row in connection.execute(
                sa.text(f"select title from {db.CONVERSATION_TABLE}")
            )
        ]

    assert "приватный" not in " ".join(titles)
    listed = store.conversations("id:42", limit=10)
    assert [chat["title"] for chat in listed] == ["мой приватный тред"]


def test_a_chat_written_before_encryption_still_opens(monkeypatch):
    """Existing deployments must not lose their history the day they get a key."""
    monkeypatch.delenv("AIRFLOW__CORE__FERNET_KEY", raising=False)
    from airflow_pytest_plugin import chatcrypto

    chatcrypto._cached = None
    db.upgrade()
    store = db.history_store()
    store.append("id:42", "старый вопрос", "старый ответ", [], 1, conversation="main")

    _fernet_key(monkeypatch)
    store.append("id:42", "новый вопрос", "новый ответ", [], 1, conversation="main")

    restored = [item["content"] for item in store.load("id:42", limit=12)]

    assert restored == ["старый вопрос", "старый ответ", "новый вопрос", "новый ответ"]


def test_a_long_title_survives_encryption_on_a_real_column(monkeypatch):
    """200 characters of title become 356 of Fernet; the column had to grow for it."""
    _fernet_key(monkeypatch)
    db.upgrade()
    store = db.history_store()
    store.append("id:42", "q", "a", [], 1, conversation="main")
    title = "т" * db.MAX_TITLE

    assert store.rename("id:42", "main", title) == 1
    assert store.conversations("id:42", limit=10)[0]["title"] == title


def test_migration_five_widens_the_title_on_the_dialects_that_enforce_it():
    """SQLite ignores the declared width; PostgreSQL and MySQL do not.

    Without this the first encrypted rename on PostgreSQL fails with "value too long
    for type character varying(200)", and the store swallows it as a warning -- so the
    rename silently does nothing.
    """
    statements: list[str] = []

    class FakeConnection:
        def __init__(self, dialect: str) -> None:
            self.engine = SimpleNamespace(dialect=SimpleNamespace(name=dialect))

        def execute(self, statement):
            statements.append(str(statement))

    db._migrate_to_5(FakeConnection("sqlite"))
    assert statements == []

    db._migrate_to_5(FakeConnection("postgresql"))
    db._migrate_to_5(FakeConnection("mysql"))

    assert "ALTER COLUMN title TYPE TEXT" in statements[0]
    assert "MODIFY title TEXT" in statements[1]
    assert all(db.CONVERSATION_TABLE in item for item in statements)


def test_the_recorded_version_reaches_the_current_schema():
    """A build whose migrations stop short records a version its tables do not match."""
    db.upgrade()

    assert db.recorded_version() == db.SCHEMA_VERSION
    assert set(db._MIGRATIONS) == set(range(3, db.SCHEMA_VERSION + 1))


def test_status_says_whether_the_stored_chat_is_encrypted(reports_root, monkeypatch):
    """An operator asking "who else can read this" gets an answer, not an assumption."""
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    from airflow_pytest_plugin import chatcrypto

    chatcrypto._cached = None
    monkeypatch.setenv("AIRFLOW__CORE__FERNET_KEY", Fernet.generate_key().decode())
    db.upgrade()
    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        history=db.history_store(),
        history_days=30,
    )

    from fastapi.testclient import TestClient

    from airflow_pytest_plugin.web.app import create_app

    def client():
        return TestClient(
            create_app(
                FileSystemReportSource(report_root=reports_root),
                authorizer=lambda dag, u: True,
                read_authorizer=lambda dag, u: True,
                user_dependency=lambda: {"id": 42},
                assistant=runtime,
            )
        )

    with client() as opened:
        body = opened.get("/api/assistant/status").json()

    assert body["history_server_side"] is True
    assert body["history_encrypted"] is True

    monkeypatch.setenv(chatcrypto.ENCRYPT_ENV, "0")
    with client() as opened:
        assert opened.get("/api/assistant/status").json()["history_encrypted"] is False


def test_one_bad_message_does_not_take_the_store_down_for_everyone():
    """A lone surrogate is something a browser can send, and it is not an outage.

    The 30-second cooldown exists so a database that is genuinely down is not hammered
    once per request. Tripping it on the *content* of one message let any user switch
    off server-side history for every other user by pasting one character.
    """
    db.upgrade()
    store = db.history_store()
    store.append("id:alice", "нормальный вопрос", "нормальный ответ", [], 1)

    store.append("id:mallory", "\ud800", "ответ", [], 1)

    assert store.available is True
    assert len(store.load("id:alice", limit=10)) == 2


def test_a_message_that_cannot_be_encoded_is_stored_repaired_not_dropped():
    """The user still asked it, and the answer is still theirs to re-read."""
    db.upgrade()
    store = db.history_store()

    store.append("id:alice", "вопрос \ud800 хвост", "ответ", [], 1)

    restored = [item["content"] for item in store.load("id:alice", limit=10)]
    assert len(restored) == 2
    assert restored[0].startswith("вопрос ")
    assert restored[0].endswith(" хвост")


def test_a_real_outage_is_still_treated_as_one(monkeypatch):
    """Narrowing what counts as an outage must not stop counting the real ones."""
    db.upgrade()
    store = db.history_store()

    def explode(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(db, "engine", explode)
    try:
        store.append("id:alice", "q", "a", [], 1)
    except OSError:
        pass
    monkeypatch.undo()

    store._warn(OSError("connection refused"))
    assert store.available is False


def test_a_finished_answer_is_already_saved_when_the_browser_is_told_it_finished(
    reports_root,
):
    """ "Done" has to mean saved, or the chat list is wrong exactly when it is looked at.

    The transcript was written in the generator's ``finally``, which runs after the last
    event has been flushed. A browser that opens **Chats** -- or reloads -- in the moment
    it renders the answer was told the chat did not exist yet.
    """

    from airflow_pytest_plugin.web.app import create_app

    db.upgrade()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    app = create_app(
        FileSystemReportSource(report_root=reports_root),
        authorizer=lambda dag, u: True,
        read_authorizer=lambda dag, u: True,
        user_dependency=lambda: {"id": 42},
        assistant=AssistantRuntime(
            provider_factory=FakeAssistant,
            reducer_factory=PassthroughReducer,
            provider_name="fake",
            model_name="offline-fake",
            context_model_name=None,
            max_context_bytes=16_384,
            max_output_tokens=256,
            max_concurrent=2,
            history=db.history_store(),
            history_days=30,
        ),
    )

    del app  # the ordering lives in the generator, not in the transport
    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
        history=db.history_store(),
        history_days=30,
    )
    store = db.history_store()
    stored_at_done = None

    for name, _ in runtime.stream(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, u: True,
        user={"id": 42},
        query=AssistantQuery(question="почему упал тест?", conversation="main"),
    ):
        if name == "done":
            # A browser reacts here: it renders the answer and may refetch the chat list
            # before the generator is ever resumed.
            stored_at_done = store.load("id:42", limit=10, conversation="main")

    assert stored_at_done is not None, "the stream never reported completion"
    assert len(stored_at_done) == 2, stored_at_done


def test_an_answer_over_an_empty_scope_is_still_the_users_chat(reports_root):
    """A question asked with nothing in scope is still a question they asked.

    Storing only "answered" outcomes meant that on a fresh install -- or with a filter
    that matches nothing, which is exactly when someone asks what the product does -- the
    reply appeared, the tab was closed, and the whole exchange was gone. No chat in the
    list, no row in the database, nothing to reopen in another tab.
    """
    db.upgrade()
    store = db.history_store()
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

    reply = runtime.ask(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, user: True,
        user={"id": 42},
        query=AssistantQuery(
            question="что умеет airflow-pytest-operator?", conversation="main"
        ),
    )

    assert reply.answer
    stored = store.load("id:42", limit=10, conversation="main")
    assert [item["content"] for item in stored] == [
        "что умеет airflow-pytest-operator?",
        reply.answer,
    ]
    assert [chat["id"] for chat in store.conversations("id:42", limit=5)] == ["main"]


def test_a_streamed_answer_over_an_empty_scope_is_stored_too(reports_root):
    """The streaming path stores before it says "done"; that must hold here as well."""
    db.upgrade()
    store = db.history_store()
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

    at_done = None
    for name, _ in runtime.stream(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, u: True,
        user={"id": 43},
        query=AssistantQuery(question="что это за продукт?", conversation="main"),
    ):
        if name == "done":
            at_done = store.load("id:43", limit=10, conversation="main")

    assert at_done is not None
    assert len(at_done) == 2, at_done


def test_a_refused_request_is_not_stored_as_a_chat(reports_root):
    """Only a completed exchange is one: a 429 or a permission error is not a message."""
    db.upgrade()
    store = db.history_store()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
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
        rate_limit=1,
        rate_window_seconds=3_600.0,
        rate_store=db.rate_store(),
    )
    ask = {
        "source": FileSystemReportSource(report_root=reports_root),
        "can_read": lambda dag, user: True,
        "user": {"id": 44},
    }
    runtime.ask(**ask, query=AssistantQuery(question="первый", conversation="main"))
    with pytest.raises(AssistantQuotaError):
        runtime.ask(**ask, query=AssistantQuery(question="второй", conversation="main"))

    stored = [item["content"] for item in store.load("id:44", limit=10)]
    assert "второй" not in stored, stored


def test_a_stopped_answer_keeps_what_was_written(reports_root):
    """Stop keeps the partial text on screen; the server has to keep it too.

    Otherwise the two disagree, and the server wins on reload: the reader stops an
    answer, sees the part that arrived, refreshes -- and their question and its partial
    reply are both gone. That is the same loss as an unsaved chat, reached by pressing a
    button the window offers.
    """
    db.upgrade()
    store = db.history_store()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class SlowStream(FakeAssistant):
        def stream(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            yield "Первая часть. "
            yield "Вторая часть. "
            yield "Третья часть."

    runtime = AssistantRuntime(
        provider_factory=SlowStream,
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

    events = runtime.stream(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, u: True,
        user={"id": 90},
        query=AssistantQuery(question="долгий вопрос", conversation="stopped"),
    )
    deltas = 0
    for name, _ in events:
        if name == "delta":
            deltas += 1
            if deltas == 2:
                events.close()  # the browser pressing Stop
                break

    rows = [
        item["content"]
        for item in store.load("id:90", limit=10, conversation="stopped")
    ]

    assert len(rows) == 2, rows
    assert rows[0] == "долгий вопрос"
    assert "Первая часть." in rows[1], rows[1]
    assert "Третья часть" not in rows[1], "only what actually arrived"


def test_a_stopped_answer_is_stored_exactly_as_the_reader_saw_it(reports_root):
    """The stored copy wins on reload, so it has to be the same text, character for
    character.

    A completed answer is stored as the model wrote it. The partial went through the
    secret scrubber as well, which is prose-hostile by design -- "bearer token" comes out
    as "bearer [REDACTED]". So the reader stopped an answer, read it, refreshed, and the
    words changed underneath them: the one thing storing the partial was meant to
    prevent. Nothing is lost by matching the completed path -- the model only ever saw
    redacted evidence, so its output has no secret to scrub.
    """
    db.upgrade()
    store = db.history_store()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class Prose(FakeAssistant):
        def stream(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            yield "Send a bearer token in the Authorization: header. "
            yield "Второй кусок."

    runtime = AssistantRuntime(
        provider_factory=Prose,
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

    events = runtime.stream(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, u: True,
        user={"id": 91},
        query=AssistantQuery(question="как авторизоваться?", conversation="prose"),
    )
    shown = []
    for name, payload in events:
        if name == "delta":
            shown.append(payload["text"])
            events.close()
            break

    stored = [
        item["content"] for item in store.load("id:91", limit=10, conversation="prose")
    ]

    assert stored[1] == "".join(shown).strip()
    assert "[REDACTED]" not in stored[1]


def test_stopping_before_a_single_word_arrives_stores_nothing(reports_root):
    """There is no exchange to keep if the answer never started."""
    db.upgrade()
    store = db.history_store()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class NeverStarts(FakeAssistant):
        def stream(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            return
            yield  # pragma: no cover - makes this a generator

    runtime = AssistantRuntime(
        provider_factory=NeverStarts,
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
    events = runtime.stream(
        source=FileSystemReportSource(report_root=reports_root),
        can_read=lambda dag, u: True,
        user={"id": 91},
        query=AssistantQuery(question="ничего не придёт", conversation="nothing"),
    )
    for name, _ in events:
        if name == "meta":
            events.close()
            break

    assert store.load("id:91", limit=10, conversation="nothing") == []


def test_a_provider_that_dies_mid_answer_keeps_what_arrived(reports_root):
    """The window shows the partial with the reason beside it; the server agrees.

    Same rule as Stop, reached without the reader doing anything: what they can see must
    survive a refresh, or the exchange is deleted in front of them by a failure that was
    not their fault.
    """
    db.upgrade()
    store = db.history_store()
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class DyingStream(FakeAssistant):
        def stream(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            yield "Начало ответа. "
            raise RuntimeError("upstream went away")

    runtime = AssistantRuntime(
        provider_factory=DyingStream,
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

    with pytest.raises(AssistantProviderError):
        for _ in runtime.stream(
            source=FileSystemReportSource(report_root=reports_root),
            can_read=lambda dag, u: True,
            user={"id": 92},
            query=AssistantQuery(question="оборвётся", conversation="dead"),
        ):
            pass

    rows = [
        item["content"] for item in store.load("id:92", limit=10, conversation="dead")
    ]

    assert len(rows) == 2, rows
    assert "Начало ответа" in rows[1]


def test_a_user_with_more_chats_than_the_list_holds_is_told_so():
    """Twenty is the list's limit, not the number of chats somebody has.

    Past it the older ones are still stored, still counted against retention and still
    readable by id -- but they leave the window with no explanation, and the summary line
    reports the truncated length as though it were the total. A reader whose chat
    vanished has no way to tell that from it having been deleted.
    """
    db.upgrade()
    store = db.history_store()
    for index in range(db.MAX_CONVERSATIONS + 5):
        store.append(
            "id:80",
            f"вопрос {index}",
            f"ответ {index}",
            [],
            1,
            conversation=f"chat{index:03d}",
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

    body = runtime.history({"id": 80})

    assert len(body["conversations"]) == db.MAX_CONVERSATIONS
    assert body["conversations_truncated"] is True
    # The oldest is out of the list but has not been lost.
    assert len(store.load("id:80", limit=10, conversation="chat000")) == 2


def test_a_user_within_the_limit_is_not_told_anything():
    db.upgrade()
    store = db.history_store()
    store.append("id:81", "один вопрос", "один ответ", [], 1, conversation="only")
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

    body = runtime.history({"id": 81})

    assert body["conversations_truncated"] is False
    assert len(body["conversations"]) == 1
