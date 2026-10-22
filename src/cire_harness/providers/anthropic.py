import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from cire_harness.providers.sse import read_json_events
from cire_harness.providers.types import (
    Message,
    Response,
    StopReason,
    StreamEvent,
    ToolCall,
    ToolSpec,
    Usage,
)

API_VERSION = "2026-10-21"
STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end",
    "stop_sequence": "end",
    "refusal": "end",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
}


def to_wire_messages(messages: Sequence[Message]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    wire: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            system_parts.append(message.content)
            continue
        if message.role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            if wire and wire[-1]["role"] == "user" and isinstance(wire[-1]["content"], list):
                wire[-1]["content"].append(block)
            else:
                wire.append({"role": "user", "content": [block]})
            continue
        content: list[dict[str, Any]] = []
        if message.content:
            content.append({"type": "text", "text": message.content})
        for call in message.tool_calls:
            content.append(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
            )
        wire.append({"role": message.role, "content": content})
    return "\n\n".join(system_parts), wire


def to_wire_tool(tool: ToolSpec) -> dict[str, Any]:
    return {"name": tool.name, "description": tool.description, "input_schema": tool.parameters}


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 16000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.client = client or httpx.AsyncClient(timeout=120)

    def build_request(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> httpx.Request:
        system, wire_messages = to_wire_messages(messages)
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": wire_messages,
            "stream": True,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [to_wire_tool(t) for t in tools]
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
        }
        return self.client.build_request(
            "POST", f"{self.base_url}/v1/messages", json=body, headers=headers
        )

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamEvent]:
        text_parts: list[str] = []
        blocks: dict[int, dict[str, Any]] = {}
        tool_calls: list[ToolCall] = []
        stop_reason: StopReason = "end"
        usage = Usage()
        async for event in read_json_events(self.client, self.build_request(messages, tools)):
            kind = event.get("type")
            if kind == "message_start":
                raw = event["message"].get("usage") or {}
                usage = Usage(
                    input_tokens=raw.get("input_tokens", 0),
                    output_tokens=raw.get("output_tokens", 0),
                    cached_tokens=raw.get("cache_read_input_tokens", 0),
                )
            elif kind == "content_block_start":
                block = dict(event["content_block"])
                block["partial_json"] = ""
                blocks[event["index"]] = block
            elif kind == "content_block_delta":
                delta = event["delta"]
                if delta.get("type") == "text_delta":
                    text_parts.append(delta["text"])
                    yield StreamEvent(type="text", text=delta["text"])
                elif delta.get("type") == "input_json_delta":
                    blocks[event["index"]]["partial_json"] += delta["partial_json"]
            elif kind == "content_block_stop":
                block = blocks.pop(event["index"])
                if block.get("type") == "tool_use":
                    call = ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=json.loads(block["partial_json"] or "{}"),
                    )
                    tool_calls.append(call)
                    yield StreamEvent(type="tool_call", tool_call=call)
            elif kind == "message_delta":
                raw_stop = (event.get("delta") or {}).get("stop_reason")
                if raw_stop:
                    stop_reason = STOP_REASONS.get(raw_stop, "end")
                raw_usage = event.get("usage") or {}
                if "output_tokens" in raw_usage:
                    usage.output_tokens = raw_usage["output_tokens"]
        if tool_calls:
            stop_reason = "tool_use"
        message = Message(role="assistant", content="".join(text_parts), tool_calls=tool_calls)
        yield StreamEvent(
            type="done", response=Response(message=message, usage=usage, stop_reason=stop_reason)
        )
