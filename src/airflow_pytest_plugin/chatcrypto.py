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

"""Encryption at rest for stored chat, using the Fernet key Airflow already has.

A transcript is not metadata. The questions quote failing tests and the answers quote
tracebacks and captured output, so the chat table holds the same class of material as a
connection password -- and Airflow encrypts those with a key every deployment already
configures. This uses the same key, through Airflow's own helper where it is importable,
so rotation (``fernet_key`` as a comma-separated list) works exactly as it does for
connections: the first key encrypts, any of them decrypts.

Two properties matter more than the encryption itself:

* **A database written before this existed still reads.** Nothing is marked or migrated.
  A stored value is decrypted only when it *is* a Fernet token, and plaintext is returned
  unchanged, so the feature arrives without a rewrite and without a flag day.
* **An unreadable row is unreadable alone.** A key that was rotated away takes its rows
  with it, and each one becomes a placeholder rather than an exception that would empty
  the whole chat window.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import threading
from typing import Any

_log = logging.getLogger(__name__)

#: Set to a false value to store the transcript as plain text even when a key exists.
#: Wanted rarely -- reading the table directly during an incident -- and it only affects
#: what is written from then on, because decryption is decided per row.
ENCRYPT_ENV = "AIRFLOW_PYTEST_ASSISTANT_ENCRYPT_HISTORY"

_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

#: Every Fernet token is urlsafe base64 of a payload whose first byte is 0x80, so they all
#: begin "gAAAAA". Requiring the whole value to be one long token is what lets plaintext
#: and ciphertext share a column: no marker to collide with a title someone typed, and no
#: migration to run over rows written before this module existed.
_TOKEN = re.compile(r"^gAAAAA[A-Za-z0-9_\-]{40,}={0,2}$")

#: version(1) + timestamp(8) + IV(16) + one AES block(16) + HMAC(32). Shape alone is not
#: enough to call a value ciphertext: somebody asking "why does gAAAAAB... fail?" types a
#: string that starts the same way, and answering them with the placeholder would delete
#: their message in front of them.
_TOKEN_BYTES = 73

#: What a reader sees in place of a message whose key is gone. Deliberately a sentence:
#: it is shown in the chat window and it is the only explanation anyone will get.
UNREADABLE = "[unreadable: encrypted with a Fernet key this server does not have]"

#: The cache is one (key, fernet) pair rather than two names, so a reader can never see a
#: fernet paired with the key it was not built from. Every API-server worker encrypts on
#: the request thread, so this is read concurrently on every stored answer.
_cache_lock = threading.Lock()
_cached: tuple[str, Any] | None = None


def _configured_key() -> str:
    """Return the raw Fernet key setting, empty when there is none."""
    for name in ("AIRFLOW__CORE__FERNET_KEY", "FERNET_KEY"):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    try:
        from airflow.configuration import conf

        return str(conf.get("core", "fernet_key", fallback="") or "").strip()
    except Exception:  # pragma: no cover - Airflow absent or misconfigured
        return ""


def _fernet() -> Any | None:
    """Return a MultiFernet for the configured key, or ``None`` when there is none.

    Cached against the key itself rather than built once: an operator who rotates the key
    restarts the API server, but a test -- and a reload -- must not be served a stale one.
    """
    global _cached
    key = _configured_key()
    if not key:
        _cached = None
        return None
    cached = _cached
    if cached is not None and cached[0] == key:
        return cached[1]
    try:
        from cryptography.fernet import Fernet, MultiFernet

        keys = [part.strip() for part in key.split(",") if part.strip()]
        built = MultiFernet([Fernet(part) for part in keys])
    except Exception as error:
        # A malformed key is the operator's to fix, but it must not take the assistant
        # down: the transcript falls back to plain text and says so in the log.
        _log.warning("assistant chat encryption is unavailable: %s", error)
        _cached = None
        return None
    with _cache_lock:
        _cached = (key, built)
    return built


def enabled() -> bool:
    """Whether newly stored chat will be encrypted."""
    raw = os.environ.get(ENCRYPT_ENV)
    if raw is not None and raw.strip().lower() in _FALSE_VALUES:
        return False
    return _fernet() is not None


def encrypt(value: str) -> str:
    """Return ``value`` as a Fernet token, or unchanged when no key is configured."""
    if not value or not enabled():
        return value
    fernet = _fernet()
    if fernet is None:  # pragma: no cover - enabled() already proved otherwise
        return value
    try:
        token: bytes = fernet.encrypt(value.encode("utf-8"))
        return token.decode("ascii")
    except Exception as error:  # pragma: no cover - defensive
        _log.warning("assistant chat could not be encrypted: %s", error)
        return value


def _is_token(value: str) -> bool:
    """Whether ``value`` is structurally a Fernet token, not merely shaped like one."""
    if not _TOKEN.match(value):
        return False
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error):
        return False
    return len(raw) >= _TOKEN_BYTES and raw[0] == 0x80


def decrypt(value: str | None) -> str:
    """Return the plain text of a stored value, whether or not it was encrypted."""
    if not value:
        return value or ""
    if not _is_token(value):
        # Written before this module existed, written with encryption switched off, or
        # simply a message that happens to start the way a token does.
        return value
    fernet = _fernet()
    if fernet is None:
        return UNREADABLE
    try:
        plain: bytes = fernet.decrypt(value.encode("ascii"))
        return plain.decode("utf-8")
    except Exception:
        # Either a key that was rotated away, or -- vanishingly unlikely -- a plain
        # string shaped exactly like a token. Neither is worth an exception that would
        # empty the reader's whole chat window.
        return UNREADABLE


def status() -> dict[str, Any]:
    """Describe the current setting for the operator-facing status endpoint."""
    return {"history_encrypted": enabled(), "fernet_key_configured": bool(_fernet())}


__all__ = ["ENCRYPT_ENV", "UNREADABLE", "decrypt", "enabled", "encrypt", "status"]
