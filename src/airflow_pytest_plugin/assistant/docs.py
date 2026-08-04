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

"""Product documentation an operator supplies, and the part of it a question needs.

The short PRODUCT block in the system prompt says what the two packages are. It cannot say
what parameters ``PytestOperator`` takes, because that documentation lives in another
package -- and a model asked to fill that gap from memory will invent a plausible,
confident, wrong answer, which is the one outcome this whole feature is built to avoid.

So the deployment supplies the files (``AIRFLOW_PYTEST_ASSISTANT_DOCS``) and this module
decides which parts of them travel with a given question. Selection is deterministic term
overlap rather than embeddings: no model call, no index to maintain, no second thing to be
wrong. Documentation that answers nothing scores nothing and is not sent, so the common
case -- a question about the user's own runs -- pays nothing for the feature.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .redaction import redact_text

_log = logging.getLogger(__name__)

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|[А-Яа-яЁё]{3,}")

#: Words that appear in every question and would make everything look equally relevant.
_STOPWORDS = frozenset(
    """
    the and for are with that this what which how why when does can from you your
    как что где для чтобы если это или так тебя ваши какие есть быть
    """.split()
)


@dataclass(frozen=True)
class DocSection:
    """One heading and the text under it."""

    title: str
    body: str
    source: str

    @property
    def text(self) -> str:
        """Return the section rendered for the prompt."""
        return f"### {self.title}\n{self.body}".strip()

    @property
    def terms(self) -> frozenset[str]:
        """Return the searchable words of this section."""
        return _terms(f"{self.title}\n{self.body}")


@dataclass(frozen=True)
class DocumentationLibrary:
    """Everything loaded, plus the rule for choosing what a question carries."""

    #: Read from disk once at start-up, so a mounted file cannot grow without bound and a
    #: mistaken path (a whole site checkout) cannot fill the API server's memory.
    MAX_TOTAL_BYTES = 512 * 1024
    #: A single section longer than this is a chapter, not an answer; it is clipped.
    MAX_SECTION_BYTES = 8 * 1024

    #: Everything sent has to be close to the best match, so a long tail of weak hits is
    #: not carried along with a good one.
    RELEVANCE_FLOOR = 0.35

    #: ...and the best match itself has to be informative. A relative floor alone lets a
    #: question the documentation does not answer through, because 35% of a weak score is
    #: still weak. A term unique to one section is worth ``log(sections)``, so this asks
    #: the best match to be most of the way there: below it, the question matched only
    #: words the whole manual uses. Scaled by library size, because "specific" means
    #: something different in a three-section file and a forty-section manual.
    MIN_RELEVANCE_SHARE = 0.6

    sections: tuple[DocSection, ...] = ()
    bytes_loaded: int = 0
    missing: tuple[str, ...] = field(default=())
    #: How many sections use each term. A word in most of them ("test", "run" in a testing
    #: tool's manual) says nothing about which section answers the question; a rare one
    #: ("PytestOperator", "cleanup") says almost everything. Without this weighting a
    #: question about the user's own runs pulled kilobytes of unrelated manual.
    frequency: dict[str, int] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """Whether anything was loaded at all."""
        return bool(self.sections)

    def select(self, question: str, *, budget: int) -> str:
        """Return the documentation worth sending with ``question``, within ``budget``.

        Scored on how many of the question's own words a section uses, so a question about
        the user's runs matches nothing and sends nothing. Ties go to the shorter section:
        a heading that is mostly the answer beats a chapter that merely mentions it.
        """
        if budget <= 0 or not self.sections:
            return ""
        wanted = _terms(question)
        if not wanted:
            return ""
        total = len(self.sections)
        scored: list[tuple[float, int, DocSection]] = []
        for section in self.sections:
            overlap = wanted & section.terms
            if not overlap:
                continue
            # Smoothed, so the weight stays positive when a term appears in every
            # section: a one-section file would otherwise score every match at zero and
            # send nothing at all.
            weight = sum(
                math.log((total + 1) / (self.frequency.get(term, 1) + 0.5))
                for term in overlap
            )
            if weight <= 0:
                continue
            size = max(1, len(section.text))
            scored.append((weight, size, section))
        if not scored:
            return ""
        scored.sort(key=lambda item: (-item[0], item[1]))
        specific = math.log(max(2, total)) * self.MIN_RELEVANCE_SHARE
        if scored[0][0] < specific:
            # The question shares only common words with the manual: it is about the
            # user's own runs, or about something the documentation does not cover.
            return ""
        floor = max(scored[0][0] * self.RELEVANCE_FLOOR, specific)

        chosen: list[str] = []
        spent = 0
        for weight, _, section in scored:
            if weight < floor:
                break
            block = section.text
            cost = len(block.encode("utf-8")) + 2
            if spent + cost > budget:
                continue
            chosen.append(block)
            spent += cost
        return "\n\n".join(chosen)


def load_documentation(paths: tuple[str, ...]) -> DocumentationLibrary:
    """Read the configured Markdown files once, splitting each into sections.

    Everything is redacted on the way in, not on the way out: documentation is written by
    people and mounted by operators, and an example in it can carry a real key.
    """
    sections: list[DocSection] = []
    missing: list[str] = []
    total = 0
    for raw in paths:
        candidate = Path(raw).expanduser()
        files = _markdown_files(candidate)
        if not files:
            missing.append(str(candidate))
            _log.warning(
                "assistant documentation path has no readable Markdown: %s", candidate
            )
            continue
        for path in files:
            if total >= DocumentationLibrary.MAX_TOTAL_BYTES:
                _log.warning(
                    "assistant documentation stopped at %d bytes; %s and anything after "
                    "it was not loaded",
                    total,
                    path,
                )
                break
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as error:  # pragma: no cover - unreadable file
                missing.append(str(path))
                _log.warning("assistant documentation is unreadable: %s", error)
                continue
            room = DocumentationLibrary.MAX_TOTAL_BYTES - total
            text = text.encode("utf-8")[:room].decode("utf-8", "ignore")
            total += len(text.encode("utf-8"))
            sections.extend(_split(redact_text(text), path.name))
    frequency: dict[str, int] = {}
    for section in sections:
        for term in section.terms:
            frequency[term] = frequency.get(term, 0) + 1
    return DocumentationLibrary(
        sections=tuple(sections),
        bytes_loaded=total,
        missing=tuple(missing),
        frequency=frequency,
    )


def _markdown_files(candidate: Path) -> list[Path]:
    if candidate.is_dir():
        return sorted(path for path in candidate.rglob("*.md") if path.is_file())
    return [candidate] if candidate.is_file() else []


def _split(text: str, source: str) -> list[DocSection]:
    """Split Markdown into (heading, body) sections, keeping the order of the file."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        body = text.strip()
        return (
            [DocSection(title=source, body=_clip(body), source=source)] if body else []
        )
    sections: list[DocSection] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if body:
            sections.append(
                DocSection(title=match.group(2), body=_clip(body), source=source)
            )
    return sections


def _clip(body: str) -> str:
    raw = body.encode("utf-8")
    if len(raw) <= DocumentationLibrary.MAX_SECTION_BYTES:
        return body
    kept = raw[: DocumentationLibrary.MAX_SECTION_BYTES].decode("utf-8", "ignore")
    return f"{kept}\n...[section truncated]..."


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        word.lower() for word in _WORD.findall(text) if word.lower() not in _STOPWORDS
    )


__all__ = ["DocSection", "DocumentationLibrary", "load_documentation"]
