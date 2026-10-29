import asyncio
import sys
from pathlib import Path

import pytest
from textual.widgets import RichLog, Static

from cire_harness.config import MCPServer
from cire_harness.context.store import ContextStore
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, StreamEvent, ToolCall, Usage
from cire_harness.tools import ToolRegistry
from cire_harness.tools.fs import fs_tools
from cire_harness.tui.app import ChatApp


@pytest.fixture
def store(tmp_path):
    return ContextStore(tmp_path / "cire.db")


def reply(text="", calls=()):
    return Response(message=Message(role="assistant", content=text, tool_calls=list(calls)))


def log_lines(app):
    lines = [str(line.text).rstrip() for line in app.query_one(RichLog).lines]
    return [line for line in lines if line]


async def test_message_round_trip_and_save(store):
    app = ChatApp(FakeProvider([reply("hi there")]), ToolRegistry([]), [], "t1", store)
    async with app.run_test() as pilot:
        await pilot.press(*"hello", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert log_lines(app) == ["you: hello", "hi there"]
    assert [m.role for m in store.load_messages("t1")] == ["user", "assistant"]


async def test_tool_calls_and_results_are_shown(tmp_path, store):
    (tmp_path / "a.py").write_text("x\n")
    call = ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})
    provider = FakeProvider([reply(calls=[call]), reply("done")])
    app = ChatApp(provider, ToolRegistry(fs_tools(tmp_path)), [], "t2", store)
    async with app.run_test() as pilot:
        await pilot.press(*"read", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        lines = log_lines(app)
        assert "-> read_file {'path': 'a.py'}" in lines
        assert "<- x" in lines
        assert lines[-1] == "done"


async def test_large_tool_result_is_masked_and_stored(tmp_path, store):
    (tmp_path / "big.txt").write_text("word " * 2000)
    call = ToolCall(id="c1", name="read_file", arguments={"path": "big.txt"})
    provider = FakeProvider([reply(calls=[call]), reply("done")])
    app = ChatApp(provider, ToolRegistry(fs_tools(tmp_path)), [], "t4", store)
    async with app.run_test() as pilot:
        await pilot.press(*"read", "enter")
        await app.workers.wait_for_complete()
    tool_msg = next(m for m in app.messages if m.role == "tool")
    assert "[stored result id=1" in tool_msg.content
    assert len(tool_msg.content) < 600
    assert store.load_tool_result(1) == "word " * 2000


async def test_over_budget_triggers_compaction(store):
    history = [Message(role="user", content="fact " * 80) for _ in range(20)]
    provider = FakeProvider([reply("answer"), reply("the summary")])
    app = ChatApp(provider, ToolRegistry([]), history, "t5", store, budget=500)
    async with app.run_test() as pilot:
        await pilot.press(*"more", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert log_lines(app)[-1].startswith("compacted: ~")
    assert app.messages[0].role == "system"
    assert "the summary" in app.messages[0].content
    assert len(app.messages) < 10
    assert store.load_messages("t5") == app.messages
    assert store.search("t5", "fact")


def make_app(store, messages=()):
    return ChatApp(FakeProvider([]), ToolRegistry([]), list(messages), "t3", store)


def test_stats_shows_usage(store):
    assert make_app(store).handle_command("/stats") == "input=0 output=0 cached=0 context~0/8000"


def test_model_get_and_set(store):
    app = make_app(store)
    assert app.handle_command("/model") == "fake-model"
    assert app.handle_command("/model nonsense").startswith("error:")
    assert app.handle_command("/model ollama:llama3.1") == "model: llama3.1"


def test_sessions_lists_store(store):
    store.save_messages("a", [])
    assert make_app(store).handle_command("/sessions") == "a"


def test_unknown_command(store):
    assert make_app(store).handle_command("/nope").startswith("unknown command")


async def test_command_does_not_reach_agent(store):
    app = make_app(store)
    async with app.run_test() as pilot:
        await pilot.press(*"/stats", "enter")
        await pilot.pause()
        assert log_lines(app) == ["input=0 output=0 cached=0 context~0/8000"]
    assert app.messages == []


class SlowProvider(FakeProvider):
    async def stream(self, messages, tools=()):
        await asyncio.sleep(5)
        async for event in super().stream(messages, tools):
            yield event


def status(app):
    return str(app.query_one("#status", Static).content)


async def test_status_shows_activity_and_escape_stops(store):
    app = ChatApp(SlowProvider([reply("late")]), ToolRegistry([]), [], "t6", store)
    async with app.run_test() as pilot:
        await pilot.press(*"hi", "enter")
        await pilot.pause(0.3)
        assert "thinking" in status(app)
        await pilot.press("escape")
        await app.workers.wait_for_complete()
        await pilot.pause(0.3)
        assert log_lines(app) == ["you: hi", "stopped"]
        assert status(app) == ""
    assert [m.role for m in app.messages] == ["user"]
    assert store.load_messages("t6") == app.messages


async def test_streamed_text_appears_in_status(store):
    class Streamer(FakeProvider):
        async def stream(self, messages, tools=()):
            yield StreamEvent(type="text", text="partial words")
            await asyncio.sleep(5)
            yield StreamEvent(type="done", response=reply("final"))

    app = ChatApp(Streamer([]), ToolRegistry([]), [], "t7", store)
    async with app.run_test() as pilot:
        await pilot.press(*"go", "enter")
        await pilot.pause(0.3)
        assert "partial words" in status(app)
        app.action_stop()
        await app.workers.wait_for_complete()


async def test_provider_error_is_logged_not_fatal(store):
    app = ChatApp(FakeProvider([]), ToolRegistry([]), [], "t8", store)
    async with app.run_test() as pilot:
        await pilot.press(*"x", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert log_lines(app)[-1].startswith("error: fake provider has no responses")


async def test_mcp_tools_join_registry_and_close_on_exit(store):
    call = ToolCall(id="c1", name="echo_echo", arguments={"text": "hi", "times": 2})
    provider = FakeProvider([reply(calls=[call]), reply("done")])
    echo_server = str(Path(__file__).parent.parent / "mcp_client" / "echo_server.py")
    servers = {
        "echo": MCPServer(command=sys.executable, args=[echo_server], trusted=True),
        "bad": MCPServer(command="no-such-cmd-xyz"),
    }
    app = ChatApp(provider, ToolRegistry([]), [], "t9", store, mcp_servers=servers)
    async with app.run_test() as pilot:
        await pilot.press(*"/tools", "enter")
        await pilot.press(*"go", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        lines = log_lines(app)
        assert "<- hihi" in lines
        assert lines[-1] == "done"
        assert any(line.startswith("mcp bad:") for line in lines)
        assert app.handle_command("/tools") == "echo_echo\necho_secret\necho_fail"
    assert app.mcp.closed


async def test_delegate_runs_executor_with_confirmation(tmp_path, store):
    from functools import partial

    from cire_harness.orchestration.delegate import delegate_tool
    from cire_harness.tui.app import ConfirmScreen

    call = ToolCall(id="d", name="delegate", arguments={"goal": "write", "acceptance": ["true"]})
    planner = FakeProvider([reply(calls=[call]), reply("planner done")])
    write = ToolCall(id="w", name="write_file", arguments={"path": "x.txt", "content": "1"})
    executor = FakeProvider(
        [
            Response(
                message=Message(role="assistant", tool_calls=[write]), usage=Usage(input_tokens=7)
            ),
            reply("executor done"),
        ]
    )
    app = ChatApp(
        planner,
        ToolRegistry([]),
        [],
        "t10",
        store,
        delegate=partial(delegate_tool, executor, tmp_path),
    )
    async with app.run_test() as pilot:
        assert "delegate" in app.handle_command("/tools")
        await pilot.press(*"go", "enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.click("#yes")
        await app.workers.wait_for_complete()
        await pilot.pause()
        lines = log_lines(app)
        assert "[exec] -> write_file {'path': 'x.txt', 'content': '1'}" in lines
        assert "[exec] executor done" in lines
        assert lines[-1] == "planner done"
        assert app.handle_command("/stats").endswith("executor: input=7 output=0 cached=0")
    assert (tmp_path / "x.txt").read_text() == "1"


async def test_log_selection_and_copy_command(store, monkeypatch):
    from textual.geometry import Offset
    from textual.selection import Selection

    from cire_harness.tui.app import Log

    history = [
        Message(role="user", content="first"),
        Message(role="assistant", content="second line"),
    ]
    app = make_app(store, history)
    copied = []
    monkeypatch.setattr(app, "copy_to_clipboard", copied.append)
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one(Log)
        text, end = log.get_selection(Selection(Offset(0, 0), Offset(6, 1)))
        assert text == "you: first\nsecond" and end == "\n"
        assert app.handle_command("/copy") == "copied 11 chars"
    assert copied == ["second line"]
    assert make_app(store).handle_command("/copy") == "nothing to copy"


async def test_slash_hint_and_help(store):
    app = make_app(store)
    async with app.run_test() as pilot:
        hint = app.query_one("#hint", Static)
        assert not hint.display
        await pilot.press("/", "m")
        await pilot.pause()
        assert hint.display and "/model" in str(hint.content) and "/stats" not in str(hint.content)
        await pilot.press(" ")
        await pilot.pause()
        assert not hint.display
        await pilot.press("backspace", "backspace", "backspace", "enter")
        await pilot.pause()
        assert log_lines(app) == []
    assert app.handle_command("/help").startswith("/model")
    assert app.handle_command("/nope").endswith("type /help")
