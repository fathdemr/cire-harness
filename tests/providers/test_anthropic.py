import json

import httpx
import pytest

from cire_harness.providers.anthropic import AnthropicProvider, to_wire_messages
from cire_harness.providers.base import ProviderError, complete
from cire_harness.providers.types import Message, ToolCall, ToolSpec


def sse(*events: dict) -> str:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def make_provider(body: str, status: int = 200, captured: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append((dict(request.headers), json.loads(request.content)))
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AnthropicProvider("claude-test", api_key="k", client=client)


def start(input_tokens: int = 0, cached: int = 0) -> dict:
    return {
        "type": "message_start",
        "message": {"usage": {"input_tokens": input_tokens, "cache_read_input_tokens": cached}},
    }


async def test_text_stream_and_usage():
    body = sse(
        start(input_tokens=7, cached=3),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Mer"}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "haba"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 2},
        },
        {"type": "message_stop"},
    )
    events = [e async for e in make_provider(body).stream([Message(role="user", content="hi")])]
    assert [e.type for e in events] == ["text", "text", "done"]
    response = events[-1].response
    assert response.message.content == "Merhaba"
    assert response.stop_reason == "end"
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 2
    assert response.usage.cached_tokens == 3


async def test_tool_use_block_is_assembled():
    body = sse(
        start(),
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "t1", "name": "read", "input": {}},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"pa'},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": 'th": "a"}'},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 9},
        },
    )
    events = [e async for e in make_provider(body).stream([Message(role="user", content="go")])]
    assert events[0].type == "tool_call"
    response = events[-1].response
    assert response.stop_reason == "tool_use"
    assert response.message.tool_calls == [ToolCall(id="t1", name="read", arguments={"path": "a"})]


def test_message_conversion():
    system, wire = to_wire_messages(
        [
            Message(role="system", content="be brief"),
            Message(role="user", content="read a and b"),
            Message(
                role="assistant",
                content="ok",
                tool_calls=[
                    ToolCall(id="t1", name="read", arguments={"path": "a"}),
                    ToolCall(id="t2", name="read", arguments={"path": "b"}),
                ],
            ),
            Message(role="tool", content="A", tool_call_id="t1"),
            Message(role="tool", content="B", tool_call_id="t2"),
        ]
    )
    assert system == "be brief"
    assert [m["role"] for m in wire] == ["user", "assistant", "user"]
    assert [b["type"] for b in wire[1]["content"]] == ["text", "tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in wire[2]["content"]] == ["t1", "t2"]


async def test_request_headers_and_body():
    captured: list = []
    provider = make_provider(sse(start(), {"type": "message_stop"}), captured=captured)
    await complete(
        provider, [Message(role="user", content="hi")], [ToolSpec(name="read", description="r")]
    )
    headers, body = captured[0]
    assert headers["x-api-key"] == "k"
    assert headers["anthropic-version"] == "2026-10-21"
    assert body["max_tokens"] == 16000
    assert body["tools"][0]["input_schema"]["type"] == "object"
    assert "system" not in body


async def test_http_error_raises_provider_error():
    with pytest.raises(ProviderError) as info:
        await complete(
            make_provider('{"error": "nope"}', status=400), [Message(role="user", content="hi")]
        )
    assert info.value.status == 400
