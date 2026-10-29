import pytest

from cire_harness.providers.base import ProviderError, complete
from cire_harness.providers.types import Message, Response, StreamEvent, Usage


class Scripted:
    name = "scripted"
    model = "none"

    def __init__(self, events):
        self.events = events

    async def stream(self, messages, tools=()):
        for event in self.events:
            yield event


async def test_complete_returns_done_response():
    response = Response(
        message=Message(role="assistant", content="hi"), usage=Usage(input_tokens=3)
    )
    provider = Scripted(
        [StreamEvent(type="text", text="hi"), StreamEvent(type="done", response=response)]
    )
    assert await complete(provider, [Message(role="user", content="hey")]) == response


async def test_complete_without_done_raises():
    provider = Scripted([StreamEvent(type="text", text="hi")])
    with pytest.raises(ProviderError):
        await complete(provider, [])


def test_usage_add():
    total = Usage(input_tokens=1, output_tokens=2) + Usage(input_tokens=3, cached_tokens=4)
    assert total == Usage(input_tokens=4, output_tokens=2, cached_tokens=4)


def test_provider_error_shows_body_when_present():
    assert str(ProviderError("HTTP 400", 400, '{"message":"bad"}')) == 'HTTP 400: {"message":"bad"}'
    assert str(ProviderError("timeout")) == "timeout"
