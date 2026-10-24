from pathlib import Path
from typing import Any

from cire_harness.providers.types import ToolSpec
from cire_harness.tools import Tool, resolve_inside, schema

MAX_READ_CHARS = 40_000


def fs_tools(root: Path) -> list[Tool]:
    root = root.resolve()

    async def read_file(args: dict[str, Any]) -> str:
        try:
            path = resolve_inside(root, args["path"])
            text = path.read_text()
        except (OSError, ValueError, KeyError) as exc:
            return f"error: {exc}"
        if len(text) > MAX_READ_CHARS:
            return text[:MAX_READ_CHARS] + f"\n[truncated, {len(text)} chars total]"
        return text

    async def write_file(args: dict[str, Any]) -> str:
        try:
            path = resolve_inside(root, args["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"])
        except (OSError, ValueError, KeyError) as exc:
            return f"error: {exc}"
        return f"wrote {len(args['content'])} chars to {args['path']}"

    async def edit_file(args: dict[str, Any]) -> str:
        try:
            path = resolve_inside(root, args["path"])
            text = path.read_text()
            old, new = args["old"], args["new"]
        except (OSError, ValueError, KeyError) as exc:
            return f"error: {exc}"
        count = text.count(old)
        if count != 1:
            return f"error: old text found {count} times, must be exactly 1"
        path.write_text(text.replace(old, new, 1))
        return f"edited {args['path']}"

    async def glob_files(args: dict[str, Any]) -> str:
        pattern = args.get("pattern", "**/*")
        matches = sorted(
            str(p.relative_to(root))
            for p in root.glob(pattern)
            if p.is_file() and ".git" not in p.parts
        )
        if not matches:
            return "no files matched"
        return "\n".join(matches[:500])

    return [
        Tool(
            ToolSpec(
                name="read_file",
                description="Read a text file relative to the working directory",
                parameters=schema(path={"type": "string"}),
            ),
            read_file,
        ),
        Tool(
            ToolSpec(
                name="write_file",
                description="Create or overwrite a text file",
                parameters=schema(path={"type": "string"}, content={"type": "string"}),
            ),
            write_file,
        ),
        Tool(
            ToolSpec(
                name="edit_file",
                description="Replace one exact occurrence of old with new in a file",
                parameters=schema(
                    path={"type": "string"}, old={"type": "string"}, new={"type": "string"}
                ),
            ),
            edit_file,
        ),
        Tool(
            ToolSpec(
                name="glob_files",
                description="List files matching a glob pattern, for example src/**/*.py",
                parameters=schema(pattern={"type": "string", "optional": True}),
            ),
            glob_files,
        ),
    ]
