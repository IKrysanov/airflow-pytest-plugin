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
_SECRET_ENV_NAME = re.compile(
    r"(?i)(secret|token|password|passwd|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|credential|auth|session)"
)

_PEM = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*){2,4}")
_URL_CREDENTIAL = re.compile(
    r"([a-zA-Z][\w+.\-]{0,39}://[^\s:/@]{1,256}:)([^\s@/]{1,256})(@)"
)
_AUTHORIZATION = re.compile(
    r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?(?:[A-Za-z]+\s+)?)\S+"
)
_BEARER = re.compile(r"(?i)((?:bearer|basic)\s+)\S+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"client[_-]?secret|private[_-]?key|auth|credential)s?[\"']?\s*[=:]\s*[\"']?)"
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
    return _OPAQUE_TOKEN.sub(_REDACTED, text)


def safe_node_id(node_id: str) -> str:
    """Redact secrets in parametrization while retaining the test selector."""
    return _NODE_PARAMETERS.sub(
        lambda match: redact_text(match.group(0)),
        node_id,
    )


def _redact_environment_values(text: str) -> str:
    for key, value in os.environ.items():
        if key in _SAFE_ENV_KEYS or _looks_like_path(value):
            continue
        minimum_length = 4 if _SECRET_ENV_NAME.search(key) else 8
        if len(value) < minimum_length or value not in text:
            continue
        whole_value = rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])"
        text = re.sub(whole_value, _REDACTED, text)
    return text


def _looks_like_path(value: str) -> bool:
    if value.startswith(("/", "~")):
        return True
    return len(value) >= 3 and value[1] == ":" and value[2] in "\\/"


__all__ = ["redact_text", "safe_node_id"]
