from cire_harness.tools.bash import MAX_LINES, bash_tools


def bash(root):
    return bash_tools(root)[0].run


async def test_stdout_is_returned(tmp_path):
    assert await bash(tmp_path)({"command": "echo hi"}) == "hi"


async def test_non_zero_exit_code_is_appended(tmp_path):
    assert await bash(tmp_path)({"command": "exit 3"}) == "\n[exit code 3]"


async def test_stderr_is_merged(tmp_path):
    assert await bash(tmp_path)({"command": "echo err 1>&2"}) == "err"


async def test_runs_in_root(tmp_path):
    assert await bash(tmp_path)({"command": "pwd"}) == str(tmp_path.resolve())


async def test_timeout_kills_command(tmp_path):
    result = await bash(tmp_path)({"command": "sleep 5", "timeout": 0.1})
    assert result.startswith("error: timed out")


async def test_output_is_truncated(tmp_path):
    result = await bash(tmp_path)({"command": "seq 300"})
    lines = result.splitlines()
    assert len(lines) == MAX_LINES + 1
    assert lines[-1] == "[truncated, 300 lines total]"


async def test_missing_command_is_an_error(tmp_path):
    assert (await bash(tmp_path)({})).startswith("error:")


def test_tool_is_risky(tmp_path):
    assert bash_tools(tmp_path)[0].risky


async def test_timeout_given_as_string_is_accepted(tmp_path):
    assert await bash(tmp_path)({"command": "echo hi", "timeout": "5"}) == "hi"


async def test_bad_timeout_is_an_error(tmp_path):
    result = await bash(tmp_path)({"command": "echo hi", "timeout": "abc"})
    assert result.startswith("error:")
