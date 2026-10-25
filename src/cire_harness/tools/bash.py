import asyncio
from asyncio.subprocess import PIPE, STDOUT
from pathlib import Path
from typing import Any

from cire_harness.providers.types import ToolSpec
from cire_harness.tools import Tool, schema

DEFAULT_TIMEOUT = 60
MAX_LINES = 200


def bash_tools(root: Path) -> list[Tool]:
    root = root.resolve()

    async def bash(args: dict[str, Any]) -> str:
        try:
            command = args["command"]
            timeout = args.get("timeout", DEFAULT_TIMEOUT)
        except KeyError as exc:
            return f"error: {exc}"

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=root,
            stdout=PIPE,
            stderr=STDOUT,
        )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return f"error: timed out after {timeout}s"

        lines = stdout.decode().splitlines()
        text = "\n".join(lines[:MAX_LINES])
        if len(lines) > MAX_LINES:
            text += f"\n[truncated, {len(lines)} lines total]"
        if proc.returncode:
            text += f"\n[exit code {proc.returncode}]"
        return text

    return [
        Tool(
            ToolSpec(
                name="bash",
                description="Run a shell command in the project root and return its output. "
                "stdout and stderr are combined, a non-zero exit code is appended as "
                "[exit code N]. Use timeout in seconds for long commands, default 60",
                parameters=schema(
                    command={"type": "string"},
                    timeout={"type": "integer", "optional": True},
                ),
            ),
            bash,
            risky=True,
        )
    ]
