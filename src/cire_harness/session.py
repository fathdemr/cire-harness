import json
from pathlib import Path

from cire_harness.providers.types import Message


def sessions_dir() -> Path:
    path = Path.home() / ".cire" / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_session(session_id: str, messages: list[Message]) -> Path:
    path = sessions_dir() / f"{session_id}.json"
    data = [m.model_dump(mode="json") for m in messages]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_session(session_id: str) -> list[Message]:
    path = sessions_dir() / f"{session_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Message.model_validate(d) for d in data]


def list_sessions() -> list[str]:
    files = sorted(sessions_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.stem for p in files]
