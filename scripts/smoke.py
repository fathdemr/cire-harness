import asyncio
import sys

from cire_harness.providers import get_provider
from cire_harness.providers.base import complete
from cire_harness.providers.types import Message, ToolSpec

TOOLS = [
    ToolSpec(
        name="read_file",
        description="Read a text file from disk",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
]


async def run(spec: str) -> None:
    provider = get_provider(spec)
    history = [
        Message(role="system", content="You are a terse coding assistant."),
        Message(role="user", content="Read the file README.md and tell me its first heading."),
    ]
    first = await complete(provider, history, TOOLS)
    print(f"[{spec}] stop={first.stop_reason} tools={[c.name for c in first.message.tool_calls]}")
    if not first.message.tool_calls:
        print(f"[{spec}] text={first.message.content[:200]!r}")
        return
    history.append(first.message)
    for call in first.message.tool_calls:
        history.append(
            Message(role="tool", content="# cire-harness\n\nsome text", tool_call_id=call.id)
        )
    second = await complete(provider, history, TOOLS)
    usage = first.usage + second.usage
    again = [c.name for c in second.message.tool_calls]
    print(f"[{spec}] answer={second.message.content.strip()[:200]!r} tools={again}")
    print(f"[{spec}] tokens in={usage.input_tokens} out={usage.output_tokens}")
    print(f"[{spec}] cached={usage.cached_tokens}")


async def main(specs: list[str]) -> None:
    for spec in specs:
        try:
            await run(spec)
        except Exception as exc:
            print(f"[{spec}] FAILED: {exc}")


if __name__ == "__main__":
    asyncio.run(
        main(sys.argv[1:] or ["anthropic:claude-opus-5-5", "openai:gpt-4o-mini", "ollama:qwen2.5"])
    )
