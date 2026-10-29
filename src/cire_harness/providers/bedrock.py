import re
from collections.abc import AsyncIterator, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from cire_harness.providers.base import ProviderError
from cire_harness.providers.types import (
    Message,
    Response,
    StopReason,
    StreamEvent,
    ToolCall,
    ToolSpec,
    Usage,
)

KEY_VAR = "AWS_BEARER_TOKEN_BEDROCK"
REGION_VARS = ("AWS_REGION", "AWS_DEFAULT_REGION")
REGION_RE = re.compile(r"^[a-z]{2}(-gov|-iso[a-z]?)?-[a-z]+-\d$")
STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end",
    "stop_sequence": "end",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
}


def to_converse_messages(
    messages: Sequence[Message],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    system: list[dict[str, Any]] = []
    wire: list[dict[str, Any]] = []

    def add(role: str, blocks: list[dict[str, Any]]) -> None:
        if wire and wire[-1]["role"] == role:
            wire[-1]["content"].extend(blocks)
        else:
            wire.append({"role": role, "content": blocks})

    for message in messages:
        if message.role == "system":
            if message.content.strip():
                system.append({"text": message.content})
        elif message.role == "tool":
            result = {
                "toolUseId": message.tool_call_id,
                "content": [{"text": message.content or "(empty)"}],
                "status": "error" if message.content.startswith("error:") else "success",
            }
            add("user", [{"toolResult": result}])
        else:
            blocks: list[dict[str, Any]] = []
            if message.content.strip():
                blocks.append({"text": message.content})
            for call in message.tool_calls:
                blocks.append(
                    {"toolUse": {"toolUseId": call.id, "name": call.name, "input": call.arguments}}
                )
            if blocks:
                add(message.role, blocks)
    return system, wire


def to_converse_tool(tool: ToolSpec) -> dict[str, Any]:
    spec: dict[str, Any] = {"name": tool.name, "inputSchema": {"json": tool.parameters}}
    if tool.description:
        spec["description"] = tool.description
    return {"toolSpec": spec}


class BedrockProvider:
    name = "bedrock"

    def __init__(
        self,
        model: str,
        api_key: str,
        region: str,
        max_tokens: int = 16000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError(f"{KEY_VAR} is not set; create a Bedrock API key and export it")
        if not REGION_RE.match(region):
            raise ProviderError(f"invalid AWS region {region!r}; set {REGION_VARS[0]}")
        self.model = model
        self.api_key = api_key
        self.base_url = f"https://bedrock-runtime.{region}.amazonaws.com"
        self.max_tokens = max_tokens
        self.client = client or httpx.AsyncClient(timeout=120)

    def __repr__(self) -> str:
        return f"BedrockProvider(model={self.model!r})"

    def build_request(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> httpx.Request:
        system, wire_messages = to_converse_messages(messages)
        body: dict[str, Any] = {
            "messages": wire_messages,
            "inferenceConfig": {"maxTokens": self.max_tokens},
        }
        if system:
            body["system"] = system
        if tools:
            body["toolConfig"] = {"tools": [to_converse_tool(t) for t in tools]}
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url}/model/{quote(self.model, safe='')}/converse"
        return self.client.build_request("POST", url, json=body, headers=headers)

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamEvent]:
        try:
            response = await self.client.send(self.build_request(messages, tools))
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc)) from exc
        if response.status_code >= 400:
            raise ProviderError(
                f"HTTP {response.status_code}", response.status_code, response.text[:2000]
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("bedrock returned a non-JSON body") from exc
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        content = ((data.get("output") or {}).get("message") or {}).get("content") or []
        for block in content:
            if "text" in block:
                text_parts.append(block["text"])
                yield StreamEvent(type="text", text=block["text"])
            elif "toolUse" in block:
                use = block["toolUse"]
                call = ToolCall(
                    id=use["toolUseId"], name=use["name"], arguments=use.get("input") or {}
                )
                tool_calls.append(call)
                yield StreamEvent(type="tool_call", tool_call=call)
        raw_usage = data.get("usage") or {}
        usage = Usage(
            input_tokens=raw_usage.get("inputTokens", 0),
            output_tokens=raw_usage.get("outputTokens", 0),
            cached_tokens=raw_usage.get("cacheReadInputTokens", 0),
        )
        stop_reason: StopReason = STOP_REASONS.get(data.get("stopReason") or "", "end")
        if tool_calls:
            stop_reason = "tool_use"
        message = Message(role="assistant", content="".join(text_parts), tool_calls=tool_calls)
        yield StreamEvent(
            type="done", response=Response(message=message, usage=usage, stop_reason=stop_reason)
        )
