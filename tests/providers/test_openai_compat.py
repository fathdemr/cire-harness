import json

import httpx
import pytest

from cire_harness.providers.base import ProviderError, complete
from cire_harness.providers.openai_compat import OpenAICompatProvider
from cire_harness.providers.types import Message, ToolCall, ToolSpec


def sse(*chunks: dict) -> str:
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def make_provider(body: str, status: int = 200, captured: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(json.loads(request.content))
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatProvider("gpt-test", base_url="http://x/v1", api_key="k", client=client)


async def test_text_stream_and_usage():
    body = sse(
        {"choices": [{"delta": {"content": "Mer"}}]},
        {"choices": [{"delta": {"content": "haba"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
    )
    provider = make_provider(body)
    events = [e async for e in provider.stream([Message(role="user", content="hi")])]
    assert [e.type for e in events] == ["text", "text", "done"]
    response = events[-1].response
    assert response.message.content == "Merhaba"
    assert response.stop_reason == "end"
    assert response.usage.input_tokens == 5
    assert response.usage.output_tokens == 2


async def test_tool_call_chunks_are_assembled():
    body = sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "c1", "function": {"name": "read", "arguments": ""}}
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"pa'}}]}}]},
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'th": "a"}'}}]}}
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    )
    response = await complete(make_provider(body), [Message(role="user", content="go")])
    assert response.stop_reason == "tool_use"
    assert response.message.tool_calls == [ToolCall(id="c1", name="read", arguments={"path": "a"})]


async def test_request_body_conversion():
    captured: list = []
    provider = make_provider(
        sse({"choices": [{"delta": {}, "finish_reason": "stop"}]}), captured=captured
    )
    messages = [
        Message(role="system", content="be brief"),
        Message(role="user", content="read a"),
        Message(
            role="assistant",
            tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "a"})],
        ),
        Message(role="tool", content="file body", tool_call_id="c1"),
    ]
    tools = [ToolSpec(name="read", description="read a file")]
    await complete(provider, messages, tools)
    body = captured[0]
    assert body["model"] == "gpt-test"
    assert body["stream"] is True
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"path": "a"}'
    assert body["messages"][3] == {"role": "tool", "content": "file body", "tool_call_id": "c1"}
    assert body["tools"][0]["function"]["name"] == "read"


async def test_http_error_raises_provider_error():
    provider = make_provider('{"error": "bad key"}', status=401)
    with pytest.raises(ProviderError) as info:
        await complete(provider, [Message(role="user", content="hi")])
    assert info.value.status == 401
    assert "bad key" in info.value.body
