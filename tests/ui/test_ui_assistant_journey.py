"""The user's side, in a real browser, against a real server and a real database.

Everything below is a thing a person does: open the panel, pick a command from the menu,
send it, watch it stream, start a second chat, come back to the first, reload the page.
No route stubbing -- the server answers with the offline provider and stores what it
answered, so what is asserted is what a user would actually see.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from airflow_pytest_plugin.assistant.prompts import command_catalogue

FAILING = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4" failures="2" errors="0" skipped="0" time="12">
  <testcase classname="tests.test_auth" name="test_login" time="1.1">
    <failure message="AssertionError: assert 401 == 200">
tests/test_auth.py:42: in test_login
    assert response.status_code == 200
E   AssertionError: assert 401 == 200
    </failure>
  </testcase>
  <testcase classname="tests.test_auth" name="test_logout" time="0.9">
    <failure message="ConnectionError: connection reset by peer">boom</failure>
  </testcase>
  <testcase classname="tests.test_billing" name="test_invoice" time="9.8"/>
  <testcase classname="tests.test_billing" name="test_refund" time="0.4"/>
</testsuite></testsuites>
"""


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    """A real uvicorn server with the assistant, a database and encryption on."""
    import threading
    import time

    import uvicorn
    from cryptography.fernet import Fernet

    root = tmp_path_factory.mktemp("e2e")
    reports = root / "reports"
    reports.mkdir()

    os.environ["AIRFLOW_PYTEST_ASSISTANT_DB_URL"] = f"sqlite:///{root}/plugin.db"
    os.environ["AIRFLOW_PYTEST_ASSISTANT_PROVIDER"] = "fake"
    os.environ["AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS"] = "30"
    os.environ["AIRFLOW__CORE__FERNET_KEY"] = Fernet.generate_key().decode()

    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "_root_conftest", Path("tests/conftest.py").resolve()
    )
    root_conftest = importlib.util.module_from_spec(spec)
    sys.modules["_root_conftest"] = root_conftest
    spec.loader.exec_module(root_conftest)
    write_report_xml = root_conftest.write_report_xml

    from airflow_pytest_plugin import chatcrypto, db
    from airflow_pytest_plugin.assistant import AssistantRuntime, PassthroughReducer
    from airflow_pytest_plugin.assistant.providers.fake import FakeAssistant
    from airflow_pytest_plugin.models import ReportRef
    from airflow_pytest_plugin.sources import FileSystemReportSource
    from airflow_pytest_plugin.web.app import create_app

    chatcrypto._cached = None
    for index, run in enumerate(("run_a", "run_b"), start=1):
        write_report_xml(
            str(reports),
            ReportRef("checkout", run, "pytest", 1),
            FAILING,
            created_at=f"2026-08-0{index}T10:00:00+00:00",
            summary={
                "total": 4,
                "passed": 2,
                "failed": 2,
                "skipped": 0,
                "errors": 0,
                "duration": 12.2,
                "exit_code": 1,
                "success": False,
                "failed_node_ids": [
                    "tests/test_auth.py::test_login",
                    "tests/test_auth.py::test_logout",
                ],
            },
        )
    db.upgrade()

    app = create_app(
        FileSystemReportSource(report_root=str(reports)),
        authorizer=lambda dag, user: True,
        read_authorizer=lambda dag, user: True,
        user_dependency=lambda: {"id": 42, "username": "ilya"},
        assistant=AssistantRuntime(
            provider_factory=FakeAssistant,
            reducer_factory=PassthroughReducer,
            provider_name="fake",
            model_name="offline-fake",
            context_model_name=None,
            max_context_bytes=48 * 1024,
            max_output_tokens=512,
            max_concurrent=4,
            history=db.history_store(),
            history_days=30,
        ),
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started and server.servers:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", root
    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.ui
def test_a_person_uses_the_assistant_end_to_end(live, page):
    base, root = live
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            errors.append(message.text) if message.type == "error" else None
        ),
    )

    # --- open it -------------------------------------------------------------------
    page.goto(f"{base}/", wait_until="networkidle")
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    page.locator("#assistant-btn").click()
    expect(page.locator("#assistant-dialog")).to_be_visible()

    # --- pick a command from the menu, the way a person does ------------------------
    field = page.locator("#ast-question")
    field.click()
    field.type("/")
    expect(page.locator("#ast-commands")).to_be_visible()
    # From the server's catalogue: the menu exists so the list is never written twice.
    expect(page.locator("#ast-commands .ast-command")).to_have_count(
        len(command_catalogue())
    )
    page.keyboard.press("ArrowDown")  # /compare
    page.keyboard.press("Enter")
    expect(field).to_have_value("/compare ")

    field.type("что изменилось между прогонами?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=30_000
    )

    # The question is shown as typed, command included.
    expect(page.locator(".ast-msg.user").last).to_contain_text("/compare")

    # --- the cost of that answer is visible ----------------------------------------
    expect(page.locator(".ast-msg.user .ast-prompt-row").last).to_be_visible()

    # --- "finished" has to mean "saved" ---------------------------------------------
    # Send comes back when the stream ends. At that instant the exchange must already be
    # on the server, or a reader who opens the chat list right then is shown a chat that
    # does not contain the answer they are looking at.
    expect(page.locator("#ast-stop")).to_be_hidden(timeout=30_000)
    saved = page.evaluate("async () => (await fetch('/api/assistant/history')).json()")
    assert len(saved["messages"]) == 2, saved

    # --- a second chat, then back to the first -------------------------------------
    page.locator("#ast-chats").click()
    expect(page.locator("#ast-chats-dialog")).to_be_visible()
    page.locator("#ast-chat-new").click()
    expect(page.locator("#ast-chats-dialog")).to_be_hidden()
    field.click()
    field.fill("какой тест самый медленный?")
    page.locator("#ast-send").click()
    expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=30_000
    )
    expect(page.locator("#ast-stop")).to_be_hidden(timeout=30_000)

    # Two chats now, each with its own exchange, newest first.
    page.locator("#ast-chats").click()
    items = page.locator("#ast-chats-dialog .ast-chat-item")
    expect(items).to_have_count(2)
    expect(items.first).to_contain_text("какой тест самый медленный?")
    expect(items.nth(1)).to_contain_text("/compare")
    # A person clicks the chat they recognise, not a position in a list.
    items.filter(has_text="/compare").first.click()
    expect(page.locator(".ast-msg.user").first).to_contain_text("/compare")

    # --- a reload brings the chat back from the server ------------------------------
    page.reload(wait_until="networkidle")
    page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    # The panel remembers that it was open and reopens itself, on the chat that
    # was being read -- so there is nothing to click, and the transcript comes
    # back from the server rather than from this tab.
    expect(page.locator("#assistant-dialog")).to_be_visible(timeout=15_000)
    expect(page.locator(".ast-msg.user").first).to_contain_text(
        "/compare", timeout=15_000
    )

    # --- and what is on disk is not readable ---------------------------------------
    import sqlalchemy as sa

    from airflow_pytest_plugin import db

    with db.engine().connect() as connection:
        stored = [
            row[0]
            for row in connection.execute(
                sa.text(f"select content from {db.MESSAGE_TABLE}")
            )
        ]
    assert stored, "the exchange should have been stored"
    assert all(row.startswith("gAAAAA") for row in stored), stored[:1]
    assert not any("изменилось" in row for row in stored)

    assert errors == [], errors


@pytest.mark.ui
def test_deleting_a_chat_in_one_tab_closes_it_in_the_other(live, context):
    """Two tabs, one account, one database -- and one of them holding a deleted chat.

    Each tab keeps its own copy of the open transcript, which is what makes a refresh
    instant. Nothing told the other tab the chat had been deleted, so it went on showing
    a conversation that no longer existed anywhere, and sending into it silently created
    it again under the same id.
    """
    base, _ = live
    first = context.new_page()
    second = context.new_page()
    console: list[str] = []
    second.on("pageerror", lambda error: console.append(f"pageerror: {error}"))
    second.on(
        "console",
        lambda message: (
            console.append(f"{message.type}: {message.text}")
            if message.type == "error"
            else None
        ),
    )
    for page in (first, second):
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
        page.locator("#assistant-btn").click()
        expect(page.locator("#assistant-dialog")).to_be_visible()

    # A chat of its own: this module's other test leaves chats in the same database, and
    # a reloaded tab opens the newest one.
    first.locator("#ast-chats").click()
    expect(first.locator("#ast-chats-dialog")).to_be_visible()
    first.locator("#ast-chat-new").click()
    expect(first.locator("#ast-chats-dialog")).to_be_hidden()

    # Tab one asks something, so there is a stored chat to lose.
    field = first.locator("#ast-question")
    field.click()
    field.fill("почему упал test_login?")
    first.locator("#ast-send").click()
    expect(first.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=30_000
    )
    expect(first.locator("#ast-stop")).to_be_hidden(timeout=30_000)

    # Tab two opens that same chat deliberately -- a reload would restore whichever chat
    # *it* was last reading, which is the behaviour a refresh is supposed to have.
    second.reload(wait_until="networkidle")
    second.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
    second.locator("#ast-chats").click()
    expect(second.locator("#ast-chats-dialog")).to_be_visible()
    second.locator(".ast-chat-item").filter(
        has_text="почему упал test_login?"
    ).first.click()
    expect(second.locator(".ast-msg.user").first).to_contain_text(
        "почему упал test_login?", timeout=15_000
    )

    # Tab one deletes it.
    first.locator("#ast-chats").click()
    expect(first.locator("#ast-chats-dialog")).to_be_visible()
    # By title, not by position: this module's other test leaves its own chats in the
    # same database, and the newest is not necessarily ours.
    row = (
        first.locator(".ast-chat-row").filter(has_text="почему упал test_login?").first
    )
    row.locator(".ast-chat-delete").click()
    row.locator(".ast-chat-confirm").click()
    # Not "no messages": having deleted the chat it was reading, the window moves on to
    # the next one, which has its own. What must be gone is *this* conversation.
    expect(
        first.locator(".ast-msg.user").filter(has_text="почему упал test_login?")
    ).to_have_count(0, timeout=10_000)

    # ...and the other tab, which was reading the same chat, must not still be showing it.
    expect(
        second.locator(".ast-msg.user").filter(has_text="почему упал test_login?")
    ).to_have_count(0, timeout=10_000)
    first.close()
    second.close()


@pytest.mark.ui
def test_deleting_one_chat_leaves_a_tab_reading_another_alone(live, context):
    """The other half of the cross-tab rule, and the way to get it wrong.

    A notice that says "a chat was deleted" must name which one. Clearing every tab that
    hears it would trade a stale transcript for a vanishing one, which is worse: the
    reader loses a conversation that still exists.
    """
    base, _ = live
    first = context.new_page()
    second = context.new_page()
    for page in (first, second):
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
        page.locator("#assistant-btn").click()
        expect(page.locator("#assistant-dialog")).to_be_visible()

    def fresh_chat(page, question):
        page.locator("#ast-chats").click()
        expect(page.locator("#ast-chats-dialog")).to_be_visible()
        page.locator("#ast-chat-new").click()
        expect(page.locator("#ast-chats-dialog")).to_be_hidden()
        page.locator("#ast-question").click()
        page.locator("#ast-question").fill(question)
        page.locator("#ast-send").click()
        expect(page.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
            "Offline assistant", timeout=30_000
        )
        expect(page.locator("#ast-stop")).to_be_hidden(timeout=30_000)

    fresh_chat(first, "вопрос из первой вкладки")
    fresh_chat(second, "вопрос из второй вкладки")

    row = first.locator(".ast-chat-row").filter(has_text="вопрос из первой вкладки")
    first.locator("#ast-chats").click()
    expect(first.locator("#ast-chats-dialog")).to_be_visible()
    row.first.locator(".ast-chat-delete").click()
    row.first.locator(".ast-chat-confirm").click()

    expect(
        first.locator(".ast-msg.user").filter(has_text="вопрос из первой вкладки")
    ).to_have_count(0, timeout=10_000)
    # The second tab was reading a different chat and keeps it.
    expect(
        second.locator(".ast-msg.user").filter(has_text="вопрос из второй вкладки")
    ).to_have_count(1, timeout=10_000)
    first.close()
    second.close()


@pytest.mark.ui
def test_clearing_a_chat_in_one_tab_clears_it_in_the_other(live, context):
    """Clear removes the server copy, so a tab still showing it is showing nothing real.

    Same rule as deleting, reached by the other button, and worth its own test because
    Clear keeps the chat id: the window that missed the notice would go on appending to
    a conversation whose earlier turns no longer exist.
    """
    base, _ = live
    first = context.new_page()
    second = context.new_page()
    for page in (first, second):
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
        page.locator("#assistant-btn").click()
        expect(page.locator("#assistant-dialog")).to_be_visible()

    first.locator("#ast-chats").click()
    expect(first.locator("#ast-chats-dialog")).to_be_visible()
    first.locator("#ast-chat-new").click()
    expect(first.locator("#ast-chats-dialog")).to_be_hidden()
    first.locator("#ast-question").click()
    first.locator("#ast-question").fill("вопрос для очистки")
    first.locator("#ast-send").click()
    expect(first.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=30_000
    )
    expect(first.locator("#ast-stop")).to_be_hidden(timeout=30_000)

    second.locator("#ast-chats").click()
    expect(second.locator("#ast-chats-dialog")).to_be_visible()
    second.locator(".ast-chat-item").filter(has_text="вопрос для очистки").first.click()
    expect(second.locator(".ast-msg.user").first).to_contain_text("вопрос для очистки")

    first.locator("#ast-clear").click()
    first.locator("#ast-clear-yes").click()

    expect(
        first.locator(".ast-msg.user").filter(has_text="вопрос для очистки")
    ).to_have_count(0, timeout=10_000)
    expect(
        second.locator(".ast-msg.user").filter(has_text="вопрос для очистки")
    ).to_have_count(0, timeout=10_000)
    first.close()
    second.close()


@pytest.mark.ui
def test_renaming_a_chat_reaches_a_list_open_in_another_tab(live, context):
    """The chat list is a shared list; two tabs showing it must not disagree about a name.

    Deleting and clearing tell the other tabs; renaming did not, so a window with the
    list open kept showing a title that had been changed, and the only way to find out
    was to reload.
    """
    base, _ = live
    first = context.new_page()
    second = context.new_page()
    for page in (first, second):
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_selector("#assistant-btn:not([hidden])", timeout=20_000)
        page.locator("#assistant-btn").click()

    first.locator("#ast-chats").click()
    expect(first.locator("#ast-chats-dialog")).to_be_visible()
    first.locator("#ast-chat-new").click()
    first.locator("#ast-question").click()
    first.locator("#ast-question").fill("чат под переименование")
    first.locator("#ast-send").click()
    expect(first.locator(".ast-msg.assistant .ast-answer").last).to_contain_text(
        "Offline assistant", timeout=30_000
    )
    expect(first.locator("#ast-stop")).to_be_hidden(timeout=30_000)

    # The second tab is looking at the list while the first renames.
    second.locator("#ast-chats").click()
    expect(second.locator("#ast-chats-dialog")).to_be_visible()
    expect(
        second.locator(".ast-chat-row").filter(has_text="чат под переименование")
    ).to_have_count(1)

    first.locator("#ast-chats").click()
    row = first.locator(".ast-chat-row").filter(has_text="чат под переименование").first
    row.locator(".ast-chat-rename").click()
    field = first.locator(".ast-chat-name-input")
    field.fill("новое имя чата")
    field.press("Enter")
    expect(
        first.locator(".ast-chat-row").filter(has_text="новое имя чата")
    ).to_have_count(1, timeout=10_000)

    expect(
        second.locator(".ast-chat-row").filter(has_text="новое имя чата")
    ).to_have_count(1, timeout=10_000)
    first.close()
    second.close()
