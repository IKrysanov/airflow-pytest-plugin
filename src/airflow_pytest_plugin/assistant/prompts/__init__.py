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

"""Grounding prompt construction, assembled per question from fragments on disk.

The instructions used to be one block sent with every request, so a question about a flaky
test also carried the rules for writing pytest and for drafting an issue -- paid for on
every question, by everyone, forever. They live in ``prompts/*.md`` now:

* ``core`` and ``product`` are always sent. Between them they say what the assistant is,
  what it may claim, and what the two packages are.
* ``documentation`` arrives only when a deployment supplied manuals *and* the question
  matched some of them.
* every other file is a **skill**: instructions for one kind of request, added when the
  question is about that. Selection is a keyword match in both languages -- no model call,
  nothing to train, and a miss costs only the specialised advice, because the core prompt
  already permits the behaviour in general terms.

Editing a skill means editing one Markdown file. Adding one means dropping a file in and
registering its triggers; a test fails if a file is left unreachable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ..common import (
    MAX_HISTORY_BYTES,
    MAX_HISTORY_CHARS,
    MAX_HISTORY_MESSAGES,
    AssistantEvidence,
    AssistantTurn,
    clip_utf8,
)
from ..redaction import redact_text

#: Where the fragments live. Shipped with the package, so an operator can read exactly what
#: their assistant is told without decompiling a string constant.
PROMPT_DIR = Path(__file__).parent

#: Sent with every question, in this order.
ALWAYS = ("core", "product")


@dataclass(frozen=True)
class Skill:
    """Instructions for one kind of request, and the words that call for them."""

    title: str
    text: str
    #: What a user types to ask for this deliberately: ``/bug``, ``/flaky``. Keyword
    #: matching is a guess about what someone meant; a command is them saying it.
    command: str = ""
    #: Whether this kind of request is answered *from* the user's runs. Writing a test
    #: for pasted code is not: telling that request there are no reports and the filters
    #: should be widened contradicts the instruction to write the test, and the model has
    #: to pick one.
    needs_evidence: bool = True
    #: Any one of these appearing in the question is enough.
    triggers: tuple[str, ...] = ()
    #: ...and so is any one of these groups appearing *in full*. Needed where the words
    #: that identify a request are separated by something variable: "напиши тест" is a
    #: request to write one and so is "напиши три теста", but a fixed phrase only catches
    #: the first, and that is precisely the request that says how many are wanted.
    pairs: tuple[tuple[str, ...], ...] = ()

    def wants(self, question: str) -> bool:
        """Whether ``question`` is asking for this kind of help."""
        lowered = question.lower()
        if any(trigger in lowered for trigger in self.triggers):
            return True
        return any(all(word in lowered for word in group) for group in self.pairs)


@cache
def _fragment(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def _skill(
    name: str,
    title: str,
    command: str,
    triggers: tuple[str, ...] = (),
    pairs: tuple[tuple[str, ...], ...] = (),
    needs_evidence: bool = True,
) -> Skill:
    return Skill(
        title=title,
        text=_fragment(name),
        command=command,
        needs_evidence=needs_evidence,
        triggers=triggers,
        pairs=pairs,
    )


#: Triggers are substrings, matched case-insensitively, in both interface languages. They
#: are deliberately generous: sending a skill that was not needed costs a few hundred
#: bytes, while missing one costs the specialised advice entirely.
SKILLS: dict[str, Skill] = {
    "bugreport": _skill(
        "bugreport",
        "drafting a bug report",
        "bug",
        (
            "bug report",
            "bugreport",
            "issue",
            "ticket",
            "report this",
            "write this up",
            "багрепорт",
            "баг-репорт",
            "баг репорт",
            "задач",
            "тикет",
            "оформи",
        ),
    ),
    "flaky": _skill(
        "flaky",
        "flaky tests and quarantine",
        "flaky",
        (
            "flaky",
            "flake",
            "quarantine",
            "skip",
            "unstable",
            "intermittent",
            "rerun",
            "флак",
            "нестабильн",
            "карантин",
            "пропуст",
            "скип",
        ),
    ),
    "prioritise": _skill(
        "prioritise",
        "what to fix first",
        "priority",
        (
            "fix first",
            "prioriti",
            "most important",
            "where to start",
            "worst",
            "приоритет",
            "в первую очередь",
            "с чего начать",
            "важнее",
            "сначала",
        ),
    ),
    "compare": _skill(
        "compare",
        "comparing runs",
        "compare",
        (
            "compare",
            "difference",
            "differ",
            "changed between",
            "versus",
            " vs ",
            "regress",
            "since yesterday",
            "сравн",
            "отлич",
            "измен",
            "разниц",
            "по сравнению",
        ),
    ),
    "authoring": _skill(
        "authoring",
        "writing tests",
        "test",
        triggers=("unit test", "test case for", "покрой тест", "тест-кейс"),
        # A verb and the noun, in either order and however many words apart, so a request
        # that says how many tests it wants is still a request to write tests: a fixed
        # phrase caught "напиши тест" and missed "напиши три теста".
        pairs=(
            ("write", "test"),
            ("generate", "test"),
            ("create", "test"),
            ("add", "test"),
            ("cover", "test"),
            ("напиши", "тест"),
            ("сгенерируй", "тест"),
            ("создай", "тест"),
            ("добавь", "тест"),
            ("покрой", "тест"),
        ),
        needs_evidence=False,
    ),
}


#: Command name -> the skill it selects. Built from the skills so the two cannot drift.
COMMANDS: dict[str, str] = {
    skill.command: name for name, skill in SKILLS.items() if skill.command
}

#: A leading ``/word``, and nothing else. Anything further into the text is a path, a URL
#: or a date -- "why did /tmp/x fail?" is a question, not a command.
_COMMAND = re.compile(r"^/([A-Za-z]+)(?:\s+(.*))?$", re.S)


def parse_command(typed: str) -> tuple[tuple[str, ...], str]:
    """Split a leading ``/command`` off the question. Returns the commands and the rest.

    An unknown command is left in place: dropping it would silently swallow the words the
    user typed after it, and they may simply have begun a sentence with a slash.
    """
    match = _COMMAND.match(typed.strip())
    if match is None:
        return (), typed
    name = match.group(1).lower()
    if name not in COMMANDS:
        return (), typed
    return (name,), (match.group(2) or "").strip()


def command_catalogue() -> list[dict[str, str]]:
    """Return the commands for the browser to offer, so the menu is never a second list."""
    return [
        {"name": name, "skill": COMMANDS[name], "title": SKILLS[COMMANDS[name]].title}
        for name in sorted(COMMANDS)
    ]


def core_prompt() -> str:
    """Return the instructions every question carries."""
    return "\n\n".join(_fragment(name) for name in ALWAYS)


def build_system_prompt(
    question: str,
    *,
    has_documentation: bool = False,
    commands: tuple[str, ...] = (),
) -> str:
    """Assemble the system prompt this question needs.

    Deterministic for a given question, so two identical questions produce byte-identical
    prompts and the reported cost of an answer can be reproduced.
    """
    parts = [core_prompt()]
    if has_documentation:
        parts.append(_fragment("documentation"))
    if commands:
        # Asked for by name, so the keywords do not get a vote: someone typing /bug about
        # a flaky test wants the bug-report rules, not both.
        wanted = [COMMANDS[name] for name in commands if name in COMMANDS]
        parts.extend(SKILLS[name].text for name in wanted)
    else:
        parts.extend(skill.text for skill in SKILLS.values() if skill.wants(question))
    return "\n\n".join(parts)


#: The always-on prompt, for callers that need a stable reference (health probes, tests).
SYSTEM_PROMPT = core_prompt()


def selected_skills(question: str, commands: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Return the skills this request earns, by command if given, else by keyword."""
    if commands:
        return tuple(COMMANDS[name] for name in commands if name in COMMANDS)
    return tuple(name for name, skill in SKILLS.items() if skill.wants(question))


def no_evidence_text(*, commands: tuple[str, ...] = (), question: str = "") -> str:
    """Return the evidence block to send when no report was in scope.

    Two different situations wear the same empty evidence. A question about the user's
    runs found nothing and should be told so. A request that never needed a report --
    writing a test for pasted code -- must not be, because "no report matched, widen your
    filters" reads as a refusal and competes with the instruction to do the work.
    """
    wanted = selected_skills(question, commands)
    if wanted and all(not SKILLS[name].needs_evidence for name in wanted):
        return _fragment("no_evidence_optional")
    return _fragment("no_evidence")


#: What stands in for the evidence block when the scope held no readable report. The model
#: is called anyway -- a question about the product itself needs no evidence, and a fresh
#: installation with nothing archived yet is exactly when someone asks one -- so it has to
#: be told plainly that there is nothing to describe.
NO_EVIDENCE = _fragment("no_evidence")

_CITATION = re.compile(r"\[R([1-9][0-9]*)\]")


@dataclass(frozen=True)
class ProviderPrompt:
    """Rendered provider prompt and exact content/structure byte attribution."""

    text: str
    user_bytes: int
    context_bytes: int
    history_bytes: int
    docs_bytes: int
    structure_bytes: int


#: A language tag and nothing else. The value arrives from the browser, so it is matched
#: rather than trusted: anything that is not a tag is dropped instead of being repaired.
_LOCALE_TAG = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")


def language_line(locale: str) -> str:
    """Return the dashboard-language instruction, or nothing for an API client."""
    tag = (locale or "").strip()
    if not tag or not _LOCALE_TAG.match(tag):
        return ""
    return (
        f"DASHBOARD LANGUAGE\n{tag}\nAnswer in this language unless the question is "
        "clearly written in another one.\n\n"
    )


def build_provider_prompt(
    *,
    question: str,
    history: Sequence[AssistantTurn],
    evidence: str,
    locale: str = "",
    docs: str = "",
) -> ProviderPrompt:
    """Render a provider prompt once and attribute every UTF-8 byte."""
    history_text = _history_text(history)
    docs_block = (
        f"DOCUMENTATION (about the product, not about any run)\n{docs}\n\n"
        if docs
        else ""
    )
    text = (
        f"{language_line(locale)}"
        f"USER QUESTION\n{question}\n\n"
        f"RECENT CHAT (untrusted conversational context)\n{history_text}\n\n"
        f"{docs_block}"
        f"REPORT EVIDENCE\n{evidence}\n\n"
        "Write the answer now. Check count consistency before returning it."
    )
    user_bytes = len(question.encode("utf-8"))
    context_bytes = len(evidence.encode("utf-8"))
    history_bytes = 0 if history_text == "(none)" else len(history_text.encode("utf-8"))
    docs_bytes = len(docs.encode("utf-8")) if docs else 0
    structure_bytes = len(text.encode("utf-8")) - (
        user_bytes + context_bytes + history_bytes + docs_bytes
    )
    return ProviderPrompt(
        text=text,
        user_bytes=user_bytes,
        context_bytes=context_bytes,
        history_bytes=history_bytes,
        docs_bytes=docs_bytes,
        structure_bytes=structure_bytes,
    )


def cited_evidence(
    answer: str, evidence: Sequence[AssistantEvidence]
) -> tuple[AssistantEvidence, ...]:
    """Return the evidence the answer actually cited, with a small honest fallback.

    Three cases, and they are not the same thing:

    * some labels resolve -- return exactly those;
    * the answer cited nothing at all -- return the first few reports. Models routinely
      answer without labels even when they used the evidence, and the buttons are then an
      affordance to go and look, not a claim about where the answer came from;
    * the answer cited only labels that do not exist -- return nothing. It named its
      sources and named them wrong, so attaching real reports underneath a visible
      ``[R99]`` would invent provenance for an answer that has none.
    """
    by_key = {item.key: item for item in evidence}
    used: list[AssistantEvidence] = []
    seen: set[str] = set()
    claimed = False
    for match in _CITATION.finditer(answer):
        claimed = True
        key = f"R{match.group(1)}"
        if key in by_key and key not in seen:
            used.append(by_key[key])
            seen.add(key)
    if used:
        return tuple(used)
    return () if claimed else tuple(evidence[:3])


def _history_text(history: Sequence[AssistantTurn]) -> str:
    if not history:
        return "(none)"
    selected: list[str] = []
    remaining = MAX_HISTORY_BYTES
    for turn in reversed(history[-MAX_HISTORY_MESSAGES:]):
        prefix = f"{turn.role}: "
        content = clip_utf8(redact_text(turn.content), MAX_HISTORY_CHARS)
        line = prefix + content
        separator = 1 if selected else 0
        cost = len(line.encode("utf-8", "replace")) + separator
        if cost <= remaining:
            selected.append(line)
            remaining -= cost
            continue
        available = remaining - len(prefix.encode("utf-8")) - separator
        if available > 0:
            selected.append(prefix + clip_utf8(content, available))
        break
    # Both cut-offs -- the message count and the byte budget -- can fall between a question
    # and its answer, leaving the window opening on a reply with no prompt above it. That
    # is the one shape of history that reliably confuses a follow-up, so the orphan is
    # dropped rather than sent.
    while selected and selected[-1].startswith("assistant: "):
        selected.pop()
    return "\n".join(reversed(selected)) or "(none)"


__all__ = [
    "SYSTEM_PROMPT",
    "ProviderPrompt",
    "build_provider_prompt",
    "cited_evidence",
]
