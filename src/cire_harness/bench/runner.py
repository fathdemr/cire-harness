import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from cire_harness.bench.tasks import Task
from cire_harness.loop.loop import run_agent
from cire_harness.orchestration.delegate import delegate_tool
from cire_harness.orchestration.spec import TaskSpec
from cire_harness.orchestration.verify import verify
from cire_harness.providers import Provider
from cire_harness.providers.types import Message, ToolCall
from cire_harness.telemetry import CallRecord, Metered, estimate_cost
from cire_harness.tools import ToolRegistry
from cire_harness.tools.bash import bash_tools
from cire_harness.tools.fs import fs_tools
from cire_harness.tools.grep import grep_tools

PLANNER_PROMPT = (
    "You are the planner. Hand implementation work to the executor with the delegate tool: "
    "write a precise goal, list the files it may change, and pass the acceptance commands given "
    "in the task. Inspect the repository first if you need to. Only edit files yourself if the "
    "delegate reports failure twice. Finish with a one-line summary."
)
SINGLE_PROMPT = "Work inside the current directory. Finish with a one-line summary."


class RunResult(BaseModel):
    task: str
    mode: str
    ok: bool
    seconds: float
    calls: list[CallRecord] = Field(default_factory=list)
    verification: str = ""
    answer: str = ""

    def tokens(self, role: str | None = None) -> tuple[int, int]:
        calls = [c for c in self.calls if role is None or c.role == role]
        return sum(c.input_tokens for c in calls), sum(c.output_tokens for c in calls)

    def cost(self, prices=None) -> float | None:
        total = 0.0
        for call in self.calls:
            cost = estimate_cost(
                call.provider, call.model, call.input_tokens, call.output_tokens, prices
            )
            if cost is None:
                return None
            total += cost
        return total


async def allow(call: ToolCall) -> bool:
    return True


ProviderFactory = Callable[[], Provider]


async def run_task(
    task: Task,
    mode: str,
    planner: ProviderFactory,
    executor: ProviderFactory | None = None,
    max_turns: int = 30,
) -> RunResult:
    workdir = Path(tempfile.mkdtemp(prefix=f"bench-{task.name}-"))
    shutil.copytree(task.fixture, workdir, dirs_exist_ok=True)
    calls: list[CallRecord] = []
    registry = ToolRegistry(fs_tools(workdir) + grep_tools(workdir) + bash_tools(workdir))
    system = SINGLE_PROMPT
    if mode == "split":
        if executor is None:
            raise ValueError("split mode needs an executor")
        tool = delegate_tool(Metered(executor(), "executor", calls.append), workdir, allow)
        registry.tools[tool.name] = tool
        system = PLANNER_PROMPT
    prompt = (
        task.prompt + "\n\nAcceptance commands:\n" + "\n".join(f"- {c}" for c in task.acceptance)
    )
    messages = [Message(role="system", content=system), Message(role="user", content=prompt)]
    started = time.monotonic()
    try:
        answer = await run_agent(
            Metered(planner(), "planner", calls.append), registry, messages, allow, max_turns
        )
    except Exception as exc:
        answer = f"error: {type(exc).__name__}: {exc}"
    seconds = time.monotonic() - started
    ok, verification = await verify(
        TaskSpec(goal=task.prompt, acceptance=task.acceptance), workdir, set()
    )
    shutil.rmtree(workdir, ignore_errors=True)
    return RunResult(
        task=task.name,
        mode=mode,
        ok=ok,
        seconds=seconds,
        calls=calls,
        verification=verification,
        answer=answer[:500],
    )
