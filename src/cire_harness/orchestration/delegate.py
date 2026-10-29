from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cire_harness.loop.loop import Approve, OnEvent
from cire_harness.orchestration.executor import delegate
from cire_harness.orchestration.spec import TaskSpec
from cire_harness.providers import Provider
from cire_harness.providers.types import ToolSpec
from cire_harness.tools import Tool, schema

STRINGS = {"type": "array", "items": {"type": "string"}}


def delegate_tool(
    executor: Provider, root: Path, approve: Approve, on_event: OnEvent | None = None
) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        try:
            spec = TaskSpec.model_validate(args)
        except ValidationError as exc:
            return f"error: bad spec: {exc}"
        report = await delegate(spec, executor, root, approve, on_event)
        return report.render()

    return Tool(
        ToolSpec(
            name="delegate",
            description="Hand a well-defined coding task to a cheaper executor model that works "
            "in a fresh context with file tools only. Give a precise goal, the files it may "
            "change, constraints, and acceptance shell commands that must exit 0. Returns a "
            "short report with the verification output. Use it for mechanical multi-file work; "
            "do small edits yourself.",
            parameters=schema(
                goal={"type": "string"},
                files={**STRINGS, "optional": True},
                constraints={**STRINGS, "optional": True},
                acceptance={**STRINGS, "optional": True},
                max_turns={"type": "integer", "optional": True},
            ),
        ),
        run,
    )
