from pathlib import Path

from cire_harness.bench.report import render_markdown, save_results, summarize, totals
from cire_harness.bench.runner import run_task
from cire_harness.bench.tasks import Task
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall, Usage


def reply(text="", calls=(), inp=100, out=10):
    return Response(
        message=Message(role="assistant", content=text, tool_calls=list(calls)),
        usage=Usage(input_tokens=inp, output_tokens=out),
    )


def make_task(tmp_path) -> Task:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "note.txt").write_text("todo\n")
    return Task(
        name="demo",
        prompt="Replace todo with done in note.txt",
        acceptance=["grep -qx done note.txt"],
        fixture=fixture,
    )


def write_call():
    return ToolCall(id="w", name="write_file", arguments={"path": "note.txt", "content": "done\n"})


async def test_single_mode_runs_in_a_copy_and_verifies(tmp_path):
    task = make_task(tmp_path)
    planner = FakeProvider([reply(calls=[write_call()]), reply("did it")])
    result = await run_task(task, "single", lambda: planner)
    assert result.ok and result.mode == "single"
    assert (task.fixture / "note.txt").read_text() == "todo\n"
    assert result.tokens() == (200, 20) and result.cost() is None
    assert [c.role for c in result.calls] == ["planner", "planner"]
    assert planner.calls[0][0][0].role == "system"
    assert "Acceptance commands" in planner.calls[0][0][1].content


async def test_split_mode_uses_delegate_and_separates_roles(tmp_path):
    task = make_task(tmp_path)
    delegate = ToolCall(
        id="d", name="delegate", arguments={"goal": "do it", "acceptance": task.acceptance}
    )
    planner = FakeProvider([reply(calls=[delegate]), reply("summary")])
    executor = FakeProvider(
        [reply(calls=[write_call()], inp=5, out=1), reply("wrote", inp=5, out=1)]
    )
    result = await run_task(task, "split", lambda: planner, lambda: executor)
    assert result.ok
    assert result.tokens("planner") == (200, 20) and result.tokens("executor") == (10, 2)


async def test_failures_and_provider_errors_are_recorded(tmp_path):
    task = make_task(tmp_path)
    result = await run_task(task, "single", lambda: FakeProvider([reply("skip")]))
    assert not result.ok and "exit 1" in result.verification
    result = await run_task(task, "single", lambda: FakeProvider([]))
    assert not result.ok and result.answer.startswith("error: ProviderError")


async def test_report_tables_and_json(tmp_path):
    task = make_task(tmp_path)
    results = [
        await run_task(
            task, "single", lambda: FakeProvider([reply(calls=[write_call()]), reply("ok")])
        ),
        await run_task(task, "single", lambda: FakeProvider([reply("skip")])),
    ]
    rows = summarize(results, {"fake-model": {"input": 1.0, "output": 1.0}})
    assert rows[0]["passed"] == 1 and rows[0]["runs"] == 2
    assert rows[0]["avg_cost"] > 0
    assert totals(rows)[0]["task"] == "**all**"
    folder = tmp_path / "results"
    assert "No results yet" in render_markdown(folder)
    path = save_results(results, folder, {"baseline (single)": "fake:fake-model"}, "uv run x")
    assert Path(path).suffix == ".json" and "verification" in path.read_text()
    md = render_markdown(folder)
    assert "| demo | single | 1/2 | ? |" in md
    assert "| baseline (single) | `fake:fake-model` |" in md and "uv run x" in md
    assert md.count("## ") == 1
