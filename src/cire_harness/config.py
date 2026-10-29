import json
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator


def default_path() -> Path:
    return Path.home() / ".cire" / "config.toml"


class MCPServer(BaseModel):
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: list[str] = Field(default_factory=list)
    trusted: bool = False

    @model_validator(mode="after")
    def one_transport(self) -> "MCPServer":
        if bool(self.command) == bool(self.url):
            raise ValueError("give exactly one of command or url")
        return self

    @field_validator("env")
    @classmethod
    def env_holds_names_only(cls, names: list[str]) -> list[str]:
        for name in names:
            if not name.isidentifier():
                raise ValueError(
                    f"env entry {name!r} must be a variable name, never a value; "
                    "set the value in your shell"
                )
        return names


class Config(BaseModel):
    mcp: dict[str, MCPServer] = Field(default_factory=dict)


def load_config(path: Path | None = None) -> Config:
    path = path or default_path()
    if not path.exists():
        return Config()
    return Config.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def save_config(config: Config, path: Path | None = None) -> Path:
    path = path or default_path()
    lines: list[str] = []
    for name, server in config.mcp.items():
        lines.append(f"[mcp.{json.dumps(name)}]")
        for key, value in server.model_dump(exclude_defaults=True).items():
            lines.append(f"{key} = {json.dumps(value)}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
