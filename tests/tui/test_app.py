import pytest
from textual.widgets import RichLog

from cire_harness.context.store import ContextStore
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall
from cire_harness.tools import ToolRegistry
from cire_harness.tools.fs import fs_tools
from cire_harness.tui.app import ChatApp


@pytest.fixture
def store(tmp_path):
    return ContextStore(tmp_path / "cire.db")


def reply(text="", calls=()):
    return Response(message=Message(role="assistant", content=text, tool_calls=list(calls)))


def log_lines(app):
    return [str(line.text) for line in app.query_one(RichLog).lines]


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


def make_app(store, messages=()):
    return ChatApp(FakeProvider([]), ToolRegistry([]), list(messages), "t3", store)


def test_stats_shows_usage(store):
    assert make_app(store).handle_command("/stats") == "input=0 output=0 cached=0"


def test_model_get_and_set(store):
    app = make_app(store)
    assert app.handle_command("/model") == "fake-model"
    assert app.handle_command("/model nonsense").startswith("error:")
    assert app.handle_command("/model ollama:llama3.1") == "model: llama3.1"


def test_compact_keeps_last_ten(store):
    app = make_app(store, (Message(role="user", content=str(i)) for i in range(15)))
    assert app.handle_command("/compact") == "kept 10 messages"
    assert app.messages[0].content == "5"


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
        assert log_lines(app) == ["input=0 output=0 cached=0"]
    assert app.messages == []
