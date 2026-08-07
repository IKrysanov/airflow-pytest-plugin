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
#: The second and third lines are function and quantity words. They carry no subject at
#: all, yet in a manual of twenty sections a word like "two" or "between" occurs once and
#: therefore looks *rare* -- which is how "what changed between the last two runs?" came
#: to be judged a question about the documentation.
_STOPWORDS = frozenset(
    """
    the and for are with that this what which how why when does can from you your
    between last next two three both other another same than then there their them
    these those here also only just very much many more most few own per via about
    как что где для чтобы если это или так тебя ваши какие есть быть
    этому этот эта эти вчера сегодня сейчас ещё уже очень свой свои него нему тот
    """.split()
)


#: A domain glossary, not a translator. Matching is lexical, so a Russian question and an
#: English manual -- which is the normal case, since the operator's own documentation is
#: written in English -- shared no term at all: "как запустить первый тест?" scored zero
#: against "Running your first test" and the reader was sent to read the manual they had
#: already been given. Keys are stems, because Russian inflects and the words that matter
#: here are few enough to list. Used in both directions.
_GLOSSARY: dict[str, tuple[str, ...]] = {
    "запуск": ("run", "running", "start", "execute"),
    "запуст": ("run", "running", "start", "execute"),
    "старт": ("start", "run"),
    "тест": ("test", "tests", "pytest"),
    "параметр": ("parameter", "parameters", "option", "options", "argument"),
    "аргумент": ("argument", "arguments", "parameter"),
    "настро": ("configure", "configuration", "setup", "settings"),
    "установ": ("install", "installation", "setup"),
    "конфиг": ("config", "configuration"),
    "перемен": ("environment", "variable", "variables"),
    "отчет": ("report", "reports"),
    "отчёт": ("report", "reports"),
    "ошибк": ("error", "errors"),
    # "падение" is deliberately absent: what failed is a question for the reports, and
    # bridging it to "failure" pulled the parameter table into every bug-report request.
    "хран": ("stored", "storage", "store"),
    "сохран": ("saved", "save", "stored", "storage"),
    "чат": ("chat", "chats", "transcript"),
    "пуст": ("empty",),
    "удал": ("delete", "deleted", "remove"),
    "прав": ("permission", "permissions", "access"),
    "покрыти": ("coverage", "cov"),
    "пример": ("example", "examples"),
    "первый": ("first",),
    "версия": ("version",),
    "модел": ("model", "models"),
    "провайдер": ("provider", "providers"),
    "квота": ("quota", "limit"),
    "лимит": ("limit", "limits", "quota", "rate"),
    "токен": ("token", "tokens"),
    "истори": ("history", "chat"),
    "шифров": ("encryption", "encrypt", "fernet"),
    "доступ": ("access", "permission", "permissions", "rbac"),
    "база": ("database",),
    "таблиц": ("table", "tables", "database"),
    "логи": ("log", "logs"),
    "длительн": ("duration", "time", "slow"),
    # No "duration": it is a field of a report, not a subject of the manual, and it
    # made "покажи самые медленные тесты" -- a question about runs -- look specific.
    "медлен": ("slow", "slowest"),
    "флак": ("flaky", "flake"),
    "карантин": ("quarantine", "skip"),
    "архив": ("archive", "archiving", "archived"),
    "дашборд": ("dashboard", "viewer"),
    "оператор": ("operator",),
    "плагин": ("plugin",),
}


def _reverse_glossary() -> dict[str, tuple[str, ...]]:
    """Return English term -> the Russian stems that mean it."""
    reversed_map: dict[str, list[str]] = {}
    for stem, english in _GLOSSARY.items():
        for word in english:
            reversed_map.setdefault(word, []).append(stem)
    return {word: tuple(stems) for word, stems in reversed_map.items()}


_GLOSSARY_EN = _reverse_glossary()


def _bridge(terms: frozenset[str]) -> frozenset[str]:
    """Return ``terms`` plus their counterparts in the other interface language."""
    extra: set[str] = set()
    for term in terms:
        for stem, english in _GLOSSARY.items():
            if term.startswith(stem):
                extra.update(english)
        extra.update(_GLOSSARY_EN.get(term, ()))
    return terms | extra


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

    #: ...and the question has to have named something the manual uses *rarely*. The test
    #: is the best single term it matched, not the sum: a sum grows with the number of
    #: ordinary words in common, so "which tests failed in the last run?" -- every word of
    #: which a testing manual uses constantly -- scored as highly as a question naming
    #: ``coverage_source``. Raising the bar could not separate them, because the leak was
    #: never a weak match; measured over both sets it only cost real answers. A term
    #: unique to one section is worth ``log(sections)``, so this asks for one term most of
    #: the way there. Scaled by library size, because "rare" means something different in
    #: a three-section file and a forty-section manual.
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

    def select(self, question: str, *, budget: int, forced: bool = False) -> str:
        """Return the documentation worth sending with ``question``, within ``budget``.

        Scored on how many of the question's own words a section uses, so a question about
        the user's runs matches nothing and sends nothing. Ties go to the shorter section:
        a heading that is mostly the answer beats a chapter that merely mentions it.

        ``forced`` is the user having typed ``/docs``. The specificity gate below exists to
        guess whether a question is about the manual at all, and that guess is worth less
        than being told: a vague "how do I install this?" shares only ordinary words with
        the manual and is dropped, which is right when it was guessed and wrong when it was
        asked for. Forcing lowers the bar; it never invents a match.
        """
        if budget <= 0 or not self.sections:
            return ""
        # Bridged across the two interface languages before scoring, so the manual is
        # found by the words its reader actually typed.
        wanted = _bridge(_terms(question))
        if not wanted:
            return ""
        total = len(self.sections)
        scored: list[tuple[float, int, DocSection, float]] = []
        for section in self.sections:
            overlap = wanted & section.terms
            if not overlap:
                continue
            # Smoothed, so the weight stays positive when a term appears in every
            # section: a one-section file would otherwise score every match at zero and
            # send nothing at all.
            weights = [
                math.log((total + 1) / (self.frequency.get(term, 1) + 0.5))
                for term in overlap
            ]
            weight = sum(weights)
            if weight <= 0:
                continue
            size = max(1, len(section.text))
            scored.append((weight, size, section, max(weights)))
        if not scored:
            return ""
        scored.sort(key=lambda item: (-item[0], item[1]))
        # A fraction of the *most* a term could be worth here, not of the library size:
        # scaled by log(total) instead, a one-section file set a bar no term in it could
        # clear -- every term appears in every section -- and a small hand-written manual
        # answered nothing at all.
        rarest_possible = math.log((total + 1) / 1.5)
        specific = 0.0 if forced else rarest_possible * self.MIN_RELEVANCE_SHARE
        # Applied per section rather than once to the best one. A question that clears the
        # bar somewhere does not thereby earn every section it shares an ordinary word
        # with: judged globally, "which tests failed in the last run?" arrived with five
        # sections and 3.4 KiB of manual attached to it.
        scored = [item for item in scored if item[3] >= specific]
        if not scored:
            # Nothing rare was named: the question shares only words the whole manual
            # uses, so it is about the user's own runs or about something not covered.
            return ""
        floor = scored[0][0] * self.RELEVANCE_FLOOR

        chosen: list[str] = []
        spent = 0
        for weight, _, section, _rarest in scored:
            if weight < floor:
                break
            block = section.text
            cost = len(block.encode("utf-8")) + 2
            if spent + cost > budget:
                continue
            chosen.append(block)
            spent += cost
        return "\n\n".join(chosen)


#: Shipped with the package, so `/docs` answers "how do I run my first test?" on a fresh
#: install. It documents *this* product -- the two packages, the parser's parameters, the
#: dashboard, retention and the things that go wrong -- which is exactly the part no
#: deployment can be expected to write and no model should recall from memory.
#: ``manual`` rather than ``docs``: a package directory beside ``docs.py`` would shadow it.
BUILTIN_MANUAL = Path(__file__).parent / "manual"


def builtin_paths() -> tuple[str, ...]:
    """Return the shipped manual, or nothing when it is missing from the install."""
    return (str(BUILTIN_MANUAL),) if BUILTIN_MANUAL.is_dir() else ()


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
