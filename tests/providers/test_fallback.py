from cire_harness.providers.base import complete
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.fallback import PromptToolProvider, extract_calls, flatten
from cire_harness.providers.types import Message, Response, ToolCall, ToolSpec

TOOLS = [ToolSpec(name="read", description="read a file")]


def reply(text: str) -> Response:
    return Response(message=Message(role="assistant", content=text))


def test_extract_calls_parses_blocks_and_strips_them():
    text = 'Let me look.\n```tool\n{"name": "read", "arguments": {"path": "a"}}\n```\n'
    clean, calls = extract_calls(text)
    assert clean == "Let me look."
    assert len(calls) == 1
    assert calls[0].name == "read"
    assert calls[0].arguments == {"path": "a"}


def test_extract_calls_ignores_broken_json():
    clean, calls = extract_calls("```tool\n{not json\n```")
    assert calls == []
    assert clean == ""


def test_flatten_renders_tools_and_history_as_text():
    messages = [
        Message(role="user", content="read a"),
        Message(
            role="assistant", tool_calls=[ToolCall(id="1", name="read", arguments={"path": "a"})]
        ),
        Message(role="tool", content="body", tool_call_id="1"),
    ]
    flat = flatten(messages, TOOLS)
    assert flat[0].role == "system"
    assert "read: read a file" in flat[0].content
    assert flat[2].role == "assistant"
    assert '"name": "read"' in flat[2].content
    assert flat[3] == Message(role="user", content="Tool result:\nbody")


async def test_wrapped_provider_returns_tool_calls():
    inner = FakeProvider([reply('```tool\n{"name": "read", "arguments": {"path": "a"}}\n```')])
    provider = PromptToolProvider(inner)
    response = await complete(provider, [Message(role="user", content="read a")], TOOLS)
    assert response.stop_reason == "tool_use"
    assert response.message.content == ""
    assert response.message.tool_calls[0].arguments == {"path": "a"}
    sent_messages, sent_tools = inner.calls[0]
    assert sent_tools == []
    assert sent_messages[0].role == "system"


async def test_wrapped_provider_passes_plain_text_through():
    provider = PromptToolProvider(FakeProvider([reply("just text")]))
    response = await complete(provider, [Message(role="user", content="hi")])
    assert response.stop_reason == "end"
    assert response.message.content == "just text"
    assert response.message.tool_calls == []
