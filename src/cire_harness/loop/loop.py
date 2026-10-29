from collections.abc import Awaitable, Callable

from cire_harness.providers import Provider
from cire_harness.providers.base import complete
from cire_harness.providers.types import Message, StreamEvent, ToolCall
from cire_harness.tools import ToolRegistry

Approve = Callable[[ToolCall], Awaitable[bool]]
OnEvent = Callable[[StreamEvent | Message], None]
Mask = Callable[[ToolCall, str], str]


async def run_agent(
    provider: Provider,
    registry: ToolRegistry,
    messages: list[Message],
    approve: Approve,
    max_turns: int = 20,
    on_event: OnEvent | None = None,
    mask: Mask | None = None,
) -> str:
    for _ in range(max_turns):
        response = await complete(provider, messages, registry.specs(), on_event)
        messages.append(response.message)
        if not response.message.tool_calls:
            return response.message.content
        for call in response.message.tool_calls:
            result = await run_tool(registry, call, approve)
            if mask is not None:
                result = mask(call, result)
            result_msg = Message(role="tool", content=result, tool_call_id=call.id)
            messages.append(result_msg)
            if on_event is not None:
                on_event(result_msg)
    return f"stopped after {max_turns} turns"


async def run_tool(registry: ToolRegistry, call: ToolCall, approve: Approve) -> str:
    tool = registry.get(call.name)
    if tool is None:
        return f"error: unknown tool {call.name}"
    if tool.risky and not await approve(call):
        return "error: permission denied"
    try:
        return await tool.run(call.arguments)
    except Exception as exc:
        return f"error: {type(exc).__name__}: {exc}"
