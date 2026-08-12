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

"""Which instructions a question earns, and what every question pays for regardless.

The prompt used to be one block that rode on every request, so a question about a flaky
test carried the rules for writing pytest and drafting an issue. These are the rules that
keep it from drifting back: the always-on part stays small, a skill arrives only when its
subject does, and every fragment on disk is reachable.
"""

from __future__ import annotations

import pytest

from airflow_pytest_plugin.assistant.prompts import (
    ALWAYS,
    COMMANDS,
    PROMPT_DIR,
    SKILLS,
    build_system_prompt,
    command_catalogue,
    core_prompt,
    no_evidence_text,
    parse_command,
)


def test_the_always_on_prompt_is_the_core_and_the_product():
    assert ALWAYS == ("core", "product")


@pytest.mark.parametrize(
    "question, skill",
    [
        ("оформи багрепорт по этому падению", "bugreport"),
        ("write this up as an issue", "bugreport"),
        ("which tests look flaky?", "flaky"),
        ("стоит ли поместить его в карантин?", "flaky"),
        ("should I skip this test for now?", "flaky"),
        ("what should I fix first?", "prioritise"),
        ("что чинить в первую очередь?", "prioritise"),
        ("compare yesterday's run with today's", "compare"),
        ("что изменилось между прогонами?", "compare"),
        ("напиши тест на эту функцию", "authoring"),
        ("write me three tests for this code", "authoring"),
    ],
)
def test_a_question_earns_the_skill_it_needs(question, skill):
    prompt = build_system_prompt(question)

    assert f"SKILL: {SKILLS[skill].title}" in prompt or SKILLS[skill].text in prompt


@pytest.mark.parametrize(
    "question",
    [
        "what failed in the latest runs?",
        "why is etl_daily red?",
        "сколько тестов упало вчера?",
        "how many unique tests are there?",
    ],
)
def test_an_ordinary_question_pays_for_no_skill_at_all(question):
    prompt = build_system_prompt(question)

    assert prompt == core_prompt()
    for name, skill in SKILLS.items():
        assert skill.text not in prompt, name


def test_the_documentation_rules_arrive_with_the_documentation():
    without = build_system_prompt("what parameters does PytestOperator take?")
    with_docs = build_system_prompt(
        "what parameters does PytestOperator take?", has_documentation=True
    )

    assert "DOCUMENTATION" not in without
    assert "DOCUMENTATION" in with_docs


def test_two_subjects_in_one_question_bring_both_skills():
    prompt = build_system_prompt("which tests are flaky, and what should I fix first?")

    assert SKILLS["flaky"].text in prompt
    assert SKILLS["prioritise"].text in prompt


def test_every_fragment_on_disk_is_registered():
    """A file nobody can reach is a rule nobody follows."""
    on_disk = {path.stem for path in PROMPT_DIR.glob("*.md")}
    registered = (
        set(SKILLS)
        | set(ALWAYS)
        | {
            "documentation",
            "no_evidence",
            "no_evidence_optional",
        }
    )

    assert on_disk == registered, on_disk ^ registered


def test_every_skill_has_triggers_in_both_languages():
    """...except the one that cannot be guessed at, which is reachable only by command.

    The documentation skill says a DOCUMENTATION section *is* supplied. Letting a keyword
    add it would put that sentence in front of the model on questions where no manual
    matched, which is an instruction to quote something that is not there.
    """
    for name, skill in SKILLS.items():
        if not skill.triggers and not skill.pairs:
            assert skill.command, f"{name} is reachable by nothing at all"
            continue
        assert skill.triggers, name
        assert any(
            any("а" <= char <= "я" for char in trigger) for trigger in skill.triggers
        ), f"{name} has no Russian trigger"


def test_the_always_on_prompt_stays_small():
    """It rides on every question; a skill that creeps in here is paid for by everyone."""
    size = len(core_prompt().encode("utf-8"))

    assert size < 4_608, f"the always-on prompt is {size} bytes"


def test_a_skill_cannot_silently_be_enormous():
    for name, skill in SKILLS.items():
        size = len(skill.text.encode("utf-8"))
        assert size < 2_048, f"{name} is {size} bytes"


def test_the_prompt_is_stable_for_the_same_question():
    first = build_system_prompt("what should I fix first?")
    second = build_system_prompt("what should I fix first?")

    assert first == second


@pytest.mark.parametrize(
    "question",
    [
        "напиши три теста на эту функцию",
        "напиши 5 тестов на этот класс",
        "write 3 tests for this function",
        "write me a couple of unit tests for the parser",
        "сгенерируй пару тестов",
        "add two tests covering the error path",
    ],
)
def test_asking_for_a_number_of_tests_still_earns_the_authoring_skill(question):
    """A count between the verb and the noun defeats a fixed phrase.

    "напиши тест" matched and "напиши три теста" did not, which is exactly the request
    that says how many are wanted.
    """
    assert SKILLS["authoring"].text in build_system_prompt(question), question


@pytest.mark.parametrize(
    "question",
    [
        "какие тесты упали?",
        "which tests failed?",
        "how many tests ran yesterday?",
    ],
)
def test_merely_saying_the_word_test_does_not_earn_it(question):
    """Every question here is about tests; the skill is for being asked to write one."""
    assert SKILLS["authoring"].text not in build_system_prompt(question), question


# --- explicit commands -----------------------------------------------------------------


def test_every_skill_has_a_command():
    """Keyword matching is a guess; a command is the user saying exactly what they want."""
    assert {skill.command for skill in SKILLS.values()} == set(COMMANDS)
    for name, skill in SKILLS.items():
        assert skill.command, name
        assert skill.command.isalpha() and skill.command.islower(), skill.command


@pytest.mark.parametrize(
    "typed, command, remaining",
    [
        ("/bug по этому падению", "bug", "по этому падению"),
        ("/flaky", "flaky", ""),
        ("/priority   what now?", "priority", "what now?"),
        ("/TEST write three of them", "test", "write three of them"),
        ("/compare yesterday and today", "compare", "yesterday and today"),
    ],
)
def test_a_command_is_taken_off_the_question(typed, command, remaining):
    """The command is an instruction to us, not part of what the model is asked."""
    used, question = parse_command(typed)

    assert used == (command,)
    assert question == remaining


@pytest.mark.parametrize(
    "typed",
    [
        "what failed?",
        "why did /tmp/x fail?",
        "the path is /bug/report",
        "/unknown do something",
        "/ ",
        "//bug",
        "",
    ],
)
def test_anything_that_is_not_a_command_is_left_alone(typed):
    used, question = parse_command(typed)

    assert used == ()
    assert question == typed


def test_a_command_wins_over_the_keywords():
    """Exact targeting: asking for /bug about a flaky test gets the bug-report rules."""
    used, question = parse_command("/bug about a flaky test")

    prompt = build_system_prompt(question, commands=used)

    assert SKILLS["bugreport"].text in prompt
    assert SKILLS["flaky"].text not in prompt


def test_without_a_command_the_keywords_still_work():
    used, question = parse_command("should I quarantine this flaky test?")

    prompt = build_system_prompt(question, commands=used)

    assert SKILLS["flaky"].text in prompt


def test_an_unknown_command_keeps_the_users_words():
    """Dropping "/summarise the last run" would lose the question with the slash."""
    used, question = parse_command("/summarise the last run")

    assert used == ()
    assert question == "/summarise the last run"


def test_the_commands_are_published_for_the_browser_to_render():
    """One source of truth: the menu must not be a second list that drifts."""
    published = command_catalogue()

    assert [item["name"] for item in published] == sorted(COMMANDS)
    for item in published:
        assert item["skill"] in SKILLS


# --- requests that need no report at all ------------------------------------------------


def test_writing_tests_is_marked_as_needing_no_evidence():
    """It is the one skill whose whole job is independent of the user's runs."""
    assert SKILLS["authoring"].needs_evidence is False
    for name in ("bugreport", "flaky", "prioritise", "compare"):
        assert SKILLS[name].needs_evidence is True, name


def test_an_empty_scope_does_not_tell_a_test_request_to_widen_its_filters():
    """Two instructions that contradict each other leave the model to pick one.

    "/test" with nothing archived was told both to write the test and to reply that no
    report matched and the filters should be widened -- and the second reads like a
    refusal, which is what came back.
    """
    text = " ".join(
        no_evidence_text(commands=("test",), question="напиши тест").split()
    )

    # It must not carry the instruction to *say* no report matched. (It does say "do not
    # suggest widening", so a bare search for the word finds the guard, not the fault.)
    assert "suggest clearing" not in text
    assert "does not need report evidence" in text


def test_an_empty_scope_still_says_so_for_a_question_about_runs():
    text = " ".join(
        no_evidence_text(commands=(), question="what failed yesterday?").split()
    )

    assert "suggest clearing or widening" in text


def test_a_bug_report_with_no_reports_is_still_told_there_are_none():
    """There is genuinely nothing to write the report from."""
    text = " ".join(
        no_evidence_text(commands=("bug",), question="оформи багрепорт").split()
    )

    assert "suggest clearing or widening" in text


def test_a_test_request_without_the_command_is_recognised_too():
    """The keyword path has to reach the same conclusion as the command path."""
    text = " ".join(
        no_evidence_text(
            commands=(), question="напиши три теста на эту функцию"
        ).split()
    )

    assert "suggest clearing" not in text
    assert "does not need report evidence" in text


def test_the_authoring_skill_says_what_to_do_with_evidence_it_did_not_ask_for():
    """Reports are still sent when the user has some in scope.

    That is deliberate -- "write a test that reproduces this failure" needs them -- but
    the skill has to say which of the two situations it is in, or an unrelated 48 KiB of
    run data gets worked into a test for pasted code.
    """
    text = " ".join(SKILLS["authoring"].text.split())

    assert "reproduces it" in text
    assert "ignore it" in text


def test_the_documentation_skill_is_reachable_only_by_command():
    """Keywords must not add it: see the note on triggers above."""
    assert SKILLS["documentation"].command == "docs"
    assert not SKILLS["documentation"].wants("расскажи про документацию и параметры")
    assert parse_command("/docs какие параметры") == (("docs",), "какие параметры")


def test_a_docs_command_does_not_claim_documentation_that_is_not_there():
    """/docs on a deployment that mounted no manuals must not promise a section."""
    prompt = build_system_prompt(
        "какие параметры", has_documentation=False, commands=("docs",)
    )

    assert "A DOCUMENTATION section is supplied" not in prompt
    assert core_prompt() in prompt


def test_a_docs_command_carries_the_documentation_rules_exactly_once():
    prompt = build_system_prompt(
        "какие параметры", has_documentation=True, commands=("docs",)
    )

    assert prompt.count("A DOCUMENTATION section is supplied") == 1


def test_a_docs_question_is_not_told_to_widen_its_filters():
    """It is a question about the product; the user's runs have nothing to do with it."""
    text = no_evidence_text(commands=("docs",), question="какие параметры")

    assert "no report was needed" in text
    assert "no report matched the current scope" not in text


def test_a_documentation_answer_is_not_told_to_widen_the_filters():
    """Asked from the manual, "no report matched" is a non-sequitur.

    The reader asked how to run their first test. Answering that with "no run matched
    your filters, clear them and try again" is the assistant refusing a question it was
    about to answer -- and on a fresh install, where there are no runs at all, it is the
    only kind of question anyone can ask.
    """
    text = no_evidence_text(
        question="как запустить первый тест?", has_documentation=True
    )

    assert "no report was needed" in text
    assert "no report matched the current scope" not in text


def test_a_question_about_runs_is_still_told_the_scope_was_empty():
    """Even when a manual happens to be loaded, this is the honest answer."""
    text = no_evidence_text(question="почему упал test_login?", has_documentation=False)

    assert "no report matched the current scope" in text


def test_a_question_about_runs_wins_over_a_manual_that_happens_to_match():
    """ "какие тесты флакают?" is about their runs, whatever the manual has to say.

    A manual for a testing tool has a section on flaky tests, so retrieval matches -- and
    treating that as "no report was needed" would answer a question about this week's
    runs with general advice and never mention that nothing was found.
    """
    text = no_evidence_text(question="какие тесты флакают?", has_documentation=True)

    assert "no report matched the current scope" in text


def test_the_authoring_skill_writes_rather_than_interviews():
    """ "Write two tests for login" is a request, not the opening of a requirements chat.

    The skill used to end with "if the request is too vague, ask one specific question",
    and a live provider took that exit for exactly the request the feature exists to
    serve -- coming back with "which framework, and what counts as success?" instead of
    two tests. A stated assumption is worth more than a question here: the reader can
    correct an assumption in one word, and they cannot use an empty answer at all.
    """
    text = " ".join(SKILLS["authoring"].text.split())

    assert "ask one specific question instead" not in text
    assert "state the assumption" in text
    assert "write them anyway" in text
