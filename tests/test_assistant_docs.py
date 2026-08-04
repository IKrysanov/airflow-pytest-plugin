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
    DocumentationLibrary,
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
