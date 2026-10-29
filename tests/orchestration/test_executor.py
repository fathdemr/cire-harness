from cire_harness.loop.loop import run_agent
from cire_harness.orchestration.delegate import delegate_tool
from cire_harness.orchestration.executor import delegate
from cire_harness.orchestration.spec import TaskSpec
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall, Usage
from cire_harness.tools import ToolRegistry

CHECK = 'test "$(cat a.txt)" = hi'


async def allow(call):
    return True


def reply(text="", calls=()):
    return Response(
        message=Message(role="assistant", content=text, tool_calls=list(calls)),
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def write(content, path="a.txt", cid="w"):
    return ToolCall(id=cid, name="write_file", arguments={"path": path, "content": content})


async def test_executor_succeeds_first_try(tmp_path):
    spec = TaskSpec(goal="write hi to a.txt", files=["a.txt"], acceptance=[CHECK])
    executor = FakeProvider([reply(calls=[write("hi")]), reply("wrote a.txt")])
    report = await delegate(spec, executor, tmp_path, allow)
    assert report.ok and report.attempts == 1
    assert report.touched == ["a.txt"]
    assert report.usage == Usage(input_tokens=20, output_tokens=10)
    sent = executor.calls[0][0]
    assert sent[0].role == "system" and "Goal: write hi to a.txt" in sent[0].content
    assert sent[1] == Message(role="user", content="Start now.")
    assert [t.name for t in executor.calls[0][1]] == [
        "read_file",
        "write_file",
        "edit_file",
        "glob_files",
        "grep",
    ]
    assert "status: ok after 1 attempt" in report.render()


async def test_failed_verification_retries_with_feedback(tmp_path):
    spec = TaskSpec(goal="g", acceptance=[CHECK])
    executor = FakeProvider(
        [reply(calls=[write("wrong")]), reply("done"), reply(calls=[write("hi")]), reply("fixed")]
    )
    report = await delegate(spec, executor, tmp_path, allow)
    assert report.ok and report.attempts == 2
    second_user = executor.calls[2][0][1]
    assert second_user.role == "user" and "failed verification" in second_user.content
    assert "exit 1" in second_user.content


async def test_two_failures_escalate_with_report(tmp_path):
    spec = TaskSpec(goal="g", files=["a.txt"], acceptance=[CHECK])
    executor = FakeProvider(
        [reply(calls=[write("x", path="b.txt")]), reply("oops"), reply("gave up")]
    )
    report = await delegate(spec, executor, tmp_path, allow)
    assert not report.ok and report.attempts == 2
    text = report.render()
    assert text.startswith("status: FAILED after 2 attempt(s)")
    assert "outside the spec: b.txt" in text and "executor report: gave up" in text


async def test_delegate_tool_through_planner_loop(tmp_path):
    call = ToolCall(
        id="d",
        name="delegate",
        arguments={"goal": "write hi", "files": ["a.txt"], "acceptance": [CHECK]},
    )
    planner = FakeProvider([reply(calls=[call]), reply("all good")])
    executor = FakeProvider([reply(calls=[write("hi")]), reply("wrote it")])
    registry = ToolRegistry([delegate_tool(executor, tmp_path, allow)])
    messages = [Message(role="user", content="do it")]
    assert await run_agent(planner, registry, messages, allow) == "all good"
    tool_msg = next(m for m in messages if m.role == "tool")
    assert tool_msg.content.startswith("status: ok")
    assert len(executor.calls[0][0]) == 2


async def test_delegate_tool_rejects_bad_spec(tmp_path):
    tool = delegate_tool(FakeProvider([]), tmp_path, allow)
    assert (await tool.run({"files": ["a"]})).startswith("error: bad spec")
    assert (await tool.run({"goal": "g", "max_turns": 0})).startswith("error: bad spec")
