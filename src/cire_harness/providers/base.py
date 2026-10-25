from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol

from cire_harness.providers.types import Message, Response, StreamEvent, ToolSpec


class ProviderError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class Provider(Protocol):
    name: str
    model: str

    def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamEvent]: ...


async def complete(
    provider: Provider,
    messages: Sequence[Message],
    tools: Sequence[ToolSpec] = (),
    on_event: Callable[[StreamEvent], None] | None = None,
) -> Response:
    async for event in provider.stream(messages, tools):
        if on_event is not None:
            on_event(event)
        if event.type == "done" and event.response is not None:
            return event.response
    raise ProviderError("stream ended without a done event")
