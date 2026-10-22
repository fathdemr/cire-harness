import json
import re
import uuid
from collections.abc import AsyncIterator, Sequence

from cire_harness.providers.base import Provider
from cire_harness.providers.types import Message, Response, StreamEvent, ToolCall, ToolSpec

TOOL_BLOCK = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)

INSTRUCTIONS = """You can call tools. To call one, write a fenced block exactly like this:

```tool
{"name": "<tool name>", "arguments": {<json arguments>}}
```

One block per call. Say nothing after the blocks. Tool results come back in the next message.
Available tools:
"""


def render_tools(tools: Sequence[ToolSpec]) -> str:
    lines = [INSTRUCTIONS]
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description}")
        lines.append(f"  arguments schema: {json.dumps(tool.parameters)}")
    return "\n".join(lines)


def render_call(call: ToolCall) -> str:
    payload = json.dumps({"name": call.name, "arguments": call.arguments})
    return f"```tool\n{payload}\n```"


def flatten(messages: Sequence[Message], tools: Sequence[ToolSpec]) -> list[Message]:
    out: list[Message] = []
    if tools:
        out.append(Message(role="system", content=render_tools(tools)))
    for message in messages:
        if message.role == "tool":
            out.append(Message(role="user", content=f"Tool result:\n{message.content}"))
        elif message.tool_calls:
            parts = [message.content] if message.content else []
            parts.extend(render_call(c) for c in message.tool_calls)
            out.append(Message(role="assistant", content="\n".join(parts)))
        else:
            out.append(message)
    return out


def extract_calls(text: str) -> tuple[str, list[ToolCall]]:
    calls: list[ToolCall] = []
    for match in TOOL_BLOCK.finditer(text):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "name" not in data:
            continue
        calls.append(
            ToolCall(
                id=uuid.uuid4().hex[:8],
                name=str(data["name"]),
                arguments=data.get("arguments") or {},
            )
        )
    return TOOL_BLOCK.sub("", text).strip(), calls


class PromptToolProvider:
    def __init__(self, inner: Provider) -> None:
        self.inner = inner
        self.name = f"{inner.name}+prompt-tools"
        self.model = inner.model

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamEvent]:
        async for event in self.inner.stream(flatten(messages, tools)):
            if event.type != "done" or event.response is None:
                yield event
                continue
            response = event.response
            text, calls = extract_calls(response.message.content)
            for call in calls:
                yield StreamEvent(type="tool_call", tool_call=call)
            message = Message(role="assistant", content=text, tool_calls=calls)
            stop_reason = "tool_use" if calls else response.stop_reason
            yield StreamEvent(
                type="done",
                response=Response(message=message, usage=response.usage, stop_reason=stop_reason),
            )
