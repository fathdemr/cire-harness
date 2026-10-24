import asyncio
from asyncio.subprocess import PIPE
from pathlib import Path
from typing import Any

from cire_harness.providers.types import ToolSpec
from cire_harness.tools import Tool, resolve_inside, schema

MAX_LINES = 200


def grep_tools(root: Path) -> list[Tool]:
    root = root.resolve()

    async def grep(args: dict[str, Any]) -> str:
        try:
            pattern = args["pattern"]
            path = resolve_inside(root, args.get("path", "."))
        except (OSError, ValueError, KeyError) as exc:
            return f"error: {exc}"

        cmd = ["grep", "-rn", "--exclude-dir=.git"]
        if glob := args.get("glob"):
            cmd.append(f"--include={glob}")
        cmd += [pattern, str(path.relative_to(root))]

        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=root, stdout=PIPE, stderr=PIPE,
        )

        stdout, stderr = await proc.communicate()
        if proc.returncode == 1:
            return "no matches"
        if proc.returncode == 2:
            return f"error: {stderr.decode().strip()}"

        lines = stdout.decode().splitlines()
        text = "\n".join(lines[:MAX_LINES])
        if len(lines) > MAX_LINES:
            text += f"\n[truncated, {len(lines)} lines total]"
        return text

    return [
        Tool(
            ToolSpec(
                name="grep",
                description="Search file contents for a regex pattern, returns file:line:text. glob limits to matching file names, for example *.py",
                parameters=schema(
                    pattern={"type": "string"},
                    path={"type": "string", "optional": True},
                    glob={"type": "string", "optional": True},
                ),
            ),
            grep,
        )
    ]
