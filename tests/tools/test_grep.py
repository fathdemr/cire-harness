from cire_harness.tools.grep import MAX_LINES, grep_tools


def grep(root):
    return grep_tools(root)[0].run


async def test_finds_match_with_relative_path(tmp_path):
    (tmp_path / "a.py").write_text("hello world\n")
    assert "a.py:1:hello world" in await grep(tmp_path)({"pattern": "hello"})


async def test_no_match_is_not_an_error(tmp_path):
    (tmp_path / "a.py").write_text("hello\n")
    assert await grep(tmp_path)({"pattern": "zzz"}) == "no matches"


async def test_git_dir_is_skipped(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("hello\n")
    (tmp_path / "a.py").write_text("hello\n")
    result = await grep(tmp_path)({"pattern": "hello"})
    assert ".git" not in result
    assert "a.py" in result


async def test_output_is_truncated(tmp_path):
    (tmp_path / "big.txt").write_text("x\n" * 300)
    result = await grep(tmp_path)({"pattern": "x"})
    lines = result.splitlines()
    assert len(lines) == MAX_LINES + 1
    assert lines[-1] == "[truncated, 300 lines total]"


async def test_path_outside_root_is_rejected(tmp_path):
    result = await grep(tmp_path)({"pattern": "x", "path": "../../etc"})
    assert result.startswith("error:")
