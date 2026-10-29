import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class Task(BaseModel):
    name: str
    prompt: str
    acceptance: list[str] = Field(min_length=1)
    fixture: Path


def load_tasks(root: Path, names: list[str] | None = None) -> list[Task]:
    tasks = []
    for folder in sorted(p for p in root.iterdir() if (p / "task.toml").exists()):
        if names and folder.name not in names:
            continue
        data = tomllib.loads((folder / "task.toml").read_text(encoding="utf-8"))
        tasks.append(Task(name=folder.name, fixture=folder / "repo", **data))
    if not tasks:
        raise ValueError(f"no tasks found in {root}")
    return tasks
