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

"""Best-effort secret redaction owned by the API-server assistant."""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager

_REDACTED = "[REDACTED]"
_SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "PWD",
        "OLDPWD",
        "SHELL",
        "USER",
        "LOGNAME",
        "HOSTNAME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TMP",
        "TEMP",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "PYENV_ROOT",
        "SSH_AUTH_SOCK",
        "_",
    }
)
#: Whole words in a variable's *name* that make its value a secret whatever it looks like.
#: Matched as words rather than substrings, so ``MONKEY_PATCH`` is not a key and
#: ``AIRFLOW__CORE__FERNET_KEY`` is -- the old pattern wanted ``api_key`` or ``access_key``
#: spelled out and let a bare ``KEY`` through to be caught by length alone.
_SECRET_NAME_WORDS = frozenset(
    """
    secret secrets token tokens password passwords passwd pwd key keys apikey
    credential credentials auth session salt signature private cert conn dsn
    """.split()
)
#: An acronym run first, so ``ANTHROPIC_API_KEY`` splits into three words rather than
#: fifteen single letters; ``MonkeyPatch`` still splits on the camel hump.
_NAME_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Za-z][a-z0-9]*")

#: A value shorter than this is not redacted from free text even when its variable is
#: named like a secret. Below it the collateral damage exceeds the protection: the stock
#: ``docker-compose.yaml`` for Airflow ships ``POSTGRES_PASSWORD=airflow``, and deleting
#: every occurrence of "airflow" from a plugin *for Airflow* costs more than it saves.
#: Real credentials are longer than this, and the shape patterns above catch the prefixed
#: ones (``sk-``, ``ghp_``, …) at any length.
_MIN_ENV_SECRET = 8

_PEM = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*){2,4}")
_URL_CREDENTIAL = re.compile(
    r"([a-zA-Z][\w+.\-]{0,39}://[^\s:/@]{1,256}:)([^\s@/]{1,256})(@)"
)
#: A colon that is not part of ``::``. A double colon separates a module from a test --
#: ``tests.auth::test_login`` -- and reading that as ``auth = test_login`` deleted the
#: name of the test from the question, the prompt, the transcript and the answer. An
#: assignment in a log line or a config dump uses one colon or an equals sign.
_ASSIGNS = r"(?::(?!:)|=)"

_AUTHORIZATION = re.compile(
    r"(?i)(authorization[\"']?\s*" + _ASSIGNS + r"\s*[\"']?(?:[A-Za-z]+\s+)?)\S+"
)
_BEARER = re.compile(r"(?i)((?:bearer|basic)\s+)\S+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"client[_-]?secret|private[_-]?key|auth|credential)s?[\"']?\s*"
    + _ASSIGNS
    + r"\s*[\"']?)"
    r"([^\s\"',]+)"
)
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_NODE_PARAMETERS = re.compile(r"\[.*\]")

_PREFIXED_TOKENS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[opsur]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{35}"),
    re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bSG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{30,}"),
    re.compile(r"\bpypi-[A-Za-z0-9_-]{40,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}"),
    re.compile(r"\bdckr_pat_[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bdapi[0-9a-f]{32,}"),
)
_OPAQUE_TOKEN = re.compile(r"(?<![A-Za-z0-9+])[A-Za-z0-9+]{20,}={0,2}(?![A-Za-z0-9+=])")

# A long alphanumeric run is only treated as an opaque credential when it does not read
# as concatenated words. Test reports are made of identifiers, and a class name such as
# ``TestReportArchiveIntegration`` is exactly the fact an answer has to cite -- the same
# scrubber also runs over the user's own question, so a false positive silently removes
# the subject of the request. Measured on random base62 tokens this still redacts 94% of
# 20-character and 99% of 40-character secrets, and every hex key.
_WORD_SHAPE = re.compile(r"[A-Z]?[a-z]{2,}")
_WORD_SHAPE_RATIO = 0.65

#: The same test applied to an environment *value* can afford to be stricter, and the
#: difference is worth having: measured over 6000 random credentials, 53 read enough like
#: words to survive at 0.65 and 1 at 0.80 -- while 28 values a real Airflow deployment
#: sets (``LocalExecutor``, ``checkout-api``, ``dag_id_checkout_nightly``) are judged
#: exactly the same at both. The looser bar has to stay for free text, where the string
#: under test is one token out of a report rather than a whole configured value.
_ENV_WORD_SHAPE_RATIO = 0.80


def _looks_like_opaque_secret(token: str, ratio: float = _WORD_SHAPE_RATIO) -> bool:
    covered = sum(len(word) for word in _WORD_SHAPE.findall(token))
    return covered < ratio * len(token)


def _is_secret_name(key: str) -> bool:
    """Whether a variable's name says its value is a credential."""
    return any(word.lower() in _SECRET_NAME_WORDS for word in _NAME_WORDS.findall(key))


def _redact_opaque_tokens(text: str) -> str:
    return _OPAQUE_TOKEN.sub(
        lambda match: (
            _REDACTED if _looks_like_opaque_secret(match.group(0)) else match.group(0)
        ),
        text,
    )


def redact_text(text: str) -> str:
    """Scrub common credentials and secret environment values from text."""
    if not text:
        return text
    text = _redact_environment_values(text)
    text = _PEM.sub(_REDACTED, text)
    text = _JWT.sub(_REDACTED, text)
    text = _URL_CREDENTIAL.sub(r"\g<1>" + _REDACTED + r"\g<3>", text)
    text = _AUTHORIZATION.sub(r"\g<1>" + _REDACTED, text)
    text = _BEARER.sub(r"\g<1>" + _REDACTED, text)
    text = _SECRET_ASSIGNMENT.sub(r"\g<1>" + _REDACTED, text)
    text = _AWS_ACCESS_KEY.sub(_REDACTED, text)
    for pattern in _PREFIXED_TOKENS:
        text = pattern.sub(_REDACTED, text)
    return _redact_opaque_tokens(text)


def safe_node_id(node_id: str) -> str:
    """Redact secrets in parametrization while retaining the test selector."""
    return _NODE_PARAMETERS.sub(
        lambda match: redact_text(match.group(0)),
        node_id,
    )


_matcher_lock = threading.Lock()
_matcher_cache: tuple[dict[str, str], re.Pattern[str] | None] | None = None
# A one-element tuple boxes the pinned matcher so that "pinned to no secrets at all" stays
# distinguishable from "not pinned".
_pinned = threading.local()


@contextmanager
def environment_snapshot() -> Iterator[None]:
    """Pin the environment matcher for the duration of one assistant request.

    Redaction runs on every report field, so the full-tree path scrubs tens of thousands
    of short strings per request. Deriving the secret list from ``os.environ`` each time
    dominated the cost -- with 200 variables it was ~200 us per call, minutes of CPU for
    one request. Inside this scope the compiled alternation is built once. Outside it
    every call still revalidates against the live environment, so callers that are not
    one bounded request never see a stale matcher.
    """
    previous = getattr(_pinned, "matcher", None)
    _pinned.matcher = (_environment_matcher(),)
    try:
        yield
    finally:
        _pinned.matcher = previous


def _environment_matcher() -> re.Pattern[str] | None:
    global _matcher_cache
    environment = dict(os.environ)
    cached = _matcher_cache
    if cached is not None and cached[0] == environment:
        return cached[1]
    matcher = _build_environment_matcher(environment)
    with _matcher_lock:
        _matcher_cache = (environment, matcher)
    return matcher


def _build_environment_matcher(
    environment: dict[str, str],
) -> re.Pattern[str] | None:
    values: list[str] = []
    for key, value in environment.items():
        if key in _SAFE_ENV_KEYS or _looks_like_path(value):
            continue
        if len(value) < _MIN_ENV_SECRET:
            continue
        # An API server is configured almost entirely through the environment, so "long
        # enough to be a secret" made secrets of the provider name, the executor and every
        # other setting -- and those words then disappeared from the reports, the
        # questions and the answers. A value earns redaction by the name it is stored
        # under or by not reading like configuration; the shape patterns above are the
        # net for anything that is a credential regardless of where it came from.
        if _is_secret_name(key) or _looks_like_opaque_secret(
            value, _ENV_WORD_SHAPE_RATIO
        ):
            values.append(value)
    if not values:
        return None
    # Longest first so the alternation cannot stop at a shorter secret that happens to
    # be a prefix of a longer one.
    values.sort(key=len, reverse=True)
    alternation = "|".join(re.escape(value) for value in values)
    return re.compile(rf"(?<![A-Za-z0-9_])(?:{alternation})(?![A-Za-z0-9_])")


def _redact_environment_values(text: str) -> str:
    pinned: tuple[re.Pattern[str] | None] | None = getattr(_pinned, "matcher", None)
    matcher = pinned[0] if pinned is not None else _environment_matcher()
    return matcher.sub(_REDACTED, text) if matcher is not None else text


def _looks_like_path(value: str) -> bool:
    if value.startswith(("/", "~")):
        return True
    return len(value) >= 3 and value[1] == ":" and value[2] in "\\/"


__all__ = ["environment_snapshot", "redact_text", "safe_node_id"]
