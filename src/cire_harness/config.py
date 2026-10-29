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


ROLES = ("planner", "executor", "compactor")


class Price(BaseModel):
    input: float = Field(ge=0)
    output: float = Field(ge=0)


class Config(BaseModel):
    roles: dict[str, str] = Field(default_factory=dict)
    prices: dict[str, Price] = Field(default_factory=dict)
    mcp: dict[str, MCPServer] = Field(default_factory=dict)

    @field_validator("roles")
    @classmethod
    def known_roles(cls, roles: dict[str, str]) -> dict[str, str]:
        for name, spec in roles.items():
            if name not in ROLES:
                raise ValueError(f"unknown role {name!r}, expected one of {', '.join(ROLES)}")
            if ":" not in spec:
                raise ValueError(f"role {name} must look like kind:model, got {spec!r}")
        return roles


def load_config(path: Path | None = None) -> Config:
    path = path or default_path()
    if not path.exists():
        return Config()
    return Config.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def save_config(config: Config, path: Path | None = None) -> Path:
    path = path or default_path()
    lines: list[str] = []
    if config.roles:
        lines.append("[roles]")
        lines += [f"{name} = {json.dumps(spec)}" for name, spec in config.roles.items()]
        lines.append("")
    for name, price in config.prices.items():
        lines.append(f"[prices.{json.dumps(name)}]")
        lines += [f"input = {price.input}", f"output = {price.output}", ""]
    for name, server in config.mcp.items():
        lines.append(f"[mcp.{json.dumps(name)}]")
        for key, value in server.model_dump(exclude_defaults=True).items():
            lines.append(f"{key} = {json.dumps(value)}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
