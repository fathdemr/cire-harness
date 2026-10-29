import re
from collections.abc import AsyncIterator, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from cire_harness.providers.anthropic import STOP_REASONS, to_wire_messages, to_wire_tool
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
ANTHROPIC_VERSION = "bedrock-2023-05-31"
REGION_RE = re.compile(r"^[a-z]{2}(-gov|-iso[a-z]?)?-[a-z]+-\d$")


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
        system, wire_messages = to_wire_messages(messages)
        body: dict[str, Any] = {
            "anthropic_version": ANTHROPIC_VERSION,
            "max_tokens": self.max_tokens,
            "messages": wire_messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [to_wire_tool(t) for t in tools]
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url}/model/{quote(self.model, safe='')}/invoke"
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
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block["text"])
                yield StreamEvent(type="text", text=block["text"])
            elif block.get("type") == "tool_use":
                call = ToolCall(
                    id=block["id"], name=block["name"], arguments=block.get("input") or {}
                )
                tool_calls.append(call)
                yield StreamEvent(type="tool_call", tool_call=call)
        raw_usage = data.get("usage") or {}
        usage = Usage(
            input_tokens=raw_usage.get("input_tokens", 0),
            output_tokens=raw_usage.get("output_tokens", 0),
            cached_tokens=raw_usage.get("cache_read_input_tokens", 0),
        )
        stop_reason: StopReason = STOP_REASONS.get(data.get("stop_reason") or "", "end")
        if tool_calls:
            stop_reason = "tool_use"
        message = Message(role="assistant", content="".join(text_parts), tool_calls=tool_calls)
        yield StreamEvent(
            type="done", response=Response(message=message, usage=usage, stop_reason=stop_reason)
        )
