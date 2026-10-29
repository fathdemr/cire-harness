import time
from collections.abc import AsyncIterator, Callable, Sequence

from pydantic import BaseModel

from cire_harness.providers import Provider
from cire_harness.providers.types import Message, StreamEvent, ToolSpec

PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-oss-120b": (0.15, 0.60),
    "gpt-oss-20b": (0.07, 0.30),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
}


class CallRecord(BaseModel):
    role: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    duration: float


Sink = Callable[[CallRecord], None]


def estimate_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int, prices=None
) -> float | None:
    if provider.startswith("ollama"):
        return 0.0
    table = dict(PRICES_PER_MILLION)
    table.update({k: (v["input"], v["output"]) for k, v in (prices or {}).items()})
    for key in sorted(table, key=len, reverse=True):
        if key in model:
            per_in, per_out = table[key]
            return (input_tokens * per_in + output_tokens * per_out) / 1_000_000
    return None


class Metered:
    def __init__(self, inner: Provider, role: str, sink: Sink) -> None:
        self.inner = inner
        self.role = role
        self.sink = sink

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamEvent]:
        started = time.monotonic()
        async for event in self.inner.stream(messages, tools):
            if event.type == "done" and event.response is not None:
                usage = event.response.usage
                self.sink(
                    CallRecord(
                        role=self.role,
                        provider=self.inner.name,
                        model=self.inner.model,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cached_tokens=usage.cached_tokens,
                        duration=time.monotonic() - started,
                    )
                )
            yield event
