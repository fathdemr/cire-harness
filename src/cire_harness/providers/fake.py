from collections.abc import AsyncIterator, Sequence

from cire_harness.providers.base import ProviderError
from cire_harness.providers.types import Message, Response, StreamEvent, ToolSpec


class FakeProvider:
    name = "fake"

    def __init__(self, responses: Sequence[Response], model: str = "fake-model") -> None:
        self.model = model
        self.responses = list(responses)
        self.calls: list[tuple[list[Message], list[ToolSpec]]] = []

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append((list(messages), list(tools)))
        if not self.responses:
            raise ProviderError("fake provider has no responses left")
        response = self.responses.pop(0)
        for word in response.message.content.split(" "):
            yield StreamEvent(type="text", text=word + " ")
        for call in response.message.tool_calls:
            yield StreamEvent(type="tool_call", tool_call=call)
        yield StreamEvent(type="done", response=response)
