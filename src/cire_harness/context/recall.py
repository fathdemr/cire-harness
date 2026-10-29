from typing import Any

from cire_harness.context.store import ContextStore
from cire_harness.providers.types import ToolSpec
from cire_harness.tools import Tool, schema

MAX_RECALL_CHARS = 8_000


def recall_tools(store: ContextStore, session_id: str) -> list[Tool]:
    async def recall(args: dict[str, Any]) -> str:
        if (result_id := args.get("id")) is not None:
            try:
                text = store.load_tool_result(int(result_id))
            except (KeyError, ValueError):
                return f"error: no stored result {result_id}"
            offset = int(args.get("offset", 0))
            chunk = text[offset : offset + MAX_RECALL_CHARS]
            if offset + MAX_RECALL_CHARS < len(text):
                chunk += f"\n[more, call again with offset={offset + MAX_RECALL_CHARS}]"
            return chunk
        if query := args.get("query"):
            try:
                hits = store.search(session_id, query)
            except Exception as exc:
                return f"error: {exc}"
            if not hits:
                return "no matches"
            return "\n".join(f"{kind} {ref}: {snippet}" for kind, ref, snippet in hits)
        return "error: give id or query"

    return [
        Tool(
            ToolSpec(
                name="recall",
                description="Fetch a stored tool result by id (with optional offset for long "
                "ones) or full-text search earlier tool results and messages with query.",
                parameters=schema(
                    id={"type": "integer", "optional": True},
                    offset={"type": "integer", "optional": True},
                    query={"type": "string", "optional": True},
                ),
            ),
            recall,
        )
    ]
