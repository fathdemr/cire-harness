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


def test_mask_keeps_small_results_and_stores_large(store):
    call = ToolCall(id="c1", name="bash", arguments={})
    assert store.mask("s1", call, "short") == "short"
    masked = store.mask("s1", call, "line\n" * 1000)
    assert masked.startswith("line\n")
    assert "[stored result id=1, 5000 chars" in masked
    assert store.load_tool_result(1) == "line\n" * 1000


def test_search_finds_tool_results_and_dropped_messages(store):
    call = ToolCall(id="c1", name="grep", arguments={})
    store.mask("s1", call, "needle in a haystack " * 100)
    store.mask("other", call, "needle elsewhere " * 100)
    store.save_summary("s1", "summary", [Message(role="user", content="find the needle")])
    hits = store.search("s1", "needle")
    assert {kind for kind, _, _ in hits} == {"tool_result", "message"}
    assert all("needle" in snippet for _, _, snippet in hits)
    assert store.search("s1", "elsewhere") == []


def test_missing_tool_result_raises(store):
    with pytest.raises(KeyError):
        store.load_tool_result(99)
