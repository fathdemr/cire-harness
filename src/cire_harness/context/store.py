import sqlite3
import time
from pathlib import Path

from cire_harness.providers.types import Message

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
"""


class ContextStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path.home() / ".cire" / "cire.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def save_messages(self, session_id: str, messages: list[Message]) -> None:
        rows = [(session_id, seq, m.model_dump_json()) for seq, m in enumerate(messages)]
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO sessions (id, updated_at) VALUES (?, ?)",
                (session_id, time.time()),
            )
            self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self.conn.executemany("INSERT INTO messages VALUES (?, ?, ?)", rows)

    def load_messages(self, session_id: str) -> list[Message]:
        found = self.conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if found is None:
            raise KeyError(session_id)
        rows = self.conn.execute(
            "SELECT data FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)
        )
        return [Message.model_validate_json(data) for (data,) in rows]

    def list_sessions(self) -> list[str]:
        rows = self.conn.execute("SELECT id FROM sessions ORDER BY updated_at DESC")
        return [session_id for (session_id,) in rows]
