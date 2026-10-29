import sqlite3
import time
from pathlib import Path

from cire_harness.providers.types import Message, ToolCall
from cire_harness.telemetry import CallRecord

MASK_CHARS = 1500
HEAD_CHARS = 300

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
CREATE TABLE IF NOT EXISTS tool_results (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL,
    duration REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS recall_fts USING fts5(
    session_id UNINDEXED, kind UNINDEXED, ref UNINDEXED, content
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

    def save_tool_result(self, session_id: str, tool: str, content: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO tool_results (session_id, tool, content) VALUES (?, ?, ?)",
                (session_id, tool, content),
            )
            self.conn.execute(
                "INSERT INTO recall_fts VALUES (?, 'tool_result', ?, ?)",
                (session_id, str(cur.lastrowid), content),
            )
        return cur.lastrowid

    def load_tool_result(self, result_id: int) -> str:
        row = self.conn.execute(
            "SELECT content FROM tool_results WHERE id = ?", (result_id,)
        ).fetchone()
        if row is None:
            raise KeyError(result_id)
        return row[0]

    def mask(self, session_id: str, call: ToolCall, result: str) -> str:
        if len(result) <= MASK_CHARS:
            return result
        result_id = self.save_tool_result(session_id, call.name, result)
        return (
            f"{result[:HEAD_CHARS]}\n"
            f"[stored result id={result_id}, {len(result)} chars, "
            f"use recall with id={result_id} or a query to see more]"
        )

    def save_summary(self, session_id: str, content: str, dropped: list[Message]) -> None:
        rows = [(session_id, "message", m.role, m.content) for m in dropped if m.content.strip()]
        with self.conn:
            self.conn.execute(
                "INSERT INTO summaries (session_id, content, created_at) VALUES (?, ?, ?)",
                (session_id, content, time.time()),
            )
            self.conn.executemany("INSERT INTO recall_fts VALUES (?, ?, ?, ?)", rows)

    def search(self, session_id: str, query: str, limit: int = 5) -> list[tuple[str, str, str]]:
        rows = self.conn.execute(
            "SELECT kind, ref, snippet(recall_fts, 3, '', '', '...', 24) FROM recall_fts "
            "WHERE recall_fts MATCH ? AND session_id = ? ORDER BY rank LIMIT ?",
            (query, session_id, limit),
        )
        return list(rows)

    def save_call(self, session_id: str, record: CallRecord) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO calls (session_id, role, provider, model, input_tokens, "
                "output_tokens, cached_tokens, duration, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    record.role,
                    record.provider,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    record.cached_tokens,
                    record.duration,
                    time.time(),
                ),
            )

    def call_totals(self, session_id: str | None = None) -> list[tuple]:
        where = "WHERE session_id = ?" if session_id else ""
        params = (session_id,) if session_id else ()
        return self.conn.execute(
            "SELECT role, provider, model, COUNT(*), SUM(input_tokens), SUM(output_tokens), "
            f"SUM(cached_tokens), SUM(duration) FROM calls {where} "
            "GROUP BY role, provider, model ORDER BY role, provider, model",
            params,
        ).fetchall()
