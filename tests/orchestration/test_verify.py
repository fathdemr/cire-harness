from cire_harness.orchestration.spec import TaskSpec
from cire_harness.orchestration.verify import verify


async def test_passing_commands_and_allowed_files(tmp_path):
    spec = TaskSpec(goal="g", files=["a.py"], acceptance=["echo fine", "test -d ."])
    ok, report = await verify(spec, tmp_path, {"a.py"})
    assert ok
    assert "$ echo fine -> ok\nfine" in report


async def test_failing_command_reports_tail(tmp_path):
    spec = TaskSpec(goal="g", acceptance=["echo boom; exit 3"])
    ok, report = await verify(spec, tmp_path, set())
    assert not ok
    assert "exit 3" in report and "boom" in report


async def test_file_outside_spec_fails(tmp_path):
    spec = TaskSpec(goal="g", files=["a.py"], acceptance=["true"])
    ok, report = await verify(spec, tmp_path, {"a.py", "b.py"})
    assert not ok
    assert "outside the spec: b.py" in report


async def test_timeout_is_a_failure(tmp_path):
    spec = TaskSpec(goal="g", acceptance=["sleep 5"])
    ok, report = await verify(spec, tmp_path, set(), timeout=0.2)
    assert not ok and "timed out" in report


async def test_no_acceptance_is_noted(tmp_path):
    ok, report = await verify(TaskSpec(goal="g"), tmp_path, set())
    assert ok and "no acceptance" in report
