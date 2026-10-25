import os
import time

import pytest

from cire_harness.providers.types import Message, ToolCall
from cire_harness.session import list_sessions, load_session, save_session


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_save_and_load_round_trip(home):
    messages = [
        Message(role="user", content="merhaba"),
        Message(
            role="assistant",
            tool_calls=[ToolCall(id="c1", name="grep", arguments={"pattern": "x"})],
        ),
        Message(role="tool", content="no matches", tool_call_id="c1"),
    ]
    path = save_session("s1", messages)
    assert path == home / ".cire" / "sessions" / "s1.json"
    assert load_session("s1") == messages


def test_missing_session_raises():
    with pytest.raises(FileNotFoundError):
        load_session("nope")


def test_list_sessions_newest_first():
    save_session("old", [])
    save_session("new", [])
    os.utime(save_session("old", []), (time.time() - 60, time.time() - 60))
    assert list_sessions() == ["new", "old"]
