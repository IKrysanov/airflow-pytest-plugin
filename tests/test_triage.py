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

from __future__ import annotations

import json

import pytest

from airflow_pytest_plugin.models import Verdict
from airflow_pytest_plugin.triage import (
    MAX_TEXT,
    MAX_VERDICTS,
    canonical_node_key,
    distill_report,
    triage_rollup,
    triage_view,
    verdicts_from_document,
)


def _failure(nodeid: str, **verdict) -> dict:
    """One pytest-triage failure record, verdict included unless explicitly None."""
    return {
        "nodeid": nodeid,
        "pytest_args": [nodeid],
        "phase": "call",
        "outcome": "failed",
        "exc_type": verdict.pop("exc_type", "AssertionError"),
        "exc_message": "boom",
        "traceback": "…",
        "verdict": None
        if verdict.get("category") is None and "category" in verdict
        else {
            "category": verdict.get("category", "regression"),
            "hypothesis": verdict.get("hypothesis", "the loader broke"),
            "confidence": verdict.get("confidence", "high"),
            "suggested_fix": verdict.get("suggested_fix", "restore the DISTINCT"),
        },
    }


def _report(*failures: dict, **top) -> dict:
    return {
        "schema_version": 1,
        "created_at": "2026-07-26T11:12:19Z",
        "ai_model": top.get("ai_model", "claude-sonnet-5"),
        "triage_duration": top.get("triage_duration", 4.12),
        "pytest_args": [f["nodeid"] for f in failures],
        "failures": list(failures),
        "total_failures": top.get("total_failures", len(failures)),
        "total_verdicts": top.get(
            "total_verdicts", sum(1 for f in failures if f.get("verdict"))
        ),
    }


# --- node-id canonicalisation -------------------------------------------------------


@pytest.mark.parametrize(
    ("node_id", "expected"),
    [
        # pytest's native slash form -> the JUnit parser's dotted form.
        ("tests/test_x.py::test_y", "tests.test_x::test_y"),
        (
            "tests/pkg/test_x.py::TestThings::test_y",
            "tests.pkg.test_x.TestThings::test_y",
        ),
        # Already dotted: idempotent, so it is safe to apply on both sides of the join.
        ("tests.test_x::test_y", "tests.test_x::test_y"),
        ("tests.test_x.TestThings::test_y", "tests.test_x.TestThings::test_y"),
        # A parametrised id keeps its bracket suffix verbatim -- including a slash inside
        # it, which must NOT be read as a path separator.
        ("tests/test_x.py::test_y[a/b]", "tests.test_x::test_y[a/b]"),
        ("tests\\test_x.py::test_y", "tests.test_x::test_y"),
        # Degenerate inputs are returned as-is rather than mangled.
        ("test_y", "test_y"),
        ("::test_y", "test_y"),
        ("", ""),
    ],
)
def test_canonical_node_key(node_id, expected):
    assert canonical_node_key(node_id) == expected


def test_canonical_node_key_is_idempotent():
    once = canonical_node_key("tests/test_x.py::TestThings::test_y")
    assert canonical_node_key(once) == once


# --- distilling the producer's block ------------------------------------------------


def test_distill_keeps_the_judgement_and_drops_the_bulk():
    archive = distill_report(_report(_failure("tests/test_etl.py::test_load")))

    assert archive.rollup["model"] == "claude-sonnet-5"
    assert archive.rollup["duration"] == 4.12
    assert (
        archive.rollup["total_failures"] == 1 and archive.rollup["total_verdicts"] == 1
    )
    assert archive.rollup["counts"] == {"regression": 1}
    entry = archive.verdicts["tests.test_etl::test_load"]
    assert entry["category"] == "regression"
    assert entry["confidence"] == "high"
    assert entry["exc_type"] == "AssertionError"
    # The rerun selector survives in pytest's own form, ready to paste.
    assert entry["selector"] == "tests/test_etl.py::test_load"
    # The traceback and captured output stay OUT: they are already in junit.xml.
    assert "traceback" not in entry and "exc_message" not in entry


def test_a_failure_without_a_verdict_is_stored_but_not_counted():
    # pytest-triage reports the failure with verdict null. It is still worth showing -- its
    # exception type and rerun selector are there -- but it is not a judgement.
    archive = distill_report(
        _report(
            _failure("tests/test_a.py::test_1"),
            _failure("tests/test_b.py::test_2", category=None),
            total_verdicts=1,
        )
    )
    assert list(archive.verdicts) == ["tests.test_a::test_1", "tests.test_b::test_2"]
    assert archive.verdicts["tests.test_b::test_2"]["category"] is None
    assert archive.rollup["counts"] == {"regression": 1}
    assert (
        archive.rollup["total_failures"] == 2 and archive.rollup["total_verdicts"] == 1
    )


def test_a_triaged_run_with_no_provider_still_yields_a_block():
    # --ai-report without a provider: every verdict null. The block must survive, or the
    # reader cannot tell "triaged, nothing judged" from "never triaged".
    archive = distill_report(
        _report(
            _failure("tests/test_a.py::test_1", category=None),
            ai_model=None,
            triage_duration=None,
        )
    )
    assert archive.rollup["counts"] == {}
    assert archive.rollup["model"] is None and archive.rollup["duration"] is None
    assert archive.rollup["total_failures"] == 1
    # The failure is still described -- that is what report-only mode is for.
    assert archive.verdicts["tests.test_a::test_1"]["selector"]


def test_unknown_category_and_confidence_are_coerced_not_trusted():
    archive = distill_report(
        _report(
            _failure("t/a.py::test_1", category="catastrophe", confidence="certain")
        )
    )
    entry = archive.verdicts["t.a::test_1"]
    assert entry["category"] == "unknown"
    assert entry["confidence"] is None


def test_model_prose_is_clipped_and_labels_single_lined():
    archive = distill_report(
        _report(
            _failure(
                "t/a.py::test_1",
                hypothesis="x" * (MAX_TEXT + 500),
                exc_type="Assertion\nError   ",
            )
        )
    )
    entry = archive.verdicts["t.a::test_1"]
    assert len(entry["hypothesis"]) == MAX_TEXT
    assert entry["exc_type"] == "Assertion Error"


def test_verdicts_are_capped_so_the_sidecar_stays_bounded():
    archive = distill_report(
        _report(*[_failure(f"t/a.py::test_{i}") for i in range(MAX_VERDICTS + 25)])
    )
    assert len(archive.verdicts) == MAX_VERDICTS
    # The roll-up still reports what pytest-triage actually saw.
    assert archive.rollup["total_failures"] == MAX_VERDICTS + 25


def test_a_repeated_node_keeps_its_first_verdict():
    archive = distill_report(
        _report(
            _failure("t/a.py::test_1", category="regression"),
            _failure("t/a.py::test_1", category="flaky"),
        )
    )
    assert archive.verdicts["t.a::test_1"]["category"] == "regression"
    assert archive.rollup["counts"] == {"regression": 1}


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "not a report",
        42,
    ],
)
def test_a_non_report_distills_to_nothing(raw):
    assert distill_report(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        {},  # no failures key at all
        {"failures": "nope"},
        {"failures": [None, 7, "x"]},
        {"failures": [{"verdict": {"category": "env"}}]},  # no nodeid to key on
    ],
)
def test_a_malformed_report_yields_an_empty_but_valid_block(raw):
    archive = distill_report(raw)
    assert archive is not None
    assert archive.verdicts == {} and archive.rollup["counts"] == {}
    # JSON-safe on both sides, whatever came in.
    assert json.dumps(archive.rollup) and json.dumps(archive.verdicts_document())


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, "4.2", True])
def test_a_bad_duration_reads_as_unknown(duration):
    # Non-finite floats are not JSON-spec and would 500 the response serializer.
    archive = distill_report(_report(triage_duration=duration))
    assert archive.rollup["duration"] is None


# --- reading the reader's side ------------------------------------------------


def test_the_archive_round_trips_through_both_files():
    archive = distill_report(
        _report(
            _failure("tests/test_a.py::test_1", category="env"),
            _failure("tests/test_b.py::test_2", category="test_bug"),
        )
    )
    # Exactly what the producer writes: roll-up into meta.json, verdicts into their own file.
    verdicts = verdicts_from_document(archive.verdicts_document())
    summary = triage_view(
        triage_rollup({"triage": archive.rollup}), list(verdicts.values())
    )

    assert summary.model == "claude-sonnet-5"
    assert summary.total_failures == 2 and summary.total_verdicts == 2
    # Counts come back in severity order, not in the order the model answered.
    assert list(summary.counts) == ["env", "test_bug"]
    assert set(verdicts) == {"tests.test_a::test_1", "tests.test_b::test_2"}
    assert verdicts["tests.test_a::test_1"].category == "env"
    assert verdicts["tests.test_b::test_2"].selector == "tests/test_b.py::test_2"


def test_counts_are_ordered_by_severity_not_by_size():
    verdicts = [
        Verdict(category="test_bug"),
        Verdict(category="test_bug"),
        Verdict(category="regression"),
    ]
    summary = triage_view({"model": "m"}, verdicts)
    assert list(summary.counts) == ["regression", "test_bug"]


def test_the_card_only_counts_verdicts_the_table_can_show():
    # A verdict whose node id matches no JUnit case -- a collection error names the file,
    # not a test -- is real, and pytest-triage counts it. The card must not advertise a
    # category the case table has no row for, so the view counts what was ATTACHED.
    rollup = {
        "model": "m",
        "total_failures": 5,
        "total_verdicts": 5,
        "counts": {"env": 5},
    }
    summary = triage_view(rollup, [Verdict(category="regression")])
    assert summary.counts == {"regression": 1}
    assert summary.total_verdicts == 1
    # ...while the number of failures pytest-triage SAW is reported as recorded, so the
    # "1 of 5 judged" gap stays visible instead of being quietly rounded away.
    assert summary.total_failures == 5


def test_an_untriaged_run_has_no_summary():
    assert triage_view(None, []) is None
    assert triage_rollup({"summary": {}}) is None


@pytest.mark.parametrize(
    "meta",
    [None, {}, {"triage": None}, {"triage": "nope"}, {"triage": []}, "not a meta"],
)
def test_an_absent_or_malformed_block_reads_as_no_triage(meta):
    assert triage_rollup(meta) is None


@pytest.mark.parametrize(
    "document",
    [None, {}, [], "nope", 42, {"verdicts": "nope"}, {"verdicts": []}],
)
def test_an_unreadable_verdicts_document_yields_nothing(document):
    assert verdicts_from_document(document) == {}


def test_a_corrupt_stored_verdict_is_dropped_not_raised():
    verdicts = verdicts_from_document(
        {
            "verdicts": {
                "tests.a::test_1": {"category": "env", "confidence": "high"},
                "tests.a::test_2": "not an object",
                "tests.a::test_3": None,
            }
        }
    )
    assert set(verdicts) == {"tests.a::test_1"}
    assert verdicts["tests.a::test_1"].category == "env"


def test_a_corrupt_count_is_skipped_not_crashed():
    summary = triage_view({"total_failures": "many"}, [Verdict(category="env")])
    # Unparseable -> falls back to what is actually attached, rather than 500ing the view.
    assert summary.total_failures == 1


def test_stored_slash_form_keys_are_canonicalised_on_read():
    # An older archive (or another producer) may have stored pytest's native form.
    verdicts = verdicts_from_document(
        {"verdicts": {"tests/test_a.py::test_1": {"category": "flaky"}}}
    )
    assert list(verdicts) == ["tests.test_a::test_1"]


def test_verdicts_stored_inline_in_the_rollup_are_still_read():
    # Archives written before the verdicts moved into their own file keep them inline. The
    # fallback costs three lines and spares those runs a silently empty analysis.
    rollup = {"model": "m", "verdicts": {"tests.a::test_1": {"category": "env"}}}
    verdicts = verdicts_from_document(None, fallback=rollup)
    assert verdicts["tests.a::test_1"].category == "env"
    # The sidecar wins when both are present -- it is the newer, authoritative copy.
    both = verdicts_from_document(
        {"verdicts": {"tests.a::test_1": {"category": "flaky"}}}, fallback=rollup
    )
    assert both["tests.a::test_1"].category == "flaky"


def test_a_read_is_capped_even_when_the_file_is_not():
    # The producer caps what it writes; a hand-written or corrupt file need not honour it,
    # and this parse runs inside the api-server on every detail request.
    document = {
        "verdicts": {
            f"t.a::test_{i}": {"category": "env"} for i in range(MAX_VERDICTS * 3)
        }
    }
    assert len(verdicts_from_document(document)) == MAX_VERDICTS


# --- verdicts that are not judgements ------------------------------------------------
# pytest-triage stamps a stable reason on a verdict it could NOT produce -- budget spent,
# provider error (a bad API key lands here), timeout, breaker tripped -- as
# category="unknown". Those are operational failures of the triage pass, not diagnoses of
# the test, and must never be presented next to real verdicts.


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("triage budget exhausted", "triage budget exhausted"),
        ("triage timed out", "triage timed out"),
        (
            "triage provider error: 401 invalid x-api-key",
            "triage provider error: 401 invalid x-api-key",
        ),
        (
            "triage stopped: the provider kept failing",
            "triage stopped: the provider kept failing",
        ),
    ],
)
def test_a_degraded_verdict_is_not_stored_as_a_judgement(reason, expected):
    archive = distill_report(
        _report(
            _failure("t/a.py::test_1", category="regression"),
            _failure(
                "t/a.py::test_2",
                category="unknown",
                confidence="low",
                hypothesis=reason,
                suggested_fix=None,
            ),
        )
    )
    # Only the real judgement is kept: the other test is simply not judged.
    assert list(archive.verdicts) == ["t.a::test_1"]
    assert archive.rollup["counts"] == {"regression": 1}
    # ...and WHY is recorded, because "the key is wrong" is the most useful thing the run
    # can tell you -- far more than five identical "Unclear" chips.
    assert archive.rollup["incomplete"] == expected


def test_a_genuine_unknown_verdict_is_still_a_verdict():
    # The model looked and could not classify. That IS a judgement, and it is kept.
    archive = distill_report(
        _report(
            _failure(
                "t/a.py::test_1",
                category="unknown",
                hypothesis="the traceback does not say enough to classify this",
            )
        )
    )
    assert archive.verdicts["t.a::test_1"]["category"] == "unknown"
    assert archive.rollup["incomplete"] is None


def test_the_first_reason_wins_when_a_run_degrades_more_than_one_way():
    # A provider that dies mid-run: the first failures error, then the breaker trips. The
    # first reason is the cause; the rest are its consequence.
    archive = distill_report(
        _report(
            _failure(
                "t/a.py::test_1",
                category="unknown",
                hypothesis="triage provider error: boom",
            ),
            _failure(
                "t/a.py::test_2",
                category="unknown",
                hypothesis="triage stopped: the provider kept failing",
            ),
        )
    )
    assert archive.verdicts == {}
    assert archive.rollup["incomplete"] == "triage provider error: boom"


def test_the_incomplete_reason_reaches_the_view():
    summary = triage_view(
        {"model": "m", "total_failures": 5, "incomplete": "triage budget exhausted"},
        [Verdict(category="env")],
    )
    assert summary.incomplete == "triage budget exhausted"
    assert summary.to_dict()["incomplete"] == "triage budget exhausted"


# --- report-only mode (triage=True, no provider) --------------------------------------
# pytest-triage describes every failure whether or not a model judged it: exception type,
# phase, and the exact argument to rerun just that test. Dropping the unjudged ones left
# `triage=True` with nothing to show at all -- a card saying "no provider" and no per-test
# value, which is not what the flag promises.


def test_report_only_failures_are_archived_with_what_the_report_does_know():
    archive = distill_report(
        _report(
            _failure("tests/test_a.py::test_1", category=None),
            _failure("tests/test_b.py::test_2", category=None),
            ai_model=None,
        )
    )
    assert set(archive.verdicts) == {"tests.test_a::test_1", "tests.test_b::test_2"}
    entry = archive.verdicts["tests.test_a::test_1"]
    # No judgement -- but the two facts that make the failure actionable survive.
    assert entry["category"] is None
    assert entry["exc_type"] == "AssertionError"
    assert entry["selector"] == "tests/test_a.py::test_1"
    assert entry["hypothesis"] is None and entry["suggested_fix"] is None
    # Nothing was judged, so nothing is counted.
    assert archive.rollup["counts"] == {}


def test_an_unjudged_failure_is_not_counted_as_a_verdict():
    archive = distill_report(
        _report(
            _failure("t/a.py::test_1", category="env"),
            _failure("t/a.py::test_2", category=None),
        )
    )
    verdicts = verdicts_from_document(archive.verdicts_document())
    summary = triage_view(archive.rollup, list(verdicts.values()))
    assert len(verdicts) == 2  # both are shown...
    assert summary.total_verdicts == 1  # ...but only one is a judgement
    assert summary.counts == {"env": 1}


def test_a_corrupt_verdict_object_still_leaves_the_failure_actionable():
    # The verdict is unusable, but the nodeid alone yields a rerun selector -- more use than
    # dropping the failure from the view entirely.
    archive = distill_report(
        {"failures": [{"nodeid": "t/a.py::test_1", "verdict": "not-an-object"}]}
    )
    entry = archive.verdicts["t.a::test_1"]
    assert entry["category"] is None and entry["selector"] == "t/a.py::test_1"


def test_a_stored_record_with_nothing_to_show_is_dropped_on_read():
    # No category, no exception type, no selector -> an empty panel; not worth a row.
    verdicts = verdicts_from_document(
        {
            "verdicts": {
                "t.a::test_1": {"category": None, "exc_type": None, "selector": None}
            }
        }
    )
    assert verdicts == {}


@pytest.mark.parametrize("field", ["hypothesis", "suggested_fix", "exc_type"])
def test_control_characters_are_stripped_from_model_written_text(field):
    # Everything here is written by a model, through a file on a shared volume, into a JSON
    # response and a log line. A NUL or an escape sequence has no business in any of them:
    # it truncates C-based consumers, and ESC sequences repaint a terminal reading the logs.
    archive = distill_report(
        _report(_failure("t/a.py::test_1", **{field: "a\x00b\x1b[31mc\x07"}))
    )
    value = archive.verdicts["t.a::test_1"][field]
    assert "\x00" not in value and "\x1b" not in value and "\x07" not in value
    assert "a" in value and "c" in value  # the readable text survives


def test_control_characters_are_stripped_from_the_rerun_selector():
    # The selector comes from the report's own pytest_args, and ends up in a shell line the
    # user is invited to copy. An ESC sequence there repaints their terminal.
    failure = _failure("t/a.py::test_1")
    failure["pytest_args"] = ["t/a.py::test_1\x1b[2Jsomething"]
    archive = distill_report({"failures": [failure]})
    selector = archive.verdicts["t.a::test_1"]["selector"]
    assert "\x1b" not in selector and "t/a.py::test_1" in selector


def test_a_control_character_cannot_ride_in_on_the_model_name():
    archive = distill_report(_report(ai_model="claude\x00\r\nX-Injected: 1"))
    assert archive.rollup["model"] == "claude X-Injected: 1"


def test_a_verdict_key_is_never_treated_as_a_path():
    # Keys are dict lookups, never path segments -- but a traversal-shaped one must still
    # come out inert rather than resolving anywhere.
    verdicts = verdicts_from_document(
        {"verdicts": {"../../../etc/passwd::t": {"category": "env"}}}
    )
    (key,) = verdicts
    assert "/" not in key and ".." not in key


def test_a_module_and_a_same_named_class_do_not_share_a_key():
    # The one shape that could put a verdict on the WRONG test: a module `a/test_b.py` and
    # a class `test_b` inside `test_a.py`, both holding `test_x`. Real values, taken from a
    # pytest run of exactly that pair -- pytest keeps them apart by carrying the module into
    # the classname, and the canonical key must not flatten that distinction away.
    module_side = canonical_node_key("tests/a/test_b.py::test_x")
    class_side = canonical_node_key("tests/test_a.py::test_b::test_x")
    assert module_side != class_side
    # ...and the JUnit parser's own dotted ids land on the same two keys, so the join holds.
    assert canonical_node_key("tests.a.test_b::test_x") == module_side
    assert canonical_node_key("tests.test_a.test_b::test_x") == class_side
