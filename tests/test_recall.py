import pytest

from cire_harness.context.recall import MAX_RECALL_CHARS, recall_tools
from cire_harness.context.store import ContextStore
from cire_harness.providers.types import ToolCall


@pytest.fixture
def recall(tmp_path):
    store = ContextStore(tmp_path / "cire.db")
    store.mask("s1", ToolCall(id="c", name="bash", arguments={}), "alpha beta " * 1000)
    return recall_tools(store, "s1")[0]


async def test_recall_by_id_pages(recall):
    first = await recall.run({"id": 1})
    assert first.startswith("alpha beta")
    assert f"offset={MAX_RECALL_CHARS}" in first
    rest = await recall.run({"id": "1", "offset": MAX_RECALL_CHARS})
    assert "[more" not in rest


async def test_recall_by_query_and_errors(recall):
    assert (await recall.run({"query": "alpha"})).startswith("tool_result 1:")
    assert await recall.run({"query": "zzz"}) == "no matches"
    assert (await recall.run({"id": 5})).startswith("error:")
    assert (await recall.run({})).startswith("error:")
