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

from types import SimpleNamespace

import pytest

from airflow_pytest_plugin.assistant import (
    AssistantRuntime,
    FakeAnswerProvider,
    PassthroughReducer,
)
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
    assert body["context_limited"] is False
    assert body["token_usage"] is None
    assert body["evidence"][0]["report_id"] == ref.token


def test_query_with_empty_scope_returns_zero_prompt_breakdown(reports_root):
    body = (
        _client(reports_root)
        .post("/api/assistant/query", json={"question": "Anything?"})
        .json()
    )

    assert body["reports_considered"] == 0
    assert body["context_limited"] is False
    assert body["token_usage"] is None
    assert body["provider_input_bytes"] == 0
    assert body["prompt_bytes"] == {
        "system": 0,
        "user": 0,
        "context": 0,
        "history": 0,
        "structure": 0,
        "total": 0,
    }


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
    runtime = AssistantRuntime.disabled("Configure the assistant provider.")
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
    assert (
        'tokens: "LLM tokens: input {input} · output {output} · total {total}"' in html
    )
    assert "astCleanPromptParts(body.prompt_bytes)" in html
    assert "astCleanTokenUsage(body.token_usage)" in html
    assert "if (item.contextLimited)" in html
    assert "body.provider_input_bytes" in html
    assert 'button.className = "ast-copy"' in html
    assert "Math.round(kib * 100)" in html
    assert 'id="ast-scope-list"' in html and 'aria-haspopup="dialog"' in html
    assert 'id="ast-scope-dialog"' in html
    assert 'id="ast-question"' in html and 'maxlength="4000"' in html
    assert 'id="ast-clear"' in html
    assert "@media (max-width: 700px)" in html
    assert 'fetch(API + "assistant/status")' in html
    assert 'fetch(API + "assistant/query"' in html
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
    assert "Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main" in html
    assert "qwen2.5-0.5b-instruct-q4_k_m.gguf" in html
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
