from collections.abc import Sequence

from cire_harness.providers import Provider
from cire_harness.providers.base import complete
from cire_harness.providers.types import Message

KEEP_MESSAGES = 6
SUMMARY_PREFIX = "Summary of earlier conversation:\n"
PROMPT = (
    "Summarize the conversation so far for your own future reference. Keep: the user's goal, "
    "decisions made, files and commands touched, open problems, stored result ids. "
    "Be terse, use bullet points, no preamble."
)


def estimate_tokens(messages: Sequence[Message]) -> int:
    chars = sum(len(m.content) + sum(len(str(c.arguments)) for c in m.tool_calls) for m in messages)
    return chars // 4


def split_point(messages: Sequence[Message], keep: int) -> int:
    cut = max(len(messages) - keep, 0)
    while cut > 0 and messages[cut].role != "user":
        cut -= 1
    return cut


async def compact(
    provider: Provider, messages: list[Message], keep: int = KEEP_MESSAGES
) -> tuple[list[Message], str]:
    cut = split_point(messages, keep)
    head = messages[:cut]
    if not head:
        return messages, ""
    response = await complete(provider, [*head, Message(role="user", content=PROMPT)])
    summary = response.message.content.strip()
    return [Message(role="system", content=SUMMARY_PREFIX + summary), *messages[cut:]], summary
