import pytest

from cire_harness.providers.base import ProviderError, complete
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall


def reply(text: str, tool_calls=()) -> Response:
    return Response(message=Message(role="assistant", content=text, tool_calls=list(tool_calls)))


async def test_streams_text_then_tool_calls_then_done():
    call = ToolCall(id="1", name="read", arguments={"path": "a.py"})
    provider = FakeProvider([reply("hello world", [call])])
    events = [e async for e in provider.stream([Message(role="user", content="hi")])]
    assert [e.type for e in events] == ["text", "text", "tool_call", "done"]
    assert "".join(e.text for e in events).strip() == "hello world"
    assert events[2].tool_call == call


async def test_records_calls_and_returns_in_order():
    provider = FakeProvider([reply("first"), reply("second")])
    assert (
        await complete(provider, [Message(role="user", content="a")])
    ).message.content == "first"
    assert (
        await complete(provider, [Message(role="user", content="b")])
    ).message.content == "second"
    assert [m[0][0].content for m in provider.calls] == ["a", "b"]


async def test_raises_when_exhausted():
    provider = FakeProvider([])
    with pytest.raises(ProviderError):
        await complete(provider, [])
