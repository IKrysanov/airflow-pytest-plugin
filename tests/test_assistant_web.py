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
import pathlib
import re
from types import SimpleNamespace

import pytest

from airflow_pytest_plugin.assistant import (
    AssistantProviderResponse,
    AssistantRuntime,
    AssistantTokenUsage,
    FakeAnswerProvider,
    PassthroughReducer,
)
from airflow_pytest_plugin.assistant.exceptions import (
    AssistantProviderError as _RawError,
)
from airflow_pytest_plugin.assistant.providers.fake import FakeAssistant
from airflow_pytest_plugin.models import ReportRef
from airflow_pytest_plugin.sources import FileSystemReportSource
from conftest import write_report

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from airflow_pytest_plugin.web import create_app  # noqa: E402


def _runtime() -> AssistantRuntime:
    return AssistantRuntime(
        provider_factory=FakeAnswerProvider,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
    )


def _client(reports_root, *, can_read=lambda dag, user: True, runtime=None, user=None):
    acting_user = user if user is not None else object()
    return TestClient(
        create_app(
            FileSystemReportSource(report_root=reports_root),
            authorizer=lambda dag, user: True,
            read_authorizer=can_read,
            user_dependency=lambda: acting_user,
            assistant=runtime or _runtime(),
        )
    )


def test_status_does_not_load_models(reports_root):
    loaded = False

    def load():
        nonlocal loaded
        loaded = True
        return FakeAnswerProvider()

    runtime = AssistantRuntime(
        provider_factory=load,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=8_192,
        max_output_tokens=256,
        max_concurrent=1,
    )

    body = _client(reports_root, runtime=runtime).get("/api/assistant/status").json()

    assert body["enabled"] is True and body["provider"] == "fake"
    assert body["context_mode"] == "direct-bounded"
    assert body["max_history_messages"] == 12
    assert body["max_scope_reports"] == 100
    assert body["direct_max_summaries"] == 100
    assert body["direct_max_detail_reports"] is None
    assert body["direct_max_failures_per_report"] is None
    assert body["max_context_bytes"] == 8_192
    assert body["max_output_tokens"] == 256
    assert body["max_failure_bytes"] == 3_072
    assert body["max_capture_bytes"] == 2_048
    assert body["local_complete_tree"] is False
    assert len(body["storage_namespace"]) == 24
    assert loaded is False


def test_status_separates_browser_history_by_airflow_user(reports_root):
    alice = _client(reports_root, user=SimpleNamespace(username="alice")).get(
        "/api/assistant/status"
    )
    alice_again = _client(reports_root, user=SimpleNamespace(username="alice")).get(
        "/api/assistant/status"
    )
    bob = _client(reports_root, user=SimpleNamespace(username="bob")).get(
        "/api/assistant/status"
    )

    assert alice.json()["storage_namespace"] == alice_again.json()["storage_namespace"]
    assert alice.json()["storage_namespace"] != bob.json()["storage_namespace"]


def test_status_supports_mapping_user_identities(reports_root):
    alice = _client(reports_root, user={"username": "alice"}).get(
        "/api/assistant/status"
    )
    bob = _client(reports_root, user={"username": "bob"}).get("/api/assistant/status")

    assert alice.json()["storage_namespace"] != bob.json()["storage_namespace"]


def test_status_does_not_share_a_namespace_between_colleagues_of_one_name(reports_root):
    """A display name is not an account: two people can hold the same one."""
    first = _client(reports_root, user=SimpleNamespace(name="Ilya Krysanov")).get(
        "/api/assistant/status"
    )
    second = _client(reports_root, user=SimpleNamespace(name="Ilya Krysanov")).get(
        "/api/assistant/status"
    )

    assert first.json()["storage_namespace"] != second.json()["storage_namespace"]


def test_status_does_not_share_namespace_between_unidentified_users(reports_root):
    first = _client(reports_root, user=object()).get("/api/assistant/status")
    second = _client(reports_root, user=object()).get("/api/assistant/status")

    assert first.json()["storage_namespace"] != second.json()["storage_namespace"]


def test_query_returns_grounded_evidence(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, failed=1)

    response = _client(reports_root).post(
        "/api/assistant/query", json={"question": "What failed?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake" and body["reports_considered"] == 1
    assert body["provider_input_bytes"] > 0
    assert body["prompt_bytes"]["total"] == body["provider_input_bytes"]
    assert body["prompt_bytes"]["total"] == sum(
        value for key, value in body["prompt_bytes"].items() if key != "total"
    )
    assert body["prompt_bytes"]["system"] > 0
    assert body["prompt_bytes"]["user"] == len(b"What failed?")
    assert body["prompt_bytes"]["context"] > 0
    assert body["prompt_bytes"]["history"] == 0
    report_context = body["report_context"]
    assert report_context["format"] == "direct-snapshot-jsonl"
    assert report_context["bytes"] == len(report_context["content"].encode())
    assert report_context["bytes"] == body["prompt_bytes"]["context"]
    assert "RUN SUMMARIES" in report_context["content"]
    assert '"dag_id":"dag"' in report_context["content"]
    assert body["context_limited"] is False
    assert body["output_limited"] is False
    assert body["token_usage"] is None
    assert body["evidence"][0]["report_id"] == ref.token


def test_query_with_an_empty_scope_still_reports_what_it_sent(reports_root):
    """An empty scope is answered by the model now, so the breakdown is not all zeroes.

    That is the honest number: a call really was made, with the system prompt, the
    question and an evidence block saying there is nothing to describe.
    """
    body = (
        _client(reports_root)
        .post("/api/assistant/query", json={"question": "Anything?"})
        .json()
    )

    assert body["reports_considered"] == 0
    assert body["context_limited"] is False
    assert body["output_limited"] is False
    assert body["evidence"] == []
    assert body["prompt_bytes"]["system"] > 0
    assert body["prompt_bytes"]["user"] > 0
    assert body["prompt_bytes"]["total"] == body["provider_input_bytes"]
    assert body["prompt_bytes"]["total"] == sum(
        body["prompt_bytes"][part]
        for part in ("system", "user", "context", "history", "structure")
    )


def test_query_rechecks_selected_report_rbac(reports_root):
    public = ReportRef("public", "r1", "task", 1)
    secret = ReportRef("secret", "r1", "task", 1)
    write_report(reports_root, public, failed=1)
    write_report(reports_root, secret, failed=1)
    client = _client(reports_root, can_read=lambda dag, user: dag == "public")

    denied = client.post(
        "/api/assistant/query",
        json={"question": "Inspect it", "scope": {"report_ids": [secret.token]}},
    )
    allowed = client.post(
        "/api/assistant/query",
        json={"question": "Inspect it", "scope": {"report_ids": [public.token]}},
    )

    assert denied.status_code == 403 and "secret" not in denied.text
    assert allowed.status_code == 200 and "secret" not in allowed.text


def test_query_filters_forbidden_dags_from_global_scope(reports_root):
    write_report(reports_root, ReportRef("public", "r1", "task", 1), failed=1)
    write_report(reports_root, ReportRef("secret", "r1", "task", 1), failed=1)

    body = (
        _client(reports_root, can_read=lambda dag, user: dag == "public")
        .post("/api/assistant/query", json={"question": "Summarize"})
        .json()
    )

    assert body["reports_considered"] == 1
    assert "secret" not in str(body)


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"question": ""}, 422),
        ({"question": "   "}, 400),
        ({"question": "x" * 4_001}, 422),
        (
            {
                "question": "x",
                "history": [{"role": "user", "content": "x"} for _ in range(13)],
            },
            422,
        ),
        ({"question": "x", "scope": {"report_ids": ["x"] * 101}}, 422),
    ],
)
def test_query_bounds_user_controlled_context(reports_root, body, status):
    assert (
        _client(reports_root).post("/api/assistant/query", json=body).status_code
        == status
    )


def test_query_body_is_capped_before_json_decode(reports_root):
    response = _client(reports_root).post(
        "/api/assistant/query",
        content=b'{"question":"' + b"x" * (70 * 1024) + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_disabled_query_returns_configuration_reason(reports_root):
    # Configured but not working: the endpoints stay so the panel can explain itself. A
    # deployment that set no provider has no assistant endpoints at all -- see
    # test_no_provider_means_no_assistant_endpoints_at_all.
    runtime = AssistantRuntime.disabled(
        "Configure the assistant provider.", configured=True
    )
    response = _client(reports_root, runtime=runtime).post(
        "/api/assistant/query", json={"question": "Anything?"}
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Configure the assistant provider."


def test_openapi_documents_assistant_routes(reports_root):
    doc = _client(reports_root).get("/api/openapi.json").json()

    assert doc["paths"]["/api/assistant/status"]["get"]["tags"] == ["assistant"]
    operation = doc["paths"]["/api/assistant/query"]["post"]
    assert operation["tags"] == ["assistant"]
    assert {"400", "403", "429", "502", "503"} <= set(operation["responses"])


def test_viewer_contains_a_lazy_accessible_assistant_dialog(reports_root):
    html = _client(reports_root).get("/").text

    assert 'id="assistant-btn"' in html and 'aria-controls="assistant-dialog"' in html
    assert (
        '<dialog id="assistant-dialog"' in html
        and 'aria-labelledby="ast-title"' in html
    )
    assert '<span id="assistant-btn-label">AI assistant</span>' in html
    assert 'button: "AI-ассистент"' in html
    assert '<span id="ast-title-text">Report assistant</span>' in html
    assert '<code class="ast-beta">BETA</code>' in html
    assert 'id="ast-session-tokens"' in html
    assert 'id="ast-reset-size"' not in html
    assert 'id="ast-messages"' in html and 'aria-live="polite"' in html
    assert 'id="ast-scope"' in html and 'aria-live="polite"' in html
    assert 'id="ast-processing"' in html and 'aria-live="polite"' in html
    assert 'id="ast-context" class="ast-context" hidden' in html
    assert 'class="ast-form-actions"' in html
    assert 'id="ast-context-label"' not in html
    assert 'className = "ast-limit-button"' in html
    assert 'tooltip.setAttribute("role", "region")' in html
    assert 'button.setAttribute("aria-expanded", "false")' in html
    assert "disclosure.dataset.open = String(open)" in html
    assert 'astAppendCodeValue(copy, model.copy, "visible", model.visible)' in html
    assert "failure details: while they fit" not in html
    assert "детали падений: пока помещаются" not in html
    assert 'promptSize: "Sent to LLM"' in html
    assert 'promptSize: "Отправлено в LLM"' in html
    assert 'promptContext: "Context data"' in html
    assert 'promptHistory: "История"' in html
    assert 'copyAnswer: "Copy"' in html
    assert 'copyAnswer: "Копировать"' in html
    assert 'contextReview: "Context overview"' in html
    assert 'contextReview: "Обзор контекста"' in html
    assert 'id="ast-report-context-wrap"' in html
    assert 'contextWrap: "Wrap lines"' in html
    assert 'contextWrap: "Перенос строк"' in html
    assert 'outputLimited: "The model reached its output-token limit' in html
    assert "body.output_limited === true" in html
    assert (
        'tokens: "LLM tokens: input {input} · output {output} · total {total}"' in html
    )
    assert 'sessionTokens: "Session total: {total} tokens"' in html
    assert 'sessionTokens: "За сессию: {total} токенов"' in html
    assert "astAddSessionTokens(pendingItem.tokenUsage)" in html
    assert "sessionTotalTokens: astSessionTotalTokens" in html
    assert "astCleanPromptParts(body.prompt_bytes)" in html
    assert "astCleanTokenUsage(body.token_usage)" in html
    # Streaming, Stop, and the pending answer that lives in the transcript.
    assert 'API + "assistant/stream"' in html
    assert "AbortController" in html and 'id="ast-stop"' in html
    assert 'stop: "Остановить"' in html
    assert "pending: true, stopped: false" in html
    assert "astCleanReportContext(body.report_context)" in html
    assert "if (item.contextLimited)" in html
    assert "body.provider_input_bytes" in html
    assert 'button.className = "ast-copy"' in html
    assert "Math.round(kib * 100)" in html
    assert 'id="ast-scope-list"' in html and 'aria-haspopup="dialog"' in html
    assert 'id="ast-scope-dialog"' in html
    assert 'id="ast-report-context-dialog"' in html
    assert 'id="ast-report-context-code"' in html
    assert 'className = "ast-context-review"' in html
    assert (
        'document.getElementById("ast-report-context-code").textContent = context.content'
        in html
    )
    assert 'id="ast-question"' in html and 'maxlength="4000"' in html
    assert 'id="ast-clear"' in html
    assert "@media (max-width: 700px)" in html
    assert 'fetch(API + "assistant/status")' in html
    assert 'fetch(API + "assistant/stream"' in html
    assert "sessionStorage.setItem(AST_STORAGE_KEY" in html
    assert "sessionStorage.getItem(AST_STORAGE_KEY)" in html
    assert "localStorage.setItem(AST_WINDOW_PREFS_KEY" in html
    assert "sessionStorage.setItem(AST_WINDOW_OPEN_KEY" in html
    assert "if (astWasOpen()) astOpen()" in html
    assert "astUseStorageNamespace(status.storage_namespace)" in html
    assert "slice(-AST_MAX_MESSAGES)" in html
    assert "astStatus.max_scope_reports" in html
    assert "astRenderMarkdown(body, text)" in html
    assert "astAppendTable(root, headers, rows)" in html
    assert 'box.className = "ast-msg assistant ast-waiting"' in html
    assert 'typeof astUpdateScope === "function"' in html
    for placeholder in (
        "__ASSISTANT_CSS__",
        "__ASSISTANT_BUTTON__",
        "__ASSISTANT_PANEL__",
        "__ASSISTANT_JS__",
    ):
        assert placeholder not in html


def test_help_explains_how_to_install_the_local_gguf_model(reports_root):
    html = _client(reports_root).get("/help").text

    assert "assistant-anthropic,assistant-local" in html
    assert "Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main" in html
    assert "qwen2.5-1.5b-instruct-q4_k_m.gguf" in html
    assert "installs the llama.cpp runtime only; it does not bundle a model" in html
    assert "указывать на доступный для чтения файл .gguf" in html
    assert "AIRFLOW_PYTEST_ASSISTANT_DIRECT_MAX_SUMMARIES=100" in html
    assert "AIRFLOW_PYTEST_ASSISTANT_TRACEBACK_BYTES=3072" in html
    assert "AIRFLOW_PYTEST_ASSISTANT_CAPTURE_BYTES=2048" in html
    assert "1 KiB = 1024 bytes" in html
    assert "1 KiB = 1024 байта" in html


def test_assistant_renders_model_text_without_inner_html(reports_root):
    html = _client(reports_root).get("/").text
    start = html.index("// -- Report assistant")
    script = html[start : html.index("load();", start)]

    assert "body.textContent = text" in script
    assert ".innerHTML" not in script


def test_long_prior_answer_does_not_break_the_next_question(reports_root):
    """A follow-up must survive the model's own previous long answer.

    The browser replays the transcript verbatim, and an answer is capped at 64 KiB, not
    at the per-turn prompt clip. Rejecting the replay makes the chat unusable until the
    user clears it, so the wire contract has to accept it and the prompt clip trims it.
    """
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    long_answer = "Подробный разбор падений. " * 800

    response = _client(reports_root).post(
        "/api/assistant/query",
        json={
            "question": "Продолжи анализ",
            "history": [
                {"role": "user", "content": "Что упало?"},
                {"role": "assistant", "content": long_answer},
            ],
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert 0 < body["prompt_bytes"]["history"] <= 16_000


def test_status_publishes_the_history_character_limit(reports_root):
    body = _client(reports_root).get("/api/assistant/status").json()

    assert body["max_history_chars"] >= 4_000
    assert body["max_history_bytes"] == 16_000


def _events(response) -> list[tuple[str, dict]]:
    """Parse a Server-Sent Event body into ``(event, payload)`` pairs."""
    parsed: list[tuple[str, dict]] = []
    for block in response.text.split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if name is not None and data is not None:
            parsed.append((name, data))
    return parsed


def test_stream_sends_meta_then_deltas_then_done(reports_root):
    ref = ReportRef("dag", "run", "task", 1)
    write_report(reports_root, ref, failed=1)

    response = _client(reports_root).post(
        "/api/assistant/stream", json={"question": "What failed?"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert [name for name, _ in events][0] == "meta"
    assert [name for name, _ in events][-1] == "done"
    names = [name for name, _ in events]
    assert names.count("delta") > 1, "the offline provider streams word by word"

    meta = events[0][1]
    assert meta["provider"] == "fake" and meta["reports_considered"] == 1
    assert meta["prompt_bytes"]["total"] == meta["provider_input_bytes"] > 0
    assert meta["report_context"]["bytes"] == meta["prompt_bytes"]["context"]
    assert "RUN SUMMARIES" in meta["report_context"]["content"]

    streamed = "".join(
        payload["text"] for name, payload in events if name == "delta"
    ).strip()
    done = events[-1][1]
    assert done["answer"] == streamed
    assert done["evidence"][0]["report_id"] == ref.token
    assert done["output_limited"] is False


def test_stream_matches_the_blocking_answer_exactly(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _client(reports_root)

    blocking = client.post("/api/assistant/query", json={"question": "Same?"}).json()
    streamed = _events(
        client.post("/api/assistant/stream", json={"question": "Same?"})
    )[-1][1]

    for field in ("answer", "prompt_bytes", "report_context", "scope", "evidence"):
        assert streamed[field] == blocking[field], field


def test_stream_rejects_a_forbidden_report_before_any_event(reports_root):
    secret = ReportRef("secret", "run", "task", 1)
    write_report(reports_root, secret, failed=1)
    client = _client(reports_root, can_read=lambda dag, user: dag != "secret")

    response = client.post(
        "/api/assistant/stream",
        json={"question": "leak", "scope": {"report_ids": [secret.token]}},
    )

    assert response.status_code == 403
    assert "event:" not in response.text


def test_stream_answers_an_empty_scope_like_any_other_question(reports_root):
    """Same event shape whether or not a report matched: meta, deltas, done."""
    events = _events(
        _client(reports_root).post(
            "/api/assistant/stream", json={"question": "Anything?"}
        )
    )

    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done"
    done = events[-1][1]
    assert done["reports_considered"] == 0
    assert done["prompt_bytes"]["total"] > 0
    assert done["evidence"] == []


def test_stream_body_is_capped_before_json_decode(reports_root):
    response = _client(reports_root).post(
        "/api/assistant/stream",
        content=b'{"question":"' + b"x" * (70 * 1024) + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_body_limit_middleware_does_not_fake_a_disconnect(reports_root):
    """Guarded endpoints must still be able to stream.

    The limit middleware buffers the request body and replays it. Answering every later
    ``receive()`` with ``http.disconnect`` told Starlette the client had gone, so it
    cancelled the streaming task and the response body came back empty.
    """
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    response = _client(reports_root).post(
        "/api/assistant/stream", json={"question": "Still connected?"}
    )

    assert response.status_code == 200
    assert response.text.strip(), "streaming body was cancelled before the first event"


def _health_client(reports_root, monkeypatch, *, enabled="1", runtime=None):
    if enabled is None:
        monkeypatch.delenv("AIRFLOW_PYTEST_ASSISTANT_HEALTHCHECK", raising=False)
    else:
        monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_HEALTHCHECK", enabled)
    return _client(reports_root, runtime=runtime)


def test_health_endpoint_is_off_unless_an_operator_opts_in(reports_root, monkeypatch):
    """It costs provider money, so it must not exist by default."""
    client = _health_client(reports_root, monkeypatch, enabled=None)

    assert client.post("/api/assistant/health").status_code == 404


def test_health_endpoint_reports_a_working_provider(reports_root, monkeypatch):
    body = (
        _health_client(reports_root, monkeypatch).post("/api/assistant/health").json()
    )

    assert body["ok"] is True
    assert body["provider"] == "fake" and body["model"] == "offline-fake"
    assert body["detail"] is None
    assert body["cached"] is False
    assert isinstance(body["latency_ms"], int)


def test_health_endpoint_returns_502_when_the_provider_is_broken(
    reports_root, monkeypatch
):
    class BrokenProvider:
        name = "broken"
        model = "broken-1"

        def answer(self, *, system: str, prompt: str, max_tokens: int) -> str:
            del system, prompt, max_tokens
            raise RuntimeError("401 unauthorized")

        def close(self) -> None:
            return None

    runtime = AssistantRuntime(
        provider_factory=BrokenProvider,
        reducer_factory=PassthroughReducer,
        provider_name="broken",
        model_name="broken-1",
        context_model_name=None,
        max_context_bytes=8_192,
        max_output_tokens=256,
        max_concurrent=1,
    )
    response = _health_client(reports_root, monkeypatch, runtime=runtime).post(
        "/api/assistant/health"
    )

    # A reachable endpoint that reports a broken dependency: the body is the diagnosis.
    assert response.status_code == 502
    body = response.json()
    assert body["ok"] is False and "401" in body["detail"]


def test_health_endpoint_is_get_free_and_bounded(reports_root, monkeypatch):
    client = _health_client(reports_root, monkeypatch)

    # GET must not trigger a paid call; the check is an explicit action.
    assert client.get("/api/assistant/health").status_code == 405
    first = client.post("/api/assistant/health").json()
    second = client.post("/api/assistant/health").json()
    assert second["cached"] is True and second["checked_at"] == first["checked_at"]


def test_health_endpoint_is_documented(reports_root, monkeypatch):
    doc = _health_client(reports_root, monkeypatch).get("/api/openapi.json").json()

    operation = doc["paths"]["/api/assistant/health"]["post"]
    assert operation["tags"] == ["assistant"]
    assert "404" in operation["responses"]


def _rate_limited_client(reports_root, **limits):
    runtime = AssistantRuntime(
        provider_factory=FakeAnswerProvider,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        **limits,
    )
    return _client(
        reports_root, runtime=runtime, user=SimpleNamespace(username="alice")
    )


def test_rate_limited_query_answers_429_with_retry_after(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _rate_limited_client(reports_root, rate_limit=1, rate_window_seconds=60.0)

    assert (
        client.post("/api/assistant/query", json={"question": "a"}).status_code == 200
    )
    refused = client.post("/api/assistant/query", json={"question": "b"})

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0
    assert "too quickly" in refused.json()["detail"]


def test_rate_limited_stream_is_refused_before_any_event(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    client = _rate_limited_client(reports_root, rate_limit=1, rate_window_seconds=60.0)

    assert (
        client.post("/api/assistant/stream", json={"question": "a"}).status_code == 200
    )
    refused = client.post("/api/assistant/stream", json={"question": "b"})

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0
    assert "event:" not in refused.text


def test_status_publishes_the_configured_limits(reports_root):
    body = (
        _rate_limited_client(reports_root, rate_limit=25, daily_token_quota=500_000)
        .get("/api/assistant/status")
        .json()
    )

    assert body["rate_limit"] == 25
    assert body["daily_token_quota"] == 500_000
    assert body["rate_window_seconds"] == 3_600.0


def test_help_does_not_recommend_a_model_measured_as_unusable(reports_root):
    """0.5B kept 24% of the required facts: worse than sending no local model at all."""
    page = _client(reports_root).get("/help").text

    lower = page.lower()
    assert "qwen2.5-1.5b-instruct" in lower
    # Naming it as a warning is fine; handing out its path or download URL is not.
    assert "qwen2.5-0.5b-instruct" not in lower


def test_stream_reports_local_progress_before_the_first_token(reports_root):
    """Local mode is silent for up to two minutes; the wait needs a visible end."""
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class ChunkedReducer:
        name = "local.gguf"

        def reduce(self, *, question: str, context: str) -> str:
            del question
            return f"partial [R1] {len(context)}"

        def close(self) -> None:
            return None

    runtime = AssistantRuntime(
        provider_factory=FakeAssistant,
        reducer_factory=ChunkedReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name="local.gguf",
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
        local_input_bytes=4_096,
    )
    client = _client(reports_root, runtime=runtime)

    events = _events(
        client.post("/api/assistant/stream", json={"question": "What failed?"})
    )

    names = [name for name, _ in events]
    assert names[0] == "progress", names[:3]
    assert "meta" in names and names[-1] == "done"
    # Progress must arrive before meta: that is the whole point of it.
    assert names.index("progress") < names.index("meta")
    phases = [payload["phase"] for name, payload in events if name == "progress"]
    assert phases[0] == "loading_model"
    assert "local_reduce" in phases


def test_direct_mode_streams_no_progress_it_has_nothing_to_wait_for(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    response = _client(reports_root).post(
        "/api/assistant/stream", json={"question": "What failed?"}
    )
    names = [name for name, _ in _events(response)]

    assert "progress" not in names
    assert names[0] == "meta"


def test_every_assistant_dialog_lifts_the_embedded_iframe(reports_root):
    """A modal missing from updateParentDim lets clicks fall through to Airflow's chrome.

    The viewer runs inside an iframe in Airflow; the page only lifts itself while a modal
    is open, and it decides that from an explicit list of dialog ids.
    """
    html = _client(reports_root).get("/").text
    dim = html[html.index("function updateParentDim()") :]
    dim = dim[: dim.index("setLocalDim(anyOpen)")]

    declared = set(re.findall(r'getElementById\("([a-z-]+)"\)', dim))
    declared |= set(re.findall(r"\((\w+Dlg) &&", dim))
    modals = set(re.findall(r'<dialog id="(ast-[a-z-]+|assistant-dialog)"', html))

    missing = sorted(name for name in modals if name not in declared)
    assert missing == [], f"dialogs not lifting the iframe: {missing}"


class _SurrogateProvider:
    """A provider whose output is not encodable UTF-8.

    Real models emit broken surrogate pairs, and captured test output can carry anything;
    either way the text reaches us as a ``str`` that ``encode()`` refuses.
    """

    name = "fake"
    model = "offline-fake"

    def answer(self, *, system: str, prompt: str, max_tokens: int):
        del system, prompt, max_tokens
        return AssistantProviderResponse(text="before \ud800 after [R1]")

    def stream(self, *, system: str, prompt: str, max_tokens: int):
        del system, prompt, max_tokens
        yield "before \ud800"
        yield " after [R1]"

    def close(self) -> None:
        return None


def test_an_unencodable_answer_does_not_break_the_stream(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    response = _client(reports_root, runtime=_runtime_with(_SurrogateProvider)).post(
        "/api/assistant/stream", json={"question": "What failed?"}
    )

    assert response.status_code == 200
    names = [name for name, _ in _events(response)]
    assert names[-1] == "done", names


def test_an_unencodable_answer_does_not_break_the_json_reply(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    response = _client(reports_root, runtime=_runtime_with(_SurrogateProvider)).post(
        "/api/assistant/query", json={"question": "What failed?"}
    )

    assert response.status_code == 200, response.text
    assert "after" in response.json()["answer"]


def _runtime_with(provider):
    """A runtime around one deliberately awkward provider."""
    return AssistantRuntime(
        provider_factory=provider,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=1,
    )


def _locale_keys(source: str, marker: str) -> dict[str, set[str]]:
    """Return the translation keys defined per locale in a JS string table.

    String literals are blanked first: the values are prose, and "reports processed:" in
    one of them is not a key.
    """
    block = _without_literals(source[source.index(marker) :])
    locales: dict[str, set[str]] = {}
    current = None
    depth = 0
    for line in block.splitlines():
        opened = re.match(r"\s*(en|ru):\s*\{", line)
        if opened:
            current, depth = opened.group(1), 1
            locales[current] = set()
            continue
        if current is None:
            continue
        depth += line.count("{") - line.count("}")
        for key in re.findall(r"(?:^|\s|\{)([A-Za-z][A-Za-z0-9_]*)\s*:", line):
            locales[current].add(key)
        if depth <= 0:
            current = None
            if len(locales) == 2:
                break
    return locales


def _without_literals(source: str) -> str:
    """Replace the contents of every JS string literal with spaces, keeping line breaks."""
    out: list[str] = []
    quote = None
    escaped = False
    for char in source:
        if quote:
            out.append("\n" if char == "\n" else " ")
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
                out[-1] = char
            continue
        if char in "\"'":
            quote = char
        out.append(char)
    return "".join(out)


def test_every_assistant_string_exists_in_both_languages(reports_root):
    """A key present in one locale renders as `undefined` in the other.

    Nothing fails, nothing logs -- the word simply disappears from a button, which is why
    this drifts silently every time a control is added.
    """
    from airflow_pytest_plugin.web.assistant_templates import assistant_js

    locales = _locale_keys(assistant_js(), "var AST_I18N")

    assert set(locales) == {"en", "ru"}, sorted(locales)
    assert locales["en"] - locales["ru"] == set(), "missing Russian"
    assert locales["ru"] - locales["en"] == set(), "missing English"


def test_every_help_string_exists_in_both_languages(reports_root):
    from airflow_pytest_plugin.web.help_templates import help_html

    page = help_html()
    referenced = set(re.findall(r'data-i18n(?:-html)?="([A-Za-z0-9]+)"', page))
    locales = _locale_keys(page, "var HELP_I18N")

    missing_en = referenced - locales.get("en", set())
    missing_ru = referenced - locales.get("ru", set())
    assert missing_en == set(), (
        f"English strings referenced but never defined: {missing_en}"
    )
    assert missing_ru == set(), (
        f"Russian strings referenced but never defined: {missing_ru}"
    )


def _routeless_client(reports_root, runtime):
    from airflow_pytest_plugin.web import create_app

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    return TestClient(
        create_app(
            FileSystemReportSource(report_root=reports_root),
            authorizer=lambda dag, u: True,
            read_authorizer=lambda dag, u: True,
            user_dependency=lambda: {"username": "alice"},
            assistant=runtime,
        )
    )


ASSISTANT_ROUTES = [
    ("GET", "/api/assistant/status"),
    ("POST", "/api/assistant/query"),
    ("POST", "/api/assistant/stream"),
    ("GET", "/api/assistant/history"),
    ("DELETE", "/api/assistant/history"),
    ("POST", "/api/assistant/health"),
]


@pytest.mark.parametrize("method, path", ASSISTANT_ROUTES)
def test_no_provider_means_no_assistant_endpoints_at_all(reports_root, method, path):
    """Nobody asked for this feature, so it should not be reachable, not merely refuse.

    A disabled endpoint is still an endpoint: it parses bodies, appears in the schema and
    has to be reasoned about. When no provider is configured there is nothing behind it.
    """
    runtime = AssistantRuntime.disabled("Set the provider.", configured=False)

    response = _routeless_client(reports_root, runtime).request(method, path)

    assert response.status_code == 404, f"{method} {path} -> {response.status_code}"


@pytest.mark.parametrize("method, path", ASSISTANT_ROUTES[:5])
def test_a_configured_but_broken_assistant_keeps_its_endpoints(
    reports_root, method, path
):
    """The operator asked for it, so the panel has to be able to say what went wrong."""
    runtime = AssistantRuntime.disabled("SDK missing.", configured=True)

    response = _routeless_client(reports_root, runtime).request(method, path)

    assert response.status_code != 404, f"{method} {path} disappeared"


def test_no_provider_leaves_the_assistant_out_of_the_api_schema(reports_root):
    runtime = AssistantRuntime.disabled("Set the provider.", configured=False)

    doc = _routeless_client(reports_root, runtime).get("/api/openapi.json").json()

    assert not [path for path in doc["paths"] if "assistant" in path], doc[
        "paths"
    ].keys()


def test_no_provider_still_leaves_the_rest_of_the_viewer_working(reports_root):
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    runtime = AssistantRuntime.disabled("Set the provider.", configured=False)
    client = _routeless_client(reports_root, runtime)

    assert client.get("/api/reports").status_code == 200
    assert client.get("/").status_code == 200


def test_no_provider_leaves_the_chat_out_of_the_page_entirely(reports_root):
    """Shipping the client anyway means a 404 in every visitor's console on every load."""
    runtime = AssistantRuntime.disabled("Set the provider.", configured=False)

    html = _routeless_client(reports_root, runtime).get("/").text

    for marker in (
        'id="assistant-btn"',  # the button
        '<dialog id="assistant-dialog"',  # the panel
        '<dialog id="ast-chats-dialog"',  # the chat list
        "assistant/status",  # and any call to a route that is not there
        "assistant/stream",
    ):
        assert marker not in html, marker
    # And nothing is left half-substituted.
    assert "__ASSISTANT" not in html
    # The main script only ever looks these up defensively, which stays safe.
    assert 'getElementById("ast-chats-dialog")' in html


def test_a_configured_assistant_still_ships_its_client(reports_root):
    runtime = AssistantRuntime.disabled("SDK missing.", configured=True)

    html = _routeless_client(reports_root, runtime).get("/").text

    assert "assistant-btn" in html and "assistant/status" in html


ASSISTANT_DOC = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/airflow_pytest_plugin/assistant/README.md"
)
ROOT_DOC = pathlib.Path(__file__).resolve().parents[1] / "README.md"


def test_every_assistant_setting_is_documented_where_it_now_lives():
    """The assistant's documentation moved out of the main README.

    A setting added later is easy to document in the file that no longer owns it, or in
    neither -- so both are checked, and the assistant's own settings have to be in its own
    file.
    """
    defined = set()
    for path in (pathlib.Path(__file__).resolve().parents[1] / "src").rglob("*.py"):
        defined |= set(
            re.findall(r'"(AIRFLOW_PYTEST_ASSISTANT_[A-Z_]+)"', path.read_text())
        )
    documented = set(
        re.findall(r"`(AIRFLOW_PYTEST_ASSISTANT_[A-Z_]+)`", ASSISTANT_DOC.read_text())
    )

    assert defined, "no assistant settings found at all -- the scan is broken"
    assert defined - documented == set(), sorted(defined - documented)


def test_the_main_readme_points_at_the_assistant_documentation():
    root = ROOT_DOC.read_text()

    assert "src/airflow_pytest_plugin/assistant/README.md" in root
    # And it keeps only a summary: the detail lives in the other file now.
    section = root[root.index("## Report assistant") :]
    section = section[: section.index("\n## ")]
    assert len(section.splitlines()) < 40, "the summary grew back into a manual"


def test_the_assistant_documentation_links_back():
    assert "../../../README.md" in ASSISTANT_DOC.read_text()


CHANGELOG = pathlib.Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def test_every_database_command_is_documented():
    """A subcommand nobody documents is a subcommand nobody runs.

    `rotate-key` is the one an operator has to know about *before* they need it -- by the
    time the transcripts are unreadable, running it no longer helps.
    """
    source = (
        pathlib.Path(__file__).resolve().parents[1] / "src/airflow_pytest_plugin/db.py"
    ).read_text()
    choices = set(
        re.findall(r'"([a-z-]+)"', re.search(r"choices=\(([^)]+)\)", source).group(1))
    )
    documented = ASSISTANT_DOC.read_text()

    assert choices, "the CLI choices could not be read -- the scan is broken"
    missing = {name for name in choices if f"db {name}" not in documented}
    assert missing == set(), sorted(missing)


def test_the_release_notes_do_not_promise_rotation_without_the_command():
    """Sharing Airflow's Fernet key does not mean sharing Airflow's rotation.

    `airflow rotate-fernet-key` re-encrypts Airflow's own connections and variables and
    knows nothing about this plugin's table, so "rotation works the same way" is advice
    that costs the reader every stored transcript at the step where they drop the old
    key. Wherever the notes raise rotation, the command that actually moves the chat
    across has to be on the same page.
    """
    notes = CHANGELOG.read_text()
    section = notes[notes.index("## [0.8.0]") :]
    section = section[: section.index("\n## [0.7.0]")]

    if "rotation" in section or "rotate" in section:
        assert "rotate-key" in section, (
            "rotation is promised but the command is missing"
        )


def test_every_published_command_has_a_label_in_both_languages(reports_root):
    """The server owns the names, the browser owns the wording -- both must be complete."""
    from airflow_pytest_plugin.assistant.prompts import command_catalogue
    from airflow_pytest_plugin.web.assistant_templates import assistant_js

    locales = _locale_keys(assistant_js(), "var AST_I18N")

    for command in command_catalogue():
        key = f"command_{command['name']}"
        assert key in locales["en"], key
        assert key in locales["ru"], key


def test_an_error_detail_is_scrubbed_and_bounded_on_the_way_out(
    reports_root, monkeypatch
):
    """The last point before the message leaves the server is where it must be safe.

    Assistant errors are built from safe text by convention -- the provider adapter
    scrubs and clips the SDK's own exception before wrapping it. Convention is not a
    guarantee: it lives far from the socket, in a different module, and the next error
    raised from somewhere new inherits none of it. So the sink enforces it too, for both
    ways out: the JSON error and the `error` event on the stream.
    """
    secret = "assistant-outbound-private-value"
    monkeypatch.setenv("ASSISTANT_OUTBOUND_SECRET", secret)
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class Leaky(FakeAnswerProvider):
        def answer(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            raise _RawError(f"upstream said {secret} " + "x" * 5_000)

        def stream(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            raise _RawError(f"upstream said {secret} " + "x" * 5_000)
            yield ""  # pragma: no cover - makes this a generator

    runtime = AssistantRuntime(
        provider_factory=Leaky,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
    )
    client = _client(reports_root, runtime=runtime)

    blocking = client.post("/api/assistant/query", json={"question": "what failed?"})
    assert secret not in blocking.text, blocking.text[:200]
    assert len(blocking.json()["detail"]) <= 300

    with client.stream(
        "POST", "/api/assistant/stream", json={"question": "what failed?"}
    ) as response:
        streamed = "".join(response.iter_text())
    assert secret not in streamed, streamed[:200]
    for line in streamed.splitlines():
        if line.startswith("data:") and '"detail"' in line:
            assert len(json.loads(line[5:])["detail"]) <= 300


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("anthropic", "AnthropicAssistant"),
        ("openai", "OpenAIAssistant"),
        ("gigachat", "GigaChatAssistant"),
    ],
)
def test_each_provider_name_selects_its_own_adapter(provider, expected, monkeypatch):
    """The name in the environment picks the adapter, and nothing else does.

    Each branch is one line, which is exactly why a typo in one of them survives review:
    the deployment that would notice is the one that configured that single provider.
    """
    from airflow_pytest_plugin.assistant import factory
    from airflow_pytest_plugin.assistant import settings as settings_mod

    monkeypatch.setenv(settings_mod.PROVIDER_ENV, provider)
    built = settings_mod.AssistantSettings.from_env()

    made: dict[str, object] = {}

    class Recorder:
        def __init__(self, configured):
            made["settings"] = configured

    monkeypatch.setattr(factory, expected, Recorder)

    assert isinstance(factory._provider_factory(built), Recorder)
    assert made["settings"] is built


def test_an_unknown_provider_name_is_refused_by_name(monkeypatch):
    from airflow_pytest_plugin.assistant import factory
    from airflow_pytest_plugin.assistant import settings as settings_mod

    monkeypatch.setenv(settings_mod.PROVIDER_ENV, "fake")
    built = settings_mod.AssistantSettings.from_env()
    object.__setattr__(built, "provider", "does-not-exist")

    with pytest.raises(RuntimeError, match="does-not-exist"):
        factory._provider_factory(built)


def test_the_shared_stores_are_only_built_when_their_limit_is_configured(monkeypatch):
    """Off by default means no table is touched, not a table that stays empty."""
    from airflow_pytest_plugin.assistant import factory
    from airflow_pytest_plugin.assistant import settings as settings_mod

    monkeypatch.setenv(settings_mod.PROVIDER_ENV, "fake")
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_DAILY_TOKEN_QUOTA", "0")
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_RATE_LIMIT", "0")
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS", "0")
    off = settings_mod.AssistantSettings.from_env()

    assert factory._quota_store(off) is None
    assert factory._rate_store(off) is None
    assert factory._history_store(off) is None

    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_DAILY_TOKEN_QUOTA", "1000")
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_RATE_LIMIT", "60")
    monkeypatch.setenv("AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS", "30")
    on = settings_mod.AssistantSettings.from_env()

    assert factory._quota_store(on) is not None
    assert factory._rate_store(on) is not None
    assert factory._history_store(on) is not None


def test_a_provider_without_streaming_still_streams_one_delta(reports_root):
    """Not every SDK offers incremental output, and the panel is built around it.

    Such a provider gets the whole answer as a single `delta`, so the browser code has
    one shape to handle rather than two, and the token accounting still arrives.
    """
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class Blocking:
        """Deliberately no `stream` attribute."""

        name = "fake"
        model = "offline-fake"

        def close(self) -> None:
            return None

        def answer(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            return AssistantProviderResponse(
                text="the whole answer at once",
                token_usage=AssistantTokenUsage(
                    input_tokens=7, output_tokens=3, total_tokens=10
                ),
                stop_reason="end_turn",
            )

    runtime = AssistantRuntime(
        provider_factory=Blocking,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
    )
    assert not hasattr(Blocking(), "stream")

    with _client(reports_root, runtime=runtime).stream(
        "POST", "/api/assistant/stream", json={"question": "what failed?"}
    ) as response:
        body = "".join(response.iter_text())

    deltas = [
        json.loads(line[5:])["text"]
        for line in body.splitlines()
        if line.startswith("data:") and '"text"' in line
    ]
    assert deltas == ["the whole answer at once"]
    done = [
        json.loads(line[5:])
        for line in body.splitlines()
        if line.startswith("data:") and '"answer"' in line
    ]
    assert done and done[-1]["answer"] == "the whole answer at once"
    assert done[-1]["token_usage"]["total_tokens"] == 10


def test_a_provider_returning_bare_text_without_streaming_also_works(reports_root):
    """The older adapter shape: a plain string, no usage object."""
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class BareText:
        name = "fake"
        model = "offline-fake"

        def close(self) -> None:
            return None

        def answer(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            return "plain string answer"

    runtime = AssistantRuntime(
        provider_factory=BareText,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
    )

    with _client(reports_root, runtime=runtime).stream(
        "POST", "/api/assistant/stream", json={"question": "what failed?"}
    ) as response:
        body = "".join(response.iter_text())

    assert '"plain string answer"' in body
    assert "event: done" in body


def test_a_stream_that_only_reports_usage_still_yields_its_text(reports_root):
    """Some SDKs deliver the text on the same object that carries the token counts."""
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)

    class UsageOnly:
        name = "fake"
        model = "offline-fake"

        def close(self) -> None:
            return None

        def answer(self, *, system, prompt, max_tokens):  # pragma: no cover - unused
            raise AssertionError("the streaming path should be taken")

        def stream(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            yield AssistantProviderResponse(
                text="answer carried on the usage object",
                token_usage=AssistantTokenUsage(
                    input_tokens=5, output_tokens=2, total_tokens=7
                ),
                stop_reason="end_turn",
            )

    runtime = AssistantRuntime(
        provider_factory=UsageOnly,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
    )

    with _client(reports_root, runtime=runtime).stream(
        "POST", "/api/assistant/stream", json={"question": "what failed?"}
    ) as response:
        body = "".join(response.iter_text())

    assert "answer carried on the usage object" in body
    assert '"total_tokens":7' in body.replace(" ", "")


def test_a_provider_failure_does_not_publish_the_sdk_message(reports_root, monkeypatch):
    """Whoever asked gets a sentence; the SDK's own words stay on the server.

    A provider exception is written for whoever holds the account: it carries request
    ids, endpoint URLs, organisation names and quota specifics. Every reader of the
    dashboard is not that person. The full text still reaches the log and the audit
    record, and `/api/assistant/health` remains the place to ask why a provider is
    unhappy -- it is operator-gated for exactly this reason.
    """
    write_report(reports_root, ReportRef("dag", "run", "task", 1), failed=1)
    sdk_text = "Error code: 401 - org_id=org-4f2a1b endpoint=https://api.internal/v1"

    class Failing(FakeAnswerProvider):
        def answer(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            raise RuntimeError(sdk_text)

        def stream(self, *, system, prompt, max_tokens):
            del system, prompt, max_tokens
            raise RuntimeError(sdk_text)
            yield ""  # pragma: no cover - makes this a generator

    runtime = AssistantRuntime(
        provider_factory=Failing,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
    )
    client = _client(reports_root, runtime=runtime)

    blocking = client.post("/api/assistant/query", json={"question": "what failed?"})
    assert blocking.status_code == 502
    assert "org-4f2a1b" not in blocking.text, blocking.text
    assert "api.internal" not in blocking.text, blocking.text
    assert blocking.json()["detail"], "the reader still has to be told something"

    with client.stream(
        "POST", "/api/assistant/stream", json={"question": "what failed?"}
    ) as response:
        streamed = "".join(response.iter_text())
    assert "org-4f2a1b" not in streamed, streamed
    assert "api.internal" not in streamed, streamed
    assert "event: error" in streamed


def test_our_own_errors_still_say_what_is_wrong(reports_root):
    """The trade only applies to somebody else's text; ours is written to be read."""
    response = _client(reports_root).post(
        "/api/assistant/query", json={"question": " "}
    )

    assert response.status_code == 400
    assert "must not be empty" in response.json()["detail"]


def _quota_runtime(quota: int) -> AssistantRuntime:
    return AssistantRuntime(
        provider_factory=FakeAnswerProvider,
        reducer_factory=PassthroughReducer,
        provider_name="fake",
        model_name="offline-fake",
        context_model_name=None,
        max_context_bytes=16_384,
        max_output_tokens=256,
        max_concurrent=2,
        daily_token_quota=quota,
    )


def test_the_status_tells_a_reader_what_is_left_of_their_budget(reports_root):
    """A quota nobody can see is a 429 that arrives without warning.

    The limit was published from the start and the spend was not, so the panel could say
    what the ceiling was but never how close somebody stood to it. `spent_today` already
    existed for exactly this and had no caller outside the tests.
    """
    runtime = _quota_runtime(10_000)
    alice = SimpleNamespace(username="alice")
    runtime.limits.charge("username:alice", 2_500)

    body = (
        _client(reports_root, runtime=runtime, user=alice)
        .get("/api/assistant/status")
        .json()
    )

    assert body["daily_token_quota"] == 10_000
    assert body["daily_tokens_spent"] == 2_500


def test_one_reader_is_not_shown_another_reader_s_spend(reports_root):
    runtime = _quota_runtime(10_000)
    runtime.limits.charge("username:alice", 4_000)

    bob = (
        _client(reports_root, runtime=runtime, user=SimpleNamespace(username="bob"))
        .get("/api/assistant/status")
        .json()
    )

    assert bob["daily_tokens_spent"] == 0


def test_no_quota_means_no_spend_to_report(reports_root):
    """Nothing is counted when nothing is bounded, so nothing is claimed."""
    body = (
        _client(
            reports_root, runtime=_quota_runtime(0), user=SimpleNamespace(username="a")
        )
        .get("/api/assistant/status")
        .json()
    )

    assert body["daily_token_quota"] == 0
    assert body["daily_tokens_spent"] is None


def test_a_viewer_with_no_identity_is_told_no_spend(reports_root):
    """An unidentifiable caller shares the anonymous bucket; publishing it would be a lie."""
    body = (
        _client(reports_root, runtime=_quota_runtime(10_000), user=object())
        .get("/api/assistant/status")
        .json()
    )

    assert body["daily_tokens_spent"] is None
