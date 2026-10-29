from pathlib import Path

from cire_harness.loop.loop import Approve, OnEvent, run_agent
from cire_harness.orchestration.spec import Report, TaskSpec
from cire_harness.orchestration.verify import verify
from cire_harness.providers import Provider
from cire_harness.providers.types import Message, Usage
from cire_harness.tools import Tool, ToolRegistry
from cire_harness.tools.fs import fs_tools
from cire_harness.tools.grep import grep_tools

SYSTEM = (
    "You are an executor working inside a code repository. Do exactly the task below and "
    "nothing else. Read a file before editing it. You cannot run commands; the harness runs the "
    "acceptance commands after you finish. When done, reply with a short report of what you "
    "changed.\n\n"
)
WRITERS = ("write_file", "edit_file")


def executor_tools(root: Path) -> tuple[list[Tool], set[str]]:
    touched: set[str] = set()
    tools = fs_tools(root) + grep_tools(root)

    def tracking(tool: Tool) -> Tool:
        async def run(args):
            touched.add(str(args.get("path", "")))
            return await tool.run(args)

        return Tool(tool.spec, run, risky=tool.risky)

    return [tracking(t) if t.name in WRITERS else t for t in tools], touched


async def run_once(
    spec: TaskSpec,
    provider: Provider,
    root: Path,
    approve: Approve,
    on_event: OnEvent | None,
    feedback: str,
) -> tuple[str, set[str], Usage]:
    tools, touched = executor_tools(root)
    usage = Usage()

    def track(event):
        nonlocal usage
        if not isinstance(event, Message) and event.type == "done":
            usage += event.response.usage
        if on_event is not None:
            on_event(event)

    messages = [
        Message(role="system", content=SYSTEM + spec.render()),
        Message(role="user", content=feedback or "Start now."),
    ]
    summary = await run_agent(
        provider, ToolRegistry(tools), messages, approve, spec.max_turns, track
    )
    return summary, touched, usage


async def delegate(
    spec: TaskSpec,
    provider: Provider,
    root: Path,
    approve: Approve,
    on_event: OnEvent | None = None,
    retries: int = 1,
) -> Report:
    feedback = ""
    usage = Usage()
    touched: set[str] = set()
    attempts = 0
    while True:
        attempts += 1
        summary, new, used = await run_once(spec, provider, root, approve, on_event, feedback)
        usage += used
        touched |= new
        ok, verification = await verify(spec, root, touched)
        if ok or attempts > retries:
            break
        feedback = (
            "A previous attempt at this task failed verification:\n"
            f"{verification}\n\nFix the problem. The files already contain the previous changes."
        )
    return Report(
        ok=ok,
        attempts=attempts,
        touched=sorted(touched),
        summary=summary,
        verification=verification,
        usage=usage,
    )
