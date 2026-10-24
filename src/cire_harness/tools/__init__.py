from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cire_harness.providers.types import ToolSpec


@dataclass
class Tool:
    spec: ToolSpec
    run: Callable[[dict[str, Any]], Awaitable[str]]
    risky: bool = False

    @property
    def name(self) -> str:
        return self.spec.name


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self.tools = {t.name: t for t in tools}

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self.tools.values()]

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)


def resolve_inside(root: Path, raw: str) -> Path:
    path = (root / raw).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path {raw!r} is outside the working directory")
    return path


def schema(**props: dict[str, Any]) -> dict[str, Any]:
    required = [k for k, v in props.items() if not v.pop("optional", False)]
    return {"type": "object", "properties": props, "required": required}
