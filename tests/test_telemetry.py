from cire_harness.context.store import ContextStore
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, Usage
from cire_harness.telemetry import CallRecord, Metered, estimate_cost


def reply(text, inp=0, out=0):
    return Response(
        message=Message(role="assistant", content=text),
        usage=Usage(input_tokens=inp, output_tokens=out),
    )


async def test_metered_records_each_call_and_passes_events_through():
    records = []
    provider = Metered(
        FakeProvider([reply("a b", 10, 2), reply("c", 5, 1)]), "planner", records.append
    )
    assert (provider.name, provider.model) == ("fake", "fake-model")
    events = [e async for e in provider.stream([Message(role="user", content="x")])]
    assert [e.type for e in events] == ["text", "text", "done"]
    [e async for e in provider.stream([])]
    assert [(r.role, r.model, r.input_tokens, r.output_tokens) for r in records] == [
        ("planner", "fake-model", 10, 2),
        ("planner", "fake-model", 5, 1),
    ]
    assert all(r.duration >= 0 for r in records)


def test_estimate_cost_known_unknown_and_overrides():
    assert (
        estimate_cost("bedrock", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0", 1_000_000, 0)
        == 3.0
    )
    assert estimate_cost("ollama+prompt-tools", "llama3.1", 1_000_000, 1_000_000) == 0.0
    assert estimate_cost("openai", "mystery-model", 10, 10) is None
    prices = {"mystery-model": {"input": 1.0, "output": 2.0}}
    assert estimate_cost("openai", "mystery-model", 1_000_000, 1_000_000, prices) == 3.0


def test_store_saves_and_totals_calls(tmp_path):
    store = ContextStore(tmp_path / "db")
    rec = CallRecord(
        role="planner",
        provider="fake",
        model="m",
        input_tokens=10,
        output_tokens=2,
        cached_tokens=1,
        duration=0.5,
    )
    store.save_call("s1", rec)
    store.save_call("s1", rec)
    store.save_call("s2", rec.model_copy(update={"role": "executor"}))
    assert store.call_totals("s1") == [("planner", "fake", "m", 2, 20, 4, 2, 1.0)]
    assert [row[0] for row in store.call_totals()] == ["executor", "planner"]
