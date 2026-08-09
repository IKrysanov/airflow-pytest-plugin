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

"""The plugin's own tables, in Airflow's metadata database by default.

Everything the reader needs to remember *between processes* lives here: the per-principal
token budget (an in-memory counter is per worker and resets on deploy, so it cannot be a
budget at all) and the server-side chat transcript.

Three deliberate choices:

* **SQLAlchemy Core, not Airflow's declarative Base.** Our tables are described in our own
  ``MetaData`` and prefixed ``pytest_assistant_``. Nothing is registered with Airflow's ORM,
  so ``airflow db`` commands, its autogenerate and its models never see them.
* **Creation is an explicit operator action.** Airflow has no migration hook for plugins.
  Creating tables from the API server at import time races across workers and needs DDL
  rights in the request path, so ``python -m airflow_pytest_plugin.db upgrade`` owns it --
  the same shape as ``airflow db migrate``.
* **Absence is normal.** No URL, no SQLAlchemy, or tables not created yet all degrade to the
  in-process behaviour instead of failing a request. The assistant is a convenience; it must
  not take the dashboard down because a table is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from . import chatcrypto

if TYPE_CHECKING:  # pragma: no cover - import-light at runtime
    from sqlalchemy import MetaData, Table
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

DB_URL_ENV = "AIRFLOW_PYTEST_ASSISTANT_DB_URL"
DB_CONN_ID_ENV = "AIRFLOW_PYTEST_ASSISTANT_DB_CONN_ID"

#: Airflow writes the legacy scheme for these connection types; SQLAlchemy 2 rejects them.
_SCHEME_ALIASES = {"postgres": "postgresql", "mysql": "mysql+mysqldb"}

#: Bumped whenever the tables change; ``upgrade`` records it so a future version can tell
#: what it is looking at instead of guessing from column names.
SCHEMA_VERSION = 5

TABLE_PREFIX = "pytest_assistant_"
USAGE_TABLE = f"{TABLE_PREFIX}usage"
MESSAGE_TABLE = f"{TABLE_PREFIX}message"
RATE_TABLE = f"{TABLE_PREFIX}rate"
CONVERSATION_TABLE = f"{TABLE_PREFIX}conversation"
SCHEMA_TABLE = f"{TABLE_PREFIX}schema"

_lock = threading.Lock()
_engine: Engine | None = None
_engine_ready = False
_metadata: MetaData | None = None
#: Why the last URL lookup or engine build failed, so the CLI can say something useful.
_resolution_error: str | None = None
_engine_error: str | None = None
_tables: dict[str, Table] = {}


class _LazyMetadata:
    """Exposes the table set without importing SQLAlchemy at module load."""

    @property
    def tables(self) -> dict[str, Any]:
        """Return the mapping of table name to table, building it on first use."""
        metadata = _build_metadata()
        return {} if metadata is None else dict(metadata.tables)


#: Introspectable table set; ``METADATA.tables`` builds lazily.
METADATA = _LazyMetadata()


def _build_metadata() -> MetaData | None:
    global _metadata
    if _metadata is not None:
        return _metadata
    try:
        from sqlalchemy import (
            BigInteger,
            Column,
            DateTime,
            Index,
            Integer,
            MetaData,
            String,
            Table,
            Text,
        )
    except ImportError:  # pragma: no cover - SQLAlchemy ships with Airflow
        return None
    metadata = MetaData()
    _tables[USAGE_TABLE] = Table(
        USAGE_TABLE,
        metadata,
        # The Airflow principal, as recorded in the audit log. Not hashed: an operator
        # investigating spend needs to see who spent it.
        Column("principal", String(128), primary_key=True),
        # Days since the epoch, UTC. An integer keeps the daily reset comparable and
        # indexable on every dialect Airflow supports.
        Column("usage_day", Integer, primary_key=True),
        Column("tokens", BigInteger, nullable=False),
        Column("requests", Integer, nullable=False),
    )
    _tables[MESSAGE_TABLE] = Table(
        MESSAGE_TABLE,
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        # Every read is filtered by this column. It is the ownership boundary for the
        # transcript, not a convenience: one principal must never load another's chat.
        Column("principal", String(128), nullable=False),
        # Which chat this message belongs to. The browser picks the id; it is opaque here
        # and only ever queried together with the principal, so guessing one buys nothing.
        Column("conversation", String(64), nullable=False),
        Column("role", String(16), nullable=False),
        Column("content", Text, nullable=False),
        # Evidence links only -- the [R<n>] report references, so restored answers keep
        # working buttons. The REPORT EVIDENCE block itself (tracebacks, captured output)
        # is deliberately never stored.
        Column("evidence", Text, nullable=True),
        Column("total_tokens", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Index(
            f"ix_{MESSAGE_TABLE}_principal_chat_id", "principal", "conversation", "id"
        ),
        Index(f"ix_{MESSAGE_TABLE}_created_at", "created_at"),
    )
    _tables[RATE_TABLE] = Table(
        RATE_TABLE,
        metadata,
        Column("principal", String(128), primary_key=True),
        # The window's index: ``floor(unix_time / window_seconds)``. Wall clock, not the
        # monotonic clock the in-process limiter uses -- monotonic values are meaningless
        # between processes, and this row is read by all of them.
        Column("rate_window", BigInteger, primary_key=True),
        Column("requests", Integer, nullable=False),
    )
    _tables[CONVERSATION_TABLE] = Table(
        CONVERSATION_TABLE,
        metadata,
        Column("principal", String(128), primary_key=True),
        Column("conversation", String(64), primary_key=True),
        # A name the user chose. Absent means "use the first question", which is the
        # default every chat starts with -- so this table only holds the exceptions.
        # Text rather than a bounded string because the stored form may be a Fernet
        # token: a 200-character title encrypts to 356, which VARCHAR(200) rejects
        # outright on PostgreSQL. Schema 5 widens it on databases created before that.
        Column("title", Text, nullable=False),
    )
    _tables[SCHEMA_TABLE] = Table(
        SCHEMA_TABLE,
        metadata,
        Column("version", Integer, primary_key=True),
    )
    _metadata = metadata
    return metadata


def _airflow_url() -> str | None:
    """Return Airflow's own metadata-database URL, when running inside Airflow.

    Read through ``conf`` rather than ``settings.SQL_ALCHEMY_CONN`` so the ``_cmd`` and
    ``_secret`` forms of the setting resolve too -- those are how an operator keeps the
    metadata password out of the environment, and reading the module attribute would miss
    them. ``settings`` remains a fallback for older layouts.

    A failure here is recorded rather than swallowed: "no database is configured" is a lie
    when the real problem is a missing driver, and it sends the operator looking in the
    wrong place.
    """
    global _resolution_error
    try:
        from airflow.configuration import conf

        url = conf.get("database", "sql_alchemy_conn")
        if url:
            _resolution_error = None
            return str(url)
    except Exception as error:
        _resolution_error = f"{type(error).__name__}: {error}"
    try:
        from airflow.settings import SQL_ALCHEMY_CONN

        if SQL_ALCHEMY_CONN:
            _resolution_error = None
            return str(SQL_ALCHEMY_CONN)
    except Exception as error:
        # Keep the first failure: ``conf`` is the route that matters, and its error names
        # the real cause. The fallback's own complaint is usually a symptom of the same one.
        if _resolution_error is None:
            _resolution_error = f"{type(error).__name__}: {error}"
    return None


def _connection_url() -> str | None:
    """Resolve an Airflow connection id into a SQLAlchemy URL.

    This is the way to give the plugin its own database without a password in our
    environment: the connection is stored wherever Airflow's configured secrets backend
    keeps it, and Airflow resolves it.
    """
    conn_id = os.environ.get(DB_CONN_ID_ENV, "").strip()
    if not conn_id:
        return None
    try:
        from airflow.models import Connection

        uri = str(Connection.get_connection_from_secrets(conn_id).get_uri())
    except Exception as error:
        _log.warning(
            "assistant database connection %r could not be resolved: %s", conn_id, error
        )
        return None
    scheme, separator, rest = uri.partition("://")
    if not separator:
        return uri
    return f"{_SCHEME_ALIASES.get(scheme, scheme)}://{rest}"


def configured_url() -> str | None:
    """Return the database URL to use, or ``None`` when there is nothing to connect to.

    Precedence is most-explicit-first: a literal URL, then an Airflow connection id, then
    Airflow's own metadata database. Naming a connection that cannot be resolved yields
    ``None`` rather than falling through -- an operator who asked for a specific database
    should see an error, not have their data quietly written somewhere else.
    """
    explicit = os.environ.get(DB_URL_ENV, "").strip()
    if explicit:
        return explicit
    if os.environ.get(DB_CONN_ID_ENV, "").strip():
        return _connection_url()
    return _airflow_url()


def engine() -> Engine | None:
    """Return a cached engine, or ``None`` when no database is available."""
    global _engine, _engine_ready, _engine_error
    with _lock:
        if _engine_ready:
            return _engine
        _engine_ready = True
        url = configured_url()
        if not url:
            return None
        try:
            from sqlalchemy import create_engine

            # A small pool on purpose: this is a second pool against the same server as
            # Airflow's own, and the plugin issues a couple of tiny statements per
            # assistant question. pool_pre_ping because an API server outlives its idle
            # connections, and a stale one must not surface as a failed request.
            options: dict[str, Any] = {"pool_pre_ping": True, "future": True}
            if not url.startswith("sqlite"):
                options.update(pool_size=2, max_overflow=3, pool_recycle=1_800)
            _engine = create_engine(url, **options)
            _engine_error = None
        except Exception as error:
            # Typically a missing driver (`postgresql://` without psycopg2). Recording it
            # turns "no database is configured" into the sentence that names the fix.
            _engine_error = f"{type(error).__name__}: {_scrub(error)}"
            _log.warning("assistant database is unavailable: %s", _engine_error)
            _engine = None
        return _engine


def reset_engine() -> None:
    """Drop the cached engine. For tests and for a changed environment."""
    global _engine, _engine_ready, _metadata, _resolution_error, _engine_error
    with _lock:
        if _engine is not None:
            try:
                _engine.dispose()
            except Exception:  # pragma: no cover - best effort
                pass
        _engine = None
        _engine_ready = False
        _metadata = None
        _resolution_error = None
        _engine_error = None
        _tables.clear()


def _table(name: str) -> Table | None:
    _build_metadata()
    return _tables.get(name)


#: The schema version each table first appeared in. A database created by an older build
#: is missing the newer ones, and a store must say so rather than fail every statement.
_TABLE_VERSION = {
    USAGE_TABLE: 1,
    MESSAGE_TABLE: 2,
    RATE_TABLE: 3,
    CONVERSATION_TABLE: 4,
    SCHEMA_TABLE: 1,
}


def ready() -> bool:
    """Whether the tables this build expects exist and can be used right now."""
    version = recorded_version()
    return version is not None and version >= SCHEMA_VERSION


def table_ready(name: str) -> bool:
    """Whether one table exists, even on a database an upgrade has not reached yet.

    Lets a deployment that is one version behind keep the features it does have instead of
    losing all of them at once, while a feature whose table is genuinely absent reports
    itself unavailable and falls back in process.
    """
    version = recorded_version()
    return version is not None and version >= _TABLE_VERSION.get(name, SCHEMA_VERSION)


def recorded_version() -> int | None:
    """Return the schema version stored in the database, or ``None`` if not initialised."""
    return _probe()[0]


def _probe() -> tuple[int | None, bool, str | None]:
    """Return ``(version, reachable, error)``.

    A missing table and an unreachable server both leave the version unknown, but they need
    different fixes -- "run upgrade" versus "check the connection" -- so they are told
    apart here instead of being collapsed into one unhelpful ``None``.
    """
    active = engine()
    schema = _table(SCHEMA_TABLE)
    if active is None or schema is None:
        return None, False, _engine_error
    try:
        from sqlalchemy import select

        with active.connect() as connection:
            try:
                value = connection.execute(select(schema.c.version)).scalar()
            except Exception:
                # Connected, but the table is not there yet.
                return None, True, None
        return (int(value) if value is not None else None), True, None
    except Exception as error:
        return None, False, f"{type(error).__name__}: {_scrub(error)}"


def _scrub(error: BaseException) -> str:
    """Render a connection error without the credentials the URL may contain."""
    text = " ".join(str(error).split())
    url = configured_url() or ""
    scheme, separator, rest = url.partition("://")
    if separator and "@" in rest:
        credentials = rest.split("@", 1)[0]
        if credentials:
            text = text.replace(credentials, "***")
            for part in credentials.split(":"):
                if part:
                    text = text.replace(part, "***")
    return text[:300]


def status() -> dict[str, Any]:
    """Summarise what the storage layer can do, for the CLI and for diagnostics."""
    url = configured_url()
    version, reachable, error = _probe()
    return {
        "configured": bool(url),
        "reachable": reachable,
        "reason": (None if url else _resolution_error) or error,
        # "ready" means this build's features all work, so a database an upgrade has not
        # reached yet is not ready even though its older tables answer fine.
        "ready": version is not None and version >= SCHEMA_VERSION,
        "version": version,
        "expected_version": SCHEMA_VERSION,
        # Credentials live in this URL, so only the dialect and host shape are reported.
        "url": _safe_url(url) if url else None,
    }


def _safe_url(url: str) -> str:
    scheme, _, rest = url.partition("://")
    host = rest.rsplit("@", 1)[-1] if "@" in rest else rest
    return f"{scheme}://{host}"


def _migrate_to_3(connection: Any) -> None:
    """Schema 3 gave each message a conversation, and added the rate-limit table.

    ``create_all`` made the new table but could not touch the existing message table, so
    this is the half that has to be written by hand. Existing rows join the default
    conversation, which is exactly where a single-transcript history belongs.
    """
    from sqlalchemy import text

    connection.execute(
        text(
            f"ALTER TABLE {MESSAGE_TABLE} ADD COLUMN conversation "
            f"VARCHAR(64) NOT NULL DEFAULT '{DEFAULT_CONVERSATION}'"
        )
    )
    try:
        connection.execute(
            text(
                f"CREATE INDEX ix_{MESSAGE_TABLE}_principal_chat_id "
                f"ON {MESSAGE_TABLE} (principal, conversation, id)"
            )
        )
    except Exception:  # pragma: no cover - an index left by a partial run
        pass


def _migrate_to_4(connection: Any) -> None:
    """Schema 4 let a user name a chat. Only a new table, so nothing to alter."""
    del connection


def _migrate_to_5(connection: Any) -> None:
    """Schema 5 widened the chat title so an encrypted one fits.

    Encryption is decided per row and needs no data migration, but the column it is
    written to does have to hold a token: 200 characters of title become 356 of Fernet,
    and PostgreSQL enforces the declared width. SQLite does not, so it is left alone --
    ``ALTER COLUMN`` is not in its dialect and the existing column already accepts the
    value.
    """
    from sqlalchemy import text

    dialect = connection.engine.dialect.name
    if dialect == "sqlite":
        return
    statement = {
        "postgresql": f"ALTER TABLE {CONVERSATION_TABLE} ALTER COLUMN title TYPE TEXT",
        "mysql": f"ALTER TABLE {CONVERSATION_TABLE} MODIFY title TEXT NOT NULL",
    }.get(dialect)
    if statement is None:  # pragma: no cover - an unfamiliar dialect
        return
    connection.execute(text(statement))


#: Version -> the statements that turn the previous shape into this one. ``create_all``
#: covers new tables; anything that alters an existing table has to live here, because a
#: recorded version that the tables do not actually match is invisible until an insert
#: fails somewhere it is caught and swallowed.
_MIGRATIONS: dict[int, Callable[[Any], None]] = {
    3: _migrate_to_3,
    4: _migrate_to_4,
    5: _migrate_to_5,
}


def _missing_columns(active: Engine) -> dict[str, list[str]]:
    """Return the columns this build expects that the database does not have."""
    from sqlalchemy import inspect

    inspector = inspect(active)
    missing: dict[str, list[str]] = {}
    for name, table in _tables.items():
        if not inspector.has_table(name):
            continue
        present = {column["name"] for column in inspector.get_columns(name)}
        absent = [column.name for column in table.columns if column.name not in present]
        if absent:
            missing[name] = absent
    return missing


def upgrade() -> dict[str, Any]:
    """Create missing tables, run any pending migrations, then record the version.

    The version is recorded **last and only on success**: every readiness check trusts
    that number, so writing it over a database the migrations did not actually reach is
    what turns a broken upgrade into a feature that silently does nothing.
    """
    active = engine()
    metadata = _build_metadata()
    if active is None or metadata is None:
        raise RuntimeError(
            f"No database is configured. Set {DB_URL_ENV}, or run inside Airflow so the "
            "metadata database can be used."
        )
    from sqlalchemy import insert, select

    before = recorded_version()
    existed = before is not None
    # Replicas start together and each start runs this command, so every step below races
    # an identical one in another process. None of those races is fatal on its own -- "the
    # table already exists", "the column already exists" -- and the only question that
    # matters is whether the schema is right afterwards. Each step therefore records its
    # failure and the verification below is the single authority. A losing replica that
    # raised here would abort its start-up chain and never run Airflow at all.
    trouble: list[str] = []
    try:
        metadata.create_all(active)
    except Exception as error:  # pragma: no cover - only under a real race
        trouble.append(f"{type(error).__name__}: {_scrub(error)}")

    def run_migrations(pending: list[int]) -> None:
        for version in pending:
            try:
                with active.begin() as connection:
                    _MIGRATIONS[version](connection)
            except Exception as error:
                trouble.append(f"{type(error).__name__}: {_scrub(error)}")

    run_migrations(
        [v for v in sorted(_MIGRATIONS) if before is not None and before < v]
    )

    missing = _missing_columns(active)
    if missing:
        # The recorded number can be wrong: a build that altered nothing still wrote its
        # version, which is precisely the state that made this bug invisible. So the
        # schema itself, not the bookkeeping, decides whether there is work left -- retry
        # every migration and judge by the tables afterwards. Each one is safe to repeat:
        # re-adding a column simply fails and is recorded.
        run_migrations(sorted(_MIGRATIONS))
        missing = _missing_columns(active)

    if missing:
        detail = "; ".join(
            f"{name} is missing {', '.join(columns)}"
            for name, columns in missing.items()
        )
        why = f" Underlying error: {trouble[0]}" if trouble else ""
        raise RuntimeError(
            f"The tables do not match schema version {SCHEMA_VERSION}: {detail}.{why} "
            "The recorded version was left unchanged so nothing trusts a schema that is "
            "not there."
        )

    schema = _tables[SCHEMA_TABLE]
    with active.begin() as connection:
        current = connection.execute(select(schema.c.version)).scalar()
        if current is None:
            connection.execute(insert(schema).values(version=SCHEMA_VERSION))
        elif int(current) != SCHEMA_VERSION:
            from sqlalchemy import update as sql_update

            connection.execute(
                sql_update(schema)
                .where(schema.c.version == current)
                .values(version=SCHEMA_VERSION)
            )
    return {"created": not existed, "version": SCHEMA_VERSION}


def live_rate_window(window_seconds: float) -> int:
    """Return the index of the window in progress; everything below it is finished."""
    return int(time.time() // max(1.0, window_seconds))


def purge_rate_windows(*, before: int) -> int:
    """Delete rate rows for windows older than ``before``. Returns how many were removed."""
    active = engine()
    table = _table(RATE_TABLE)
    if active is None or table is None or not ready():
        return 0
    from sqlalchemy import delete

    try:
        with active.begin() as connection:
            result = connection.execute(
                delete(table).where(table.c.rate_window < before)
            )
            return int(result.rowcount or 0)
    except Exception as error:  # pragma: no cover - defensive
        _log.warning("assistant rate-window purge failed: %s", error)
        return 0


def purge_usage(*, before_day: int) -> int:
    """Delete usage rows older than ``before_day``. Returns how many were removed."""
    active = engine()
    usage = _table(USAGE_TABLE)
    if active is None or usage is None or not ready():
        return 0
    from sqlalchemy import delete

    with active.begin() as connection:
        result = connection.execute(delete(usage).where(usage.c.usage_day < before_day))
        return int(result.rowcount or 0)


class _Store:
    """Shared honesty about whether this table is usable *right now*.

    ``table_ready`` only reads the recorded schema version, and a recorded number can be
    wrong: a half-restored backup, a REVOKE on one table, a search_path that no longer
    sees it, or a migration that never ran all leave the version saying yes while every
    statement fails. Those failures are swallowed on purpose -- storage is a convenience,
    never an outage -- but swallowing them while still answering "available" leaves the
    user with a chat list that is permanently empty and no hint why.

    So a statement that fails marks the store down, and ``available`` says so until the
    cooldown lapses and the next call gets to try again. No extra round trip in the happy
    path, and an outage clears itself without a restart.
    """

    #: How long a failure suppresses the feature before another attempt is made.
    retry_after_seconds = 30.0

    def __init__(self) -> None:
        self._warned = False
        self._failed_at = 0.0

    def _usable(self, table: str) -> bool:
        if (
            self._failed_at
            and time.monotonic() - self._failed_at < self.retry_after_seconds
        ):
            return False
        return table_ready(table)

    def _worked(self) -> None:
        self._failed_at = 0.0

    def _warn(self, error: BaseException) -> None:
        # A statement that fails on the *content* of one row is not an outage, and
        # treating it as one let any user switch server-side history off for everybody
        # by sending a single character the database could not encode. The cooldown is
        # for a database that is genuinely unreachable.
        if isinstance(error, (UnicodeError, ValueError, TypeError)):
            _log.warning("%s could not store one row: %s", type(self).__name__, error)
            return
        self._failed_at = time.monotonic()
        if not self._warned:
            self._warned = True
            _log.warning("%s is unavailable: %s", type(self).__name__, error)


class DatabaseQuotaStore(_Store):
    """Per-(principal, day) token accounting shared by every API-server process."""

    @property
    def available(self) -> bool:
        """Whether the table is usable; callers fall back in process when not."""
        return self._usable(USAGE_TABLE)

    def spent(self, principal: str, day: int) -> int:
        """Return today's token spend, or ``0`` when the database cannot answer."""
        active = engine()
        usage = _table(USAGE_TABLE)
        if active is None or usage is None:
            return 0
        try:
            from sqlalchemy import select

            with active.connect() as connection:
                value = connection.execute(
                    select(usage.c.tokens).where(
                        usage.c.principal == principal, usage.c.usage_day == day
                    )
                ).scalar()
            return int(value or 0)
        except Exception as error:
            self._warn(error)
            return 0

    def charge(self, principal: str, day: int, tokens: int) -> None:
        """Add ``tokens`` to the principal's spend for ``day``.

        UPDATE-then-INSERT rather than a dialect-specific upsert: it is correct on SQLite,
        PostgreSQL and MySQL alike, and the racing INSERT is retried as an UPDATE. Each
        statement runs in its own transaction so a lost race cannot poison the next one.
        """
        active = engine()
        usage = _table(USAGE_TABLE)
        if active is None or usage is None:
            return
        try:
            if self._add(active, usage, principal, day, tokens):
                return
            try:
                from sqlalchemy import insert

                with active.begin() as connection:
                    connection.execute(
                        insert(usage).values(
                            principal=principal,
                            usage_day=day,
                            tokens=tokens,
                            requests=1,
                        )
                    )
                return
            except Exception:
                # Another worker inserted the row first; add to theirs.
                self._add(active, usage, principal, day, tokens)
        except Exception as error:
            self._warn(error)

    @staticmethod
    def _add(
        active: Engine, usage: Table, principal: str, day: int, tokens: int
    ) -> bool:
        from sqlalchemy import update

        with active.begin() as connection:
            result = connection.execute(
                update(usage)
                .where(usage.c.principal == principal, usage.c.usage_day == day)
                .values(
                    tokens=usage.c.tokens + tokens,
                    requests=usage.c.requests + 1,
                )
            )
            return bool(result.rowcount)


def quota_store() -> DatabaseQuotaStore:
    """Return the shared quota store."""
    return DatabaseQuotaStore()


def rate_store() -> DatabaseRateStore:
    """Return the shared request-rate store."""
    return DatabaseRateStore()


#: Where a chat lands when the browser did not name one -- an API client posting straight
#: to ``/query``, or a transcript stored before the picker existed.
DEFAULT_CONVERSATION = "main"

#: How long a user-chosen chat name may be. Matches the column.
MAX_TITLE = 200

#: Chats a picker will show for one principal. A bound, not a cap on how many exist: older
#: ones stay readable by id, they simply fall off the list.
MAX_CONVERSATIONS = 20

#: ``~`` is in the allowed set because this function's own output uses it as the digest
#: separator. Without it the cleaner was not a fixed point -- it stripped the separator
#: it had just written and hashed the result again -- so an id that needed normalising
#: was stored under one form and looked up under another.
_CONVERSATION_SHAPE = re.compile(r"[^A-Za-z0-9._~-]")

#: Matches the column width.
_MAX_CONVERSATION = 64


def storable_text(value: str) -> str:
    """Return ``value`` in a form the database and Fernet can both accept.

    A browser can put a lone surrogate in a question -- it survives JSON, and Python
    holds it happily -- but it has no UTF-8 encoding, so the driver raises on the way to
    the column. Repairing the character keeps the message: the alternative is dropping
    an exchange the user can see in their own window and cannot explain the loss of.
    """
    if not value:
        return value
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return value.encode("utf-8", "replace").decode("utf-8")
    return value


def clean_conversation(value: str | None) -> str:
    """Return a safe conversation id: the browser picks it, so it is never trusted.

    Restricted to a short opaque token. The id is only ever used inside a parameterised
    equality test, but it also reaches logs and the audit trail, and there is no reason for
    it to carry anything but an identifier.

    Stripping characters can map two different ids onto one string, which would silently
    merge two chats -- so anything that had to be changed keeps a digest of the original.
    An id that was already safe is returned untouched, which is every id the browser sends.

    Applying this twice must equal applying it once. It is called on the way into the
    runtime and again inside the store, and the id it returns is handed to the browser to
    send back, so a form this function will not accept unchanged is a chat nobody can
    reopen.
    """
    text = (value or "").strip()
    if not text:
        return DEFAULT_CONVERSATION
    safe = _CONVERSATION_SHAPE.sub("", text)
    if safe == text and len(text) <= _MAX_CONVERSATION:
        return text
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]
    return f"{safe[: _MAX_CONVERSATION - len(digest) - 1]}~{digest}"


#: A principal we could not identify. Several real users can collapse onto it when an auth
#: manager returns a user type we do not recognise, so a shared transcript there would be a
#: cross-account leak. Their chat stays browser-local instead.
ANONYMOUS_PRINCIPAL = "unidentified"

#: The identity of a viewer running with no auth manager at all -- the standalone preview.
#: Exactly the same argument applies: every visitor is this one principal, so nothing is
#: stored for them either. Server-side chat needs a real account, not the absence of one.
STANDALONE_PRINCIPAL = "standalone"

#: Principals that name a *situation* rather than a person. Never stored under.
UNOWNED_PRINCIPALS = frozenset({ANONYMOUS_PRINCIPAL, STANDALONE_PRINCIPAL})


class DatabaseRateStore(_Store):
    """Per-(principal, window) request counting shared by every API-server process.

    A **fixed** window, not the sliding one the in-process limiter keeps: a sliding window
    in SQL needs a row per request, and this counter exists to bound a limit that is not
    billed. The cost of the choice is a burst across a window boundary -- up to twice the
    allowance in one window's width, in the worst case -- which is acceptable for a guard
    rail against a runaway loop and is documented as such.
    """

    @property
    def available(self) -> bool:
        """Whether the table is usable; callers fall back in process when not."""
        return self._usable(RATE_TABLE)

    def spent(self, principal: str, window: int) -> int:
        """Return the requests already admitted in this window, across all workers."""
        active = engine()
        table = _table(RATE_TABLE)
        if active is None or table is None:
            return 0
        try:
            from sqlalchemy import select

            with active.connect() as connection:
                value = connection.execute(
                    select(table.c.requests).where(
                        table.c.principal == principal,
                        table.c.rate_window == window,
                    )
                ).scalar()
            return int(value or 0)
        except Exception as error:
            self._warn(error)
            return 0

    def charge(self, principal: str, window: int) -> None:
        """Record one admitted request. Same portable upsert as the token quota."""
        active = engine()
        table = _table(RATE_TABLE)
        if active is None or table is None:
            return
        try:
            if self._add(active, table, principal, window):
                return
            try:
                from sqlalchemy import insert

                with active.begin() as connection:
                    connection.execute(
                        insert(table).values(
                            principal=principal, rate_window=window, requests=1
                        )
                    )
                return
            except Exception:
                # Another worker inserted the row first; add to theirs.
                self._add(active, table, principal, window)
        except Exception as error:
            self._warn(error)

    @staticmethod
    def _add(active: Engine, table: Table, principal: str, window: int) -> bool:
        from sqlalchemy import update

        with active.begin() as connection:
            result = connection.execute(
                update(table)
                .where(table.c.principal == principal, table.c.rate_window == window)
                .values(requests=table.c.requests + 1)
            )
            return bool(result.rowcount)


class ChatHistoryStore(_Store):
    """The server-side transcript, owned by one principal.

    Every statement is filtered by ``principal``. That is the whole access-control story for
    chat history, so it is enforced here rather than left to callers.
    """

    @property
    def available(self) -> bool:
        """Whether the table is usable right now."""
        return self._usable(MESSAGE_TABLE)

    @staticmethod
    def storable(principal: str) -> bool:
        """Whether a transcript may be kept for this principal at all."""
        return bool(principal) and principal not in UNOWNED_PRINCIPALS

    def load(
        self, principal: str, *, limit: int, conversation: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the newest ``limit`` messages, oldest first.

        With no ``conversation`` this reads the principal's newest chat, which is what a
        browser opening the panel for the first time wants.
        """
        active = engine()
        table = _table(MESSAGE_TABLE)
        if active is None or table is None or not self.storable(principal):
            return []
        chat = (
            clean_conversation(conversation)
            if conversation
            else self.latest_conversation(principal)
        )
        if chat is None:
            return []
        try:
            from sqlalchemy import select

            with active.connect() as connection:
                rows = connection.execute(
                    select(
                        table.c.role,
                        table.c.content,
                        table.c.evidence,
                        table.c.total_tokens,
                    )
                    .where(
                        table.c.principal == principal,
                        table.c.conversation == chat,
                    )
                    .order_by(table.c.id.desc())
                    .limit(max(1, limit))
                ).all()
        except Exception as error:
            self._warn(error)
            return []
        return [
            {
                "role": row.role,
                "content": chatcrypto.decrypt(row.content),
                "evidence": _decode_evidence(row.evidence),
                "total_tokens": int(row.total_tokens or 0),
            }
            for row in reversed(rows)
        ]

    def latest_conversation(self, principal: str) -> str | None:
        """Return the id of the chat this principal last wrote to."""
        active = engine()
        table = _table(MESSAGE_TABLE)
        if active is None or table is None or not self.storable(principal):
            return None
        try:
            from sqlalchemy import select

            with active.connect() as connection:
                value = connection.execute(
                    select(table.c.conversation)
                    .where(table.c.principal == principal)
                    .order_by(table.c.id.desc())
                    .limit(1)
                ).scalar()
            return str(value) if value else None
        except Exception as error:
            self._warn(error)
            return None

    def conversations(self, principal: str, *, limit: int) -> list[dict[str, Any]]:
        """Return this principal's chats, newest activity first.

        The title is the chat's first question. Nothing else would identify it to the
        person who asked, and inventing one would mean another model call.
        """
        active = engine()
        table = _table(MESSAGE_TABLE)
        if active is None or table is None or not self.storable(principal):
            return []
        try:
            from sqlalchemy import func, select

            summary = (
                select(
                    table.c.conversation.label("id"),
                    func.max(table.c.id).label("last_id"),
                    func.min(table.c.id).label("first_id"),
                    func.count(table.c.id).label("messages"),
                    func.max(table.c.created_at).label("updated_at"),
                )
                .where(table.c.principal == principal)
                .group_by(table.c.conversation)
                .order_by(func.max(table.c.id).desc())
                .limit(max(1, limit))
            )
            names = _table(CONVERSATION_TABLE)
            # Resolved before a connection is held: this reads the schema table, and
            # checking it from inside an open connection means one thread holding two at
            # once. With a small pool and enough readers, every thread then waits for a
            # connection every other thread is already holding.
            has_names = names is not None and table_ready(CONVERSATION_TABLE)
            with active.connect() as connection:
                rows = connection.execute(summary).all()
                titles = {
                    row.conversation: self._label(chatcrypto.decrypt(row.content))
                    for row in connection.execute(
                        select(table.c.conversation, table.c.content).where(
                            table.c.id.in_([row.first_id for row in rows] or [-1])
                        )
                    ).all()
                }
                if has_names and names is not None:
                    # A name the user chose wins over the opening question.
                    titles.update(
                        {
                            row.conversation: chatcrypto.decrypt(row.title)
                            for row in connection.execute(
                                select(names.c.conversation, names.c.title).where(
                                    names.c.principal == principal
                                )
                            ).all()
                        }
                    )
        except Exception as error:
            self._warn(error)
            return []
        return [
            {
                "id": row.id,
                "title": titles.get(row.id, ""),
                "messages": int(row.messages or 0),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

    @staticmethod
    def _label(title: str) -> str:
        """Return a chat label: one line, bounded, whatever it was derived from.

        A chosen title and one derived from the opening question end up in the same
        column of the same list, so they are shaped the same way here rather than in
        two places that drifted apart.
        """
        return " ".join(str(title or "").split())[:MAX_TITLE]

    def rename(self, principal: str, conversation: str, title: str) -> int:
        """Give one chat a name of the user's own, or clear it back to the default.

        Filtered by principal like every other statement here: a guessed id belonging to
        someone else matches no row, so it can neither be read nor relabelled.
        """
        active = engine()
        table = _table(CONVERSATION_TABLE)
        messages = _table(MESSAGE_TABLE)
        if active is None or table is None or messages is None:
            return 0
        if not self.storable(principal):
            return 0
        chat = clean_conversation(conversation)
        clean = storable_text(self._label(title))
        try:
            from sqlalchemy import delete, func, insert, select, update

            with active.begin() as connection:
                owns = connection.execute(
                    select(func.count(messages.c.id)).where(
                        messages.c.principal == principal,
                        messages.c.conversation == chat,
                    )
                ).scalar()
                if not owns:
                    return 0
                if not clean:
                    result = connection.execute(
                        delete(table).where(
                            table.c.principal == principal,
                            table.c.conversation == chat,
                        )
                    )
                    return int(result.rowcount or 0) or 1
                changed = connection.execute(
                    update(table)
                    .where(
                        table.c.principal == principal,
                        table.c.conversation == chat,
                    )
                    .values(title=chatcrypto.encrypt(clean))
                )
                if not changed.rowcount:
                    connection.execute(
                        insert(table).values(
                            principal=principal,
                            conversation=chat,
                            title=chatcrypto.encrypt(clean),
                        )
                    )
                return 1
        except Exception as error:
            self._warn(error)
            return 0

    def append(
        self,
        principal: str,
        question: str,
        answer: str,
        evidence: list[dict[str, Any]],
        total_tokens: int,
        conversation: str = DEFAULT_CONVERSATION,
    ) -> None:
        """Store one completed exchange."""
        active = engine()
        table = _table(MESSAGE_TABLE)
        if active is None or table is None or not self.storable(principal):
            return
        if not question or not answer:
            return
        chat = clean_conversation(conversation)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            from sqlalchemy import insert

            with active.begin() as connection:
                connection.execute(
                    insert(table),
                    [
                        {
                            "principal": principal,
                            "conversation": chat,
                            "role": "user",
                            "content": chatcrypto.encrypt(storable_text(question)),
                            "evidence": None,
                            "total_tokens": 0,
                            "created_at": now,
                        },
                        {
                            "principal": principal,
                            "conversation": chat,
                            "role": "assistant",
                            "content": chatcrypto.encrypt(storable_text(answer)),
                            "evidence": json.dumps(evidence, ensure_ascii=False)
                            if evidence
                            else None,
                            "total_tokens": max(0, total_tokens),
                            "created_at": now,
                        },
                    ],
                )
        except Exception as error:
            self._warn(error)

    def clear(self, principal: str, *, conversation: str | None = None) -> int:
        """Delete this principal's messages -- one chat, or all of them. Returns how many."""
        active = engine()
        table = _table(MESSAGE_TABLE)
        if active is None or table is None or not principal:
            return 0
        # Cleaned here as well as on write: `clear` is reached both from the runtime,
        # which cleans, and directly, which does not. Only a non-empty id is cleaned --
        # the cleaner maps "" onto the default conversation, which would turn a blank
        # parameter into "delete this user's main chat".
        chat = clean_conversation(conversation) if conversation else conversation
        try:
            from sqlalchemy import delete

            statement = delete(table).where(table.c.principal == principal)
            names = _table(CONVERSATION_TABLE)
            # Same reason as in `conversations`: never hold two connections at once.
            has_names = names is not None and table_ready(CONVERSATION_TABLE)
            titles = None
            if names is not None:
                titles = delete(names).where(names.c.principal == principal)
                if chat is not None:
                    titles = titles.where(names.c.conversation == chat)
            if chat is not None:
                statement = statement.where(table.c.conversation == chat)
            with active.begin() as connection:
                result = connection.execute(statement)
                if titles is not None and has_names:
                    # Otherwise a new chat reusing the id inherits a stranger's label.
                    connection.execute(titles)
                return int(result.rowcount or 0)
        except Exception as error:
            self._warn(error)
            return 0


def _decode_evidence(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def history_store() -> ChatHistoryStore:
    """Return the shared chat-history store."""
    return ChatHistoryStore()


def purge_history(*, before: datetime) -> int:
    """Delete stored messages written before ``before``. Returns how many were removed."""
    active = engine()
    table = _table(MESSAGE_TABLE)
    if active is None or table is None or not ready():
        return 0
    from sqlalchemy import delete

    cutoff = before.astimezone(timezone.utc).replace(tzinfo=None)
    with active.begin() as connection:
        result = connection.execute(delete(table).where(table.c.created_at < cutoff))
        return int(result.rowcount or 0)


def encryption_summary() -> str:
    """One line describing what encryption is doing right now, for the CLI.

    Written once and printed by both `status` and `doctor`: a mistyped Fernet key used
    to be visible nowhere but a warning in the API server's log, and the log is not
    where anyone looks when the question is whether the chat is encrypted.
    """
    state = chatcrypto.status()
    if state["history_encrypted"]:
        return "on, with the Fernet key Airflow uses for connections"
    if not state["fernet_key_configured"]:
        return "off: no Fernet key is configured, so the transcript is stored as plain text"
    if not state["fernet_key_usable"]:
        return (
            "off: a Fernet key is configured but cannot be used (check the value); "
            "the transcript is stored as plain text"
        )
    return (
        f"off: switched off with {chatcrypto.ENCRYPT_ENV}; the transcript is stored as "
        "plain text"
    )


#: Rows read and rewritten per transaction while re-keying. The whole table is not held
#: in memory, and a run interrupted halfway leaves every committed batch already under
#: the new key -- re-running finishes the job, because a row already re-encrypted simply
#: decrypts and re-encrypts again.
_ROTATE_BATCH = 500


def rotate_history_key() -> dict[str, int]:
    """Re-encrypt stored chat with the Fernet key that is configured right now.

    Sharing Airflow's key means inheriting Airflow's rotation procedure -- new key first,
    ``airflow rotate-fernet-key``, then drop the old key -- and that command re-encrypts
    Airflow's own connections and variables. It knows nothing about this table, so the
    last step used to take every transcript with it. Run this while both keys are still
    listed and the chat moves across with them.

    A row that cannot be read is counted and left exactly as it is. Writing the
    placeholder back would be the one irreversible thing here: the key it needs may still
    turn up, and a row that was skipped can still be recovered by listing that key again.
    """
    active = engine()
    messages = _table(MESSAGE_TABLE)
    conversations = _table(CONVERSATION_TABLE)
    moved = {"messages": 0, "titles": 0, "unreadable": 0}
    if active is None or messages is None or not ready():
        return moved
    from sqlalchemy import and_, or_, select, update

    def after(keys: tuple[Any, ...], cursor: tuple[Any, ...]) -> Any:
        """``(k1, k2) > (c1, c2)``, written without a row-value comparison.

        ``tuple_()`` renders one, and the databases Airflow supports do accept it -- but
        this is the statement that rewrites every stored message, and an unsupported
        construct here fails an operator halfway through a key rotation. The expanded
        form is the same predicate in terms every dialect has always had.
        """
        return or_(
            *[
                and_(
                    *[keys[before] == cursor[before] for before in range(index)],
                    keys[index] > cursor[index],
                )
                for index in range(len(keys))
            ]
        )

    def rekey(table: Any, column: Any, keys: tuple[Any, ...], counter: str) -> None:
        """Walk one table by its primary key, rewriting a column batch by batch."""
        cursor: tuple[Any, ...] | None = None
        while True:
            with active.begin() as connection:
                query = select(*keys, column).order_by(*keys).limit(_ROTATE_BATCH)
                if cursor is not None:
                    query = query.where(after(keys, cursor))
                rows = connection.execute(query).all()
                if not rows:
                    return
                cursor = tuple(rows[-1][: len(keys)])
                for row in rows:
                    # `read`, not `decrypt`: the placeholder is a sentence somebody can
                    # type, so the text alone cannot say whether this row is lost or
                    # merely talking about being lost.
                    plain, readable = chatcrypto.read(row[-1])
                    if not readable:
                        moved["unreadable"] += 1
                        continue
                    connection.execute(
                        update(table)
                        .where(
                            *[
                                key == value
                                for key, value in zip(
                                    keys, row[: len(keys)], strict=True
                                )
                            ]
                        )
                        .values({column.key: chatcrypto.encrypt(plain)})
                    )
                    moved[counter] += 1

    rekey(messages, messages.c.content, (messages.c.id,), "messages")
    if conversations is not None and table_ready(CONVERSATION_TABLE):
        rekey(
            conversations,
            conversations.c.title,
            (conversations.c.principal, conversations.c.conversation),
            "titles",
        )
    return moved


#: The principal the doctor writes its round-trip probe under. Not a real identity, so
#: nothing it leaves behind could be mistaken for a person's chat.
DOCTOR_PRINCIPAL = "airflow-pytest-plugin-doctor"


def _stored_messages() -> int:
    """How many chat messages are in the table right now, for the CLI to report."""
    active = engine()
    table = _table(MESSAGE_TABLE)
    if active is None or table is None or not table_ready(MESSAGE_TABLE):
        return 0
    try:
        from sqlalchemy import func, select

        with active.connect() as connection:
            return int(connection.execute(select(func.count(table.c.id))).scalar() or 0)
    except Exception:  # pragma: no cover - defensive
        return 0


def _doctor(state: dict[str, Any]) -> int:
    """Walk the preconditions for saving a chat, in order, and name the first that fails.

    "Nothing is written to the database" has several possible causes -- a URL that points
    somewhere else, an unreachable server, tables that were never created, retention
    switched off, or a write that fails -- and they need different fixes. Checking them in
    order and stopping at the first failure turns a support conversation into one command.
    """
    from .assistant.settings import AssistantSettings

    print(f"1. Database URL      : {state['url'] or '(none resolved)'}")
    if not state["configured"]:
        print(
            f"   -> Nothing is configured. Set {DB_URL_ENV} or {DB_CONN_ID_ENV}, or run "
            "this inside Airflow so its metadata database is used."
        )
        return 1
    if not state["reachable"]:
        print(f"   -> The database could not be reached:\n      {state['reason']}")
        return 1
    print("2. Reachable         : yes")

    version = state["version"]
    if version is None:
        print(
            "3. Tables            : missing\n"
            "   -> Run: python -m airflow_pytest_plugin.db upgrade"
        )
        return 1
    print(
        f"3. Tables            : present at version {version} "
        f"(this build expects {state['expected_version']})"
    )
    if version < state["expected_version"]:
        print("   -> Run: python -m airflow_pytest_plugin.db upgrade")
        return 1

    # The recorded number and the real shape can disagree: a build that adds a column has
    # to alter an existing table, and a version written without that migration having run
    # leaves every insert failing where it is caught and swallowed.
    active = engine()
    missing = _missing_columns(active) if active is not None else {}
    if missing:
        for name, columns in missing.items():
            print(
                f"   -> {name} says version {version} but is missing "
                f"{', '.join(columns)}."
            )
        print("      Run: python -m airflow_pytest_plugin.db upgrade")
        return 1

    days = AssistantSettings.from_env().history_days
    if days <= 0:
        print(
            "4. Chat history      : switched off\n"
            "   -> AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS is 0, so nothing is stored on "
            "purpose. Set it to a number of days."
        )
        return 1
    print(f"4. Chat history      : on, kept for {days} day(s)")

    store = ChatHistoryStore()
    if not store.available:
        print(
            "5. Write probe       : the message table is not usable from this process."
        )
        return 1
    store.clear(DOCTOR_PRINCIPAL)
    store.append(DOCTOR_PRINCIPAL, "doctor probe", "doctor probe", [], 0)
    written = store.load(DOCTOR_PRINCIPAL, limit=2)
    store.clear(DOCTOR_PRINCIPAL)
    if len(written) != 2:
        print(
            "5. Write probe       : FAILED -- the row could not be written and read back.\n"
            "   -> Check that this database user may INSERT and SELECT on "
            f"{MESSAGE_TABLE}."
        )
        return 1
    print("5. Write probe       : wrote and read back a message, then removed it")
    print(f"6. Encryption        : {encryption_summary()}")
    print(
        "\nStorage is working. If chats still do not appear, the acting user is the last "
        "thing to check:\n"
        "  - open /api/assistant/status in the browser that is signed in;\n"
        '  - "history_server_side": true means this user\'s chats are being saved;\n'
        "  - false means the auth manager gives no unique account key for them (or there "
        "is no auth manager at all), and their chat stays in the browser."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """``python -m airflow_pytest_plugin.db`` -- create or inspect the plugin's tables."""
    parser = argparse.ArgumentParser(
        prog="python -m airflow_pytest_plugin.db",
        description=(
            "Manage the plugin's own tables. They live in Airflow's metadata database "
            f"unless {DB_URL_ENV} points elsewhere, and are always prefixed "
            f"'{TABLE_PREFIX}'."
        ),
    )
    parser.add_argument(
        "command",
        choices=("upgrade", "status", "purge", "doctor", "rotate-key"),
        help=(
            "upgrade: create missing tables. status: report what is configured. "
            "purge: delete stored chat messages past retention. "
            "doctor: work out why chats are not being saved. "
            "rotate-key: re-encrypt stored chat with the current Fernet key."
        ),
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=None,
        help="purge only: retention in days (default: AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS).",
    )
    args = parser.parse_args(argv)

    state = status()
    if not state["configured"]:
        if os.environ.get(DB_CONN_ID_ENV, "").strip():
            print(
                f"The Airflow connection named by {DB_CONN_ID_ENV} "
                f"({os.environ[DB_CONN_ID_ENV].strip()!r}) could not be resolved.\n"
                "Check that the connection exists and that this process can reach the "
                "configured secrets backend."
            )
            return 1
        if state["reason"]:
            print(
                "Airflow's metadata database could not be resolved:\n"
                f"  {state['reason']}\n"
                f"Fix that, or point the plugin elsewhere with {DB_URL_ENV} or "
                f"{DB_CONN_ID_ENV}."
            )
            return 1
        print(
            "No database is configured.\n"
            f"Set {DB_URL_ENV} or {DB_CONN_ID_ENV}, or run this inside an Airflow "
            "environment so the metadata database is used."
        )
        return 1

    if args.command == "purge":
        if not state["ready"]:
            print("Nothing to purge: the tables do not exist yet.")
            return 1
        from .assistant.settings import AssistantSettings

        settings = AssistantSettings.from_env()
        stale = purge_rate_windows(
            before=live_rate_window(settings.rate_window_seconds)
        )
        if stale:
            print(f"Deleted {stale} finished rate-limit window(s).")
        days = args.history_days
        if days is None:
            days = settings.history_days
            if days <= 0:
                # Switching the feature off does not delete what it already wrote, and
                # refusing to run left those rows with no way out but hand-written SQL.
                # Deleting them unasked would be worse, so say what is there and how.
                left = _stored_messages()
                if left:
                    print(
                        f"Server-side chat history is switched off, but {left} message(s) "
                        "written while it was on are still stored.\n"
                        "Remove them with: python -m airflow_pytest_plugin.db purge "
                        "--history-days 0"
                    )
                else:
                    print(
                        "Server-side chat history is switched off; nothing is stored."
                    )
                return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))
        removed = purge_history(before=cutoff)
        if days <= 0:
            print(f"Deleted all {removed} stored chat message(s).")
        else:
            print(f"Deleted {removed} chat message(s) older than {days} day(s).")
        return 0

    if args.command == "rotate-key":
        if not state["ready"]:
            print("Nothing to re-encrypt: the tables do not exist yet.")
            return 1
        crypto = chatcrypto.status()
        if crypto["fernet_key_configured"] and not crypto["fernet_key_usable"]:
            print(
                "A Fernet key is configured but cannot be used -- check it before "
                "re-encrypting, or this would store the transcript as plain text."
            )
            return 1
        if not crypto["history_encrypted"]:
            # Coherent and occasionally wanted -- reading the table during an incident --
            # but never by accident, so it is said out loud rather than done quietly.
            print(
                "Encryption is off, so this will store the transcript as PLAIN TEXT.\n"
                f"Set a Fernet key (and leave {chatcrypto.ENCRYPT_ENV} unset) to "
                "re-encrypt instead."
            )
        moved = rotate_history_key()
        # "Re-encrypted" would be a lie in the plain-text mode above, and this line is
        # the only record of what the command did.
        verb = (
            "Re-encrypted" if crypto["history_encrypted"] else "Rewrote in plain text"
        )
        print(
            f"{verb} {moved['messages']} message(s) and {moved['titles']} chat name(s)."
        )
        if moved["unreadable"]:
            print(
                f"Left {moved['unreadable']} row(s) untouched: their key is not among "
                "the configured ones. List that key as well and run this again to bring "
                "them across -- they are still recoverable."
            )
        return 0

    if args.command == "doctor":
        return _doctor(state)

    if args.command == "status":
        if not state["reachable"]:
            print(f"Database {state['url']} could not be reached:\n  {state['reason']}")
            return 1
        if not state["ready"]:
            # An empty database and an out-of-date one both need `upgrade`, but only one
            # of them is missing everything -- saying "not initialised" to an operator
            # whose chat history is right there sends them looking for a second database.
            if state["version"] is None:
                print(
                    f"Database {state['url']} is reachable but not initialised.\n"
                    "Run: python -m airflow_pytest_plugin.db upgrade"
                )
            else:
                print(
                    f"Database {state['url']} is at schema version "
                    f"{state['version']}; this build expects "
                    f"{state['expected_version']}.\n"
                    "Run: python -m airflow_pytest_plugin.db upgrade"
                )
            return 1
        print(f"Database {state['url']} is ready at version {state['version']}.")
        from .assistant.settings import AssistantSettings

        days = AssistantSettings.from_env().history_days
        print(
            f"Chat history: {'stored for ' + str(days) + ' day(s)' if days else 'off'}.\n"
            f"Encryption: {encryption_summary()}."
        )
        if state["version"] != SCHEMA_VERSION:
            print(f"This build expects version {SCHEMA_VERSION}; run upgrade.")
            return 1
        return 0

    try:
        result = upgrade()
    except Exception as error:
        print(f"Could not create the tables: {error}")
        return 1
    print(
        f"Tables {'created' if result['created'] else 'already present'} at "
        f"version {result['version']} in {status()['url']}."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ANONYMOUS_PRINCIPAL",
    "STANDALONE_PRINCIPAL",
    "UNOWNED_PRINCIPALS",
    "DEFAULT_CONVERSATION",
    "MAX_CONVERSATIONS",
    "MAX_TITLE",
    "clean_conversation",
    "DatabaseRateStore",
    "CONVERSATION_TABLE",
    "RATE_TABLE",
    "live_rate_window",
    "DOCTOR_PRINCIPAL",
    "purge_rate_windows",
    "rate_store",
    "DB_CONN_ID_ENV",
    "DB_URL_ENV",
    "METADATA",
    "SCHEMA_VERSION",
    "TABLE_PREFIX",
    "ChatHistoryStore",
    "DatabaseQuotaStore",
    "configured_url",
    "history_store",
    "engine",
    "main",
    "purge_history",
    "table_ready",
    "live_rate_window",
    "DOCTOR_PRINCIPAL",
    "purge_rate_windows",
    "purge_usage",
    "quota_store",
    "ready",
    "recorded_version",
    "reset_engine",
    "status",
    "upgrade",
]
