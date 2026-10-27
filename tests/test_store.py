import pytest

from cire_harness.context.store import ContextStore
from cire_harness.providers.types import Message, ToolCall


@pytest.fixture
def store(tmp_path):
    return ContextStore(tmp_path / "db" / "cire.db")


def test_save_and_load_round_trip(store):
    messages = [
        Message(role="user", content="merhaba"),
        Message(
            role="assistant",
            tool_calls=[ToolCall(id="c1", name="grep", arguments={"pattern": "x"})],
        ),
        Message(role="tool", content="no matches", tool_call_id="c1"),
    ]
    store.save_messages("s1", messages)
    store.save_messages("s1", messages)
    assert store.load_messages("s1") == messages


def test_missing_session_raises(store):
    with pytest.raises(KeyError):
        store.load_messages("nope")


def test_list_sessions_newest_first(store):
    store.save_messages("old", [])
    store.save_messages("new", [])
    store.save_messages("old", [])
    assert store.list_sessions() == ["old", "new"]
