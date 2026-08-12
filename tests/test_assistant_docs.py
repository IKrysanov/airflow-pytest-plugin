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

"""Documentation an operator supplies, and how a question picks its way through it.

The assistant cannot answer "what parameters does PytestOperator take" from anything in
this repository -- that documentation lives in another package. Inventing an answer is the
one thing this feature must never do, so the deployment supplies the files and the only
question here is which parts of them a given question should carry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from airflow_pytest_plugin.assistant.docs import (
    BUILTIN_MANUAL,
    DocumentationLibrary,
    builtin_paths,
    load_documentation,
)

QUICKSTART = """\
# airflow-pytest-operator

## Quickstart

Install it and point a DAG at your suite.

## PytestOperator parameters

| Name | Default | Meaning |
| --- | --- | --- |
| `tests` | — | path passed to pytest |
| `parser` | built-in | object that reads the JUnit report |
| `cleanup` | `"always"` | when the working directory is removed |

## Coverage

Pass `--cov` through `pytest_args`.
"""


@pytest.fixture
def library(tmp_path: Path) -> DocumentationLibrary:
    (tmp_path / "operator.md").write_text(QUICKSTART, encoding="utf-8")
    return load_documentation((str(tmp_path / "operator.md"),))


def test_a_question_gets_the_section_that_answers_it(library):
    picked = library.select("какие параметры есть у PytestOperator?", budget=4_096)

    assert "PytestOperator parameters" in picked
    assert "`cleanup`" in picked
    assert "Coverage" not in picked


def test_a_different_question_gets_a_different_section(library):
    """Selection is lexical: it matches the words the documentation actually uses.

    "How do I run my first test" shares nothing with a Quickstart that talks about
    installing and pointing a DAG at a suite -- the question has to name something the
    manual names. That is the honest limit of matching without a model, and it is why the
    short PRODUCT block in the system prompt answers the vaguer questions.
    """
    picked = library.select(
        "how do I install and point a DAG at my suite?", budget=4_096
    )

    assert "Quickstart" in picked


def test_nothing_relevant_sends_nothing(library):
    assert library.select("what is the airspeed of a swallow?", budget=4_096) == ""


def test_a_question_about_the_users_own_runs_carries_no_manual(library):
    """The common case must pay nothing for this feature."""
    assert library.select("why did test_login fail yesterday?", budget=4_096) == ""


def test_the_budget_is_never_exceeded(library):
    picked = library.select("PytestOperator parameters coverage quickstart", budget=200)

    assert len(picked.encode("utf-8")) <= 200


def test_a_zero_budget_switches_it_off(library):
    assert library.select("PytestOperator parameters", budget=0) == ""


def test_no_paths_means_no_library(tmp_path):
    assert load_documentation(()).select("anything", budget=4_096) == ""


def test_a_directory_brings_in_every_markdown_file(tmp_path):
    (tmp_path / "a.md").write_text("# One\n\nabout widgets\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Two\n\nabout sprockets\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text(
        "# Three\n\nabout ignored things\n", encoding="utf-8"
    )

    library = load_documentation((str(tmp_path),))

    assert "widgets" in library.select("widgets", budget=4_096)
    assert "sprockets" in library.select("sprockets", budget=4_096)
    assert library.select("ignored", budget=4_096) == "", "only markdown is read"


def test_a_missing_path_is_reported_not_fatal(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        library = load_documentation((str(tmp_path / "nope.md"),))

    assert library.select("anything", budget=4_096) == ""
    assert any("nope.md" in record.message for record in caplog.records)


def test_a_huge_file_is_bounded_at_load_time(tmp_path):
    (tmp_path / "big.md").write_text(
        "# Huge\n\n" + ("filler paragraph about pytest\n\n" * 200_000), encoding="utf-8"
    )

    library = load_documentation((str(tmp_path / "big.md"),))

    assert library.bytes_loaded <= DocumentationLibrary.MAX_TOTAL_BYTES


def test_secrets_in_documentation_are_redacted_before_they_can_be_sent(
    tmp_path, monkeypatch
):
    """Documentation is mounted by an operator and can hold an example with a real key."""
    monkeypatch.setenv("SOME_TOKEN", "sk-live-0123456789abcdef")
    (tmp_path / "doc.md").write_text(
        "# Setup\n\nexport TOKEN=sk-live-0123456789abcdef\n", encoding="utf-8"
    )

    picked = load_documentation((str(tmp_path / "doc.md"),)).select(
        "setup", budget=4_096
    )

    assert "sk-live-0123456789abcdef" not in picked


def test_a_forced_selection_answers_what_the_specificity_gate_would_reject(tmp_path):
    """`/docs` is the user saying the question is about the manual.

    The gate exists because a question that matches only a word the whole manual uses is
    usually about the user's own runs, and a real manual is big enough for that to happen
    often. Guessing wrong costs the answer; being told costs nothing.
    """
    manual = "\n".join(
        f"## Chapter {n}\nThis chapter explains the cleanup behaviour of step {n}.\n"
        for n in range(12)
    )
    (tmp_path / "manual.md").write_text(manual, encoding="utf-8")
    library = load_documentation((str(tmp_path / "manual.md"),))

    assert library.select("what about cleanup?", budget=4_096) == ""
    assert "cleanup" in library.select("what about cleanup?", budget=4_096, forced=True)


def test_a_forced_selection_still_sends_nothing_when_nothing_matches(library):
    """Forcing lowers the bar; it does not invent a match."""
    assert library.select("проблемы с кубернетесом", budget=4_096, forced=True) == ""
    assert library.select("какие параметры", budget=0, forced=True) == ""


RUSSIAN_ASKS_ENGLISH_MANUAL = """\
# airflow-pytest-operator

## Running your first test

Add a `PytestOperator` to a DAG, point `tests` at your suite, and give the task an
`ArchivingResultParser` so the JUnit report is archived where the dashboard reads it.

## Installing the plugin

Install it into the API server image and restart.

## Coverage

Pass `--cov` through `pytest_args`.
"""


@pytest.fixture
def bilingual(tmp_path: Path) -> DocumentationLibrary:
    (tmp_path / "operator.md").write_text(RUSSIAN_ASKS_ENGLISH_MANUAL, encoding="utf-8")
    return load_documentation((str(tmp_path / "operator.md"),))


def test_a_russian_question_finds_an_english_manual(bilingual):
    """The dashboard speaks two languages; the manual it is given speaks one.

    Matching is lexical, so "как запустить первый тест?" shared not one term with
    "Running your first test" and the reader was told to go and read the manual they had
    already been given. A small domain glossary bridges the two -- no model, no index.
    """
    picked = bilingual.select("как запустить первый тест?", budget=4_096)

    assert "Running your first test" in picked
    assert "PytestOperator" in picked


def test_the_bridge_works_in_the_other_direction_too(tmp_path):
    """A deployment whose runbook is in Russian, read by someone asking in English."""
    (tmp_path / "runbook.md").write_text(
        "# Руководство\n\n## Как запустить первый тест\n\n"
        "Добавьте PytestOperator в DAG и укажите путь к набору тестов.\n\n"
        "## Покрытие\n\nПередайте `--cov` через `pytest_args`.\n",
        encoding="utf-8",
    )
    library = load_documentation((str(tmp_path / "runbook.md"),))

    picked = library.select("how do I run my first test?", budget=4_096)

    assert "запустить первый тест" in picked


def test_the_glossary_does_not_drag_the_manual_into_a_question_about_runs(bilingual):
    """The words it adds are common ones; the relevance bar still has to hold."""
    assert bilingual.select("почему упал test_login вчера?", budget=4_096) == ""
    assert bilingual.select("что сломалось в последнем прогоне?", budget=4_096) == ""


# --- the manual shipped with the package -------------------------------------------------


@pytest.fixture(scope="module")
def builtin() -> DocumentationLibrary:
    return load_documentation(builtin_paths())


def test_the_shipped_manual_is_found_and_loads(builtin):
    assert builtin.available
    assert builtin.missing == ()
    assert builtin.bytes_loaded < DocumentationLibrary.MAX_TOTAL_BYTES


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("как запустить первый тест?", "ArchivingResultParser"),
        ("how do I run my first test?", "ArchivingResultParser"),
        ("какие параметры есть у ArchivingResultParser?", "coverage_threshold"),
        ("what does coverage_source do?", "coverage_source"),
        ("где хранятся отчёты?", "reports_root"),
        ("how do I delete old reports?", "RETENTION"),
        ("почему дашборд пустой?", "empty"),
        ("чаты не сохраняются, что делать?", "doctor"),
        ("что такое flaky тест?", "flaky"),
        ("нужен ли cleanup never?", "cleanup"),
    ],
)
def test_the_shipped_manual_answers_the_questions_it_exists_for(
    builtin, question, expected
):
    """Each of these is a question a person asks on their first day."""
    picked = builtin.select(question, budget=8_192)

    assert expected in picked, picked[:200] or "(nothing selected)"


@pytest.mark.parametrize(
    "question",
    [
        "почему упал test_login вчера?",
        "which tests failed in the last run?",
        "что сломалось в run_42?",
        "сколько тестов упало сегодня?",
        "покажи самые медленные тесты",
        "what changed between the last two runs?",
        "оформи багрепорт по этому падению",
        "какой тест самый нестабильный?",
        "что чинить в первую очередь?",
        "напиши тест на эту функцию",
    ],
)
def test_a_question_about_runs_pulls_none_of_the_shipped_manual(builtin, question):
    """It ships with every install, so it must stay silent on the common question.

    While the corpus was the operator's own, a false positive was their bytes and their
    problem. Now it is on every request in every deployment, which is what made the
    relevance rule worth measuring rather than assuming.
    """
    assert builtin.select(question, budget=8_192) == "", question


def test_the_manual_documents_the_parser_the_code_actually_has():
    """A hand-written manual drifts; this is the guard that says so out loud.

    Every parameter the manual names must exist on ``ArchivingResultParser``, and every
    parameter the class takes must be named in the manual -- so adding one to the code
    without documenting it fails here rather than in front of a user.
    """
    import inspect
    import re

    from airflow_pytest_plugin import ArchivingResultParser

    text = (BUILTIN_MANUAL / "02-archiving-parser.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `([a-z_]+)`", text, re.M))
    real = {
        name
        for name in inspect.signature(ArchivingResultParser.__init__).parameters
        if name != "self"
    }

    assert documented == real, (
        f"only in manual: {documented - real}; missing: {real - documented}"
    )


def test_the_manual_only_names_environment_variables_that_exist():
    """The other half of the same guard, for the settings it tells people to set."""
    import re

    from airflow_pytest_plugin import config, db, retention
    from airflow_pytest_plugin.assistant import settings as assistant_settings

    named = set()
    for path in sorted(BUILTIN_MANUAL.glob("*.md")):
        named |= set(
            re.findall(
                r"`(AIRFLOW_PYTEST_[A-Z0-9_]+)`", path.read_text(encoding="utf-8")
            )
        )
    known = {
        value
        for module in (config, retention, assistant_settings, db)
        for value in vars(module).values()
        if isinstance(value, str) and value.startswith("AIRFLOW_PYTEST_")
    }

    assert named, "the manual should name the settings it tells people to set"
    assert named <= known, (
        f"named in the manual but not in the code: {sorted(named - known)}"
    )


def test_a_section_earns_its_place_by_itself(builtin):
    """One good match does not entitle a question to the rest of the manual.

    Judged once against the best section, "which tests failed in the last run?" arrived
    with five sections and 3.4 KiB attached. Each section now has to have been named by
    something it uses rarely.
    """
    picked = builtin.select("what does coverage_source do?", budget=32_768)

    assert "coverage_source" in picked
    assert picked.count("### ") <= 3, picked.count("### ")


def test_the_builtin_manual_is_replaced_by_a_configured_one(monkeypatch, tmp_path):
    """Setting the variable means "use mine", not "use both"."""
    from airflow_pytest_plugin.assistant.settings import AssistantSettings

    monkeypatch.delenv("AIRFLOW_PYTEST_ASSISTANT_DOCS", raising=False)
    monkeypatch.delenv("AIRFLOW_PYTEST_ASSISTANT_DOCS_BUILTIN", raising=False)
    assert AssistantSettings.from_env().docs_paths == builtin_paths()

    mine = tmp_path / "runbook.md"
    mine.write_text("# Runbook\n\n## Our rules\n\nAsk Ivan.\n", encoding="utf-8")
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_DOCS", str(mine))

    assert AssistantSettings.from_env().docs_paths == (str(mine),)


def test_the_builtin_manual_can_be_switched_off_entirely(monkeypatch):
    from airflow_pytest_plugin.assistant.settings import AssistantSettings

    monkeypatch.delenv("AIRFLOW_PYTEST_ASSISTANT_DOCS", raising=False)
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_DOCS_BUILTIN", "0")

    assert AssistantSettings.from_env().docs_paths == ()
