import json

import httpx
import pytest

from cire_harness.providers import get_provider
from cire_harness.providers.base import ProviderError, complete
from cire_harness.providers.bedrock import BedrockProvider, to_converse_messages
from cire_harness.providers.types import Message, ToolCall, ToolSpec

MODEL = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"


def make_provider(body: dict | str, status: int = 200, captured: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append((str(request.url), dict(request.headers), json.loads(request.content)))
        text = body if isinstance(body, str) else json.dumps(body)
        return httpx.Response(status, text=text, headers={"content-type": "application/json"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return BedrockProvider(MODEL, api_key="secret-key", region="eu-central-1", client=client)


def answer(*content, stop="end_turn"):
    return {
        "output": {"message": {"role": "assistant", "content": list(content)}},
        "stopReason": stop,
        "usage": {"inputTokens": 11, "outputTokens": 4, "cacheReadInputTokens": 2},
    }


async def test_request_uses_converse_with_bearer_token():
    captured: list = []
    provider = make_provider(answer({"text": "hi"}), captured=captured)
    await complete(
        provider,
        [Message(role="system", content="be brief"), Message(role="user", content="hey")],
        [ToolSpec(name="read", description="r"), ToolSpec(name="bare", description="")],
    )
    url, headers, body = captured[0]
    assert url == (
        "https://bedrock-runtime.eu-central-1.amazonaws.com/model/"
        "eu.anthropic.claude-sonnet-4-5-20250929-v1%3A0/converse"
    )
    assert headers["authorization"] == "Bearer secret-key"
    assert "x-api-key" not in headers
    assert body["system"] == [{"text": "be brief"}]
    assert body["inferenceConfig"] == {"maxTokens": 16000}
    assert body["messages"] == [{"role": "user", "content": [{"text": "hey"}]}]
    tools = body["toolConfig"]["tools"]
    assert tools[0]["toolSpec"]["inputSchema"]["json"]["type"] == "object"
    assert "description" not in tools[1]["toolSpec"]
    assert "anthropic_version" not in body and "model" not in body


def test_message_conversion_merges_roles_and_tool_results():
    call = ToolCall(id="t1", name="read", arguments={"path": "a"})
    system, wire = to_converse_messages(
        [
            Message(role="system", content="s"),
            Message(role="user", content="one"),
            Message(role="user", content="two"),
            Message(role="assistant", content="", tool_calls=[call]),
            Message(role="tool", content="data", tool_call_id="t1"),
            Message(role="tool", content="error: nope", tool_call_id="t2"),
        ]
    )
    assert system == [{"text": "s"}]
    assert wire[0] == {"role": "user", "content": [{"text": "one"}, {"text": "two"}]}
    assert wire[1] == {
        "role": "assistant",
        "content": [{"toolUse": {"toolUseId": "t1", "name": "read", "input": {"path": "a"}}}],
    }
    results = [b["toolResult"] for b in wire[2]["content"]]
    assert results[0] == {"toolUseId": "t1", "content": [{"text": "data"}], "status": "success"}
    assert results[1]["status"] == "error"


async def test_text_tool_use_and_unknown_blocks_are_parsed():
    provider = make_provider(
        answer(
            {"reasoningContent": {"reasoningText": {"text": "hmm"}}},
            {"text": "Let me look. "},
            {"toolUse": {"toolUseId": "t1", "name": "read", "input": {"path": "a"}}},
            stop="tool_use",
        )
    )
    events = [e async for e in provider.stream([Message(role="user", content="x")])]
    assert [e.type for e in events] == ["text", "tool_call", "done"]
    response = events[-1].response
    assert response.message.content == "Let me look. "
    assert response.message.tool_calls[0].arguments == {"path": "a"}
    assert response.stop_reason == "tool_use"
    assert (response.usage.input_tokens, response.usage.cached_tokens) == (11, 2)


async def test_http_error_keeps_key_out_of_message():
    with pytest.raises(ProviderError) as info:
        await complete(make_provider('{"message":"denied"}', status=403), [Message(role="user")])
    assert info.value.status == 403
    assert "secret-key" not in str(info.value) + info.value.body + repr(make_provider({}))


def test_missing_key_or_bad_region_fail_fast():
    with pytest.raises(ProviderError, match="AWS_BEARER_TOKEN_BEDROCK"):
        BedrockProvider(MODEL, api_key="", region="eu-central-1")
    for region in ("", "evil.com/#", "eu-central-1.attacker.net", "EU-CENTRAL-1"):
        with pytest.raises(ProviderError, match="invalid AWS region"):
            BedrockProvider(MODEL, api_key="k", region=region)


def test_factory_reads_env_only(monkeypatch):
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(ProviderError, match="AWS_BEARER_TOKEN_BEDROCK"):
        get_provider(f"bedrock:{MODEL}")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "k")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    provider = get_provider("bedrock:openai.gpt-oss-120b-1:0")
    assert isinstance(provider, BedrockProvider)
    assert provider.model == "openai.gpt-oss-120b-1:0"
    assert provider.base_url == "https://bedrock-runtime.us-east-1.amazonaws.com"
