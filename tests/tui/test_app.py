import pytest
from textual.widgets import RichLog

from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall
from cire_harness.session import load_session
from cire_harness.tools import ToolRegistry
from cire_harness.tools.fs import fs_tools
from cire_harness.tui.app import ChatApp


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


def reply(text="", calls=()):
    return Response(message=Message(role="assistant", content=text, tool_calls=list(calls)))


def log_lines(app):
    return [str(line.text) for line in app.query_one(RichLog).lines]


async def test_message_round_trip_and_save():
    app = ChatApp(FakeProvider([reply("hi there")]), ToolRegistry([]), [], "t1")
    async with app.run_test() as pilot:
        await pilot.press(*"hello", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert log_lines(app) == ["you: hello", "hi there"]
    assert [m.role for m in load_session("t1")] == ["user", "assistant"]


async def test_tool_calls_and_results_are_shown(tmp_path):
    (tmp_path / "a.py").write_text("x\n")
    call = ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})
    provider = FakeProvider([reply(calls=[call]), reply("done")])
    app = ChatApp(provider, ToolRegistry(fs_tools(tmp_path)), [], "t2")
    async with app.run_test() as pilot:
        await pilot.press(*"read", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        lines = log_lines(app)
        assert "-> read_file {'path': 'a.py'}" in lines
        assert "<- x" in lines
        assert lines[-1] == "done"
