from cire_harness.loop.loop import run_agent
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall, ToolSpec
from cire_harness.tools import Tool, ToolRegistry
from cire_harness.tools.fs import fs_tools


async def allow(call):
    return True


async def deny(call):
    return False


def reply(text="", calls=()):
    return Response(message=Message(role="assistant", content=text, tool_calls=list(calls)))


def ask(text="hi"):
    return [Message(role="user", content=text)]


async def test_plain_answer_returns_text(tmp_path):
    provider = FakeProvider([reply("hello")])
    result = await run_agent(provider, ToolRegistry([]), ask(), allow)
    assert result == "hello"
    assert len(provider.calls) == 1


async def test_tool_result_is_fed_back(tmp_path):
    (tmp_path / "a.py").write_text("print(1)\n")
    call = ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})
    provider = FakeProvider([reply(calls=[call]), reply("done")])
    messages = ask()
    result = await run_agent(provider, ToolRegistry(fs_tools(tmp_path)), messages, allow)
    assert result == "done"
    tool_msg = provider.calls[1][0][-1]
    assert tool_msg.role == "tool"
    assert tool_msg.tool_call_id == "c1"
    assert tool_msg.content == "print(1)\n"
    assert [m.role for m in messages] == ["user", "assistant", "tool", "assistant"]


async def test_unknown_tool_is_reported_not_raised():
    call = ToolCall(id="c1", name="nope")
    provider = FakeProvider([reply(calls=[call]), reply("ok")])
    assert await run_agent(provider, ToolRegistry([]), ask(), allow) == "ok"
    assert provider.calls[1][0][-1].content == "error: unknown tool nope"


async def test_risky_tool_needs_approval():
    ran = []

    async def run(args):
        ran.append(args)
        return "ran"

    tool = Tool(ToolSpec(name="danger", description="x"), run, risky=True)
    call = ToolCall(id="c1", name="danger")
    provider = FakeProvider([reply(calls=[call]), reply("ok")])
    await run_agent(provider, ToolRegistry([tool]), ask(), deny)
    assert ran == []
    assert provider.calls[1][0][-1].content == "error: permission denied"

    provider = FakeProvider([reply(calls=[call]), reply("ok")])
    await run_agent(provider, ToolRegistry([tool]), ask(), allow)
    assert ran == [{}]


async def test_max_turns_stops_the_loop():
    call = ToolCall(id="c1", name="nope")
    provider = FakeProvider([reply(calls=[call])] * 3)
    result = await run_agent(provider, ToolRegistry([]), ask(), allow, max_turns=3)
    assert result == "stopped after 3 turns"
    assert len(provider.calls) == 3
