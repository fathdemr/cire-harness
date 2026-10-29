from cire_harness.context.compactor import compact, estimate_tokens, split_point
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall


def msgs(n):
    out = []
    for i in range(n):
        out.append(Message(role="user", content=f"question {i} " * 20))
        out.append(
            Message(role="assistant", tool_calls=[ToolCall(id=str(i), name="grep", arguments={})])
        )
        out.append(Message(role="tool", content="result " * 20, tool_call_id=str(i)))
        out.append(Message(role="assistant", content="answer " * 20))
    return out


def test_estimate_counts_content_and_tool_arguments():
    assert estimate_tokens([Message(role="user", content="a" * 40)]) == 10
    call = ToolCall(id="1", name="x", arguments={"k": "v"})
    assert estimate_tokens([Message(role="assistant", tool_calls=[call])]) > 0


def test_split_point_keeps_last_exchange_whole():
    history = msgs(3)
    cut = split_point(history, keep=6)
    assert history[cut].role == "user"
    assert cut == 4
    assert split_point(history, keep=11) == 0


async def test_compact_replaces_head_with_summary():
    history = msgs(5)
    provider = FakeProvider([Response(message=Message(role="assistant", content="short summary"))])
    new, summary = await compact(provider, history)
    assert summary == "short summary"
    assert new[0].role == "system" and "short summary" in new[0].content
    assert new[1:] == history[12:]
    assert estimate_tokens(new) < estimate_tokens(history)
    sent = provider.calls[0][0]
    assert sent[-1].role == "user" and "Summarize" in sent[-1].content


async def test_compact_with_nothing_to_drop_is_noop():
    history = msgs(1)
    new, summary = await compact(FakeProvider([]), history)
    assert new == history and summary == ""
