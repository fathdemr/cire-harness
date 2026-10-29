import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class MCPServer(BaseModel):
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    trusted: bool = False

    @model_validator(mode="after")
    def one_transport(self) -> "MCPServer":
        if bool(self.command) == bool(self.url):
            raise ValueError("give exactly one of command or url")
        return self


class Config(BaseModel):
    mcp: dict[str, MCPServer] = Field(default_factory=dict)


def load_config(path: Path | None = None) -> Config:
    if path is None:
        path = Path.home() / ".cire" / "config.toml"
    if not path.exists():
        return Config()
    return Config.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
