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

STOP_REASONS: dict[str, StopReason] = {
    "stop": "end",
    "tool_calls": "tool_use",
    "length": "max_tokens",
}


def to_wire_message(message: Message) -> dict[str, Any]:
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.role == "tool":
        wire["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return wire


def to_wire_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def parse_usage(raw: dict[str, Any] | None) -> Usage:
    if not raw:
        return Usage()
    details = raw.get("prompt_tokens_details") or {}
    return Usage(
        input_tokens=raw.get("prompt_tokens", 0),
        output_tokens=raw.get("completion_tokens", 0),
        cached_tokens=details.get("cached_tokens", 0),
    )


class OpenAICompatProvider:
    name = "openai"

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=120)

    def build_request(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> httpx.Request:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [to_wire_message(m) for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            body["tools"] = [to_wire_tool(t) for t in tools]
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        return self.client.build_request(
            "POST", f"{self.base_url}/chat/completions", json=body, headers=headers
        )

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamEvent]:
        text_parts: list[str] = []
        pending: dict[int, dict[str, str]] = {}
        stop_reason: StopReason = "end"
        usage = Usage()
        async for chunk in read_json_events(self.client, self.build_request(messages, tools)):
            if chunk.get("usage"):
                usage = parse_usage(chunk["usage"])
            for choice in chunk.get("choices", []):
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    text_parts.append(delta["content"])
                    yield StreamEvent(type="text", text=delta["content"])
                for part in delta.get("tool_calls") or []:
                    slot = pending.setdefault(part["index"], {"id": "", "name": "", "args": ""})
                    slot["id"] = part.get("id") or slot["id"]
                    fn = part.get("function") or {}
                    slot["name"] = fn.get("name") or slot["name"]
                    slot["args"] += fn.get("arguments") or ""
                if choice.get("finish_reason"):
                    stop_reason = STOP_REASONS.get(choice["finish_reason"], "end")
        tool_calls = [
            ToolCall(id=slot["id"], name=slot["name"], arguments=json.loads(slot["args"] or "{}"))
            for _, slot in sorted(pending.items())
        ]
        for call in tool_calls:
            yield StreamEvent(type="tool_call", tool_call=call)
        if tool_calls:
            stop_reason = "tool_use"
        message = Message(role="assistant", content="".join(text_parts), tool_calls=tool_calls)
        yield StreamEvent(
            type="done", response=Response(message=message, usage=usage, stop_reason=stop_reason)
        )
