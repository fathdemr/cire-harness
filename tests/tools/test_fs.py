from cire_harness.tools import ToolRegistry
from cire_harness.tools.fs import fs_tools


def registry(root):
    return ToolRegistry(fs_tools(root))


async def test_write_then_read(tmp_path):
    reg = registry(tmp_path)
    assert "wrote" in await reg.get("write_file").run({"path": "a/b.txt", "content": "hi"})
    assert await reg.get("read_file").run({"path": "a/b.txt"}) == "hi"


async def test_read_missing_returns_error_string(tmp_path):
    result = await registry(tmp_path).get("read_file").run({"path": "nope.txt"})
    assert result.startswith("error:")


async def test_path_outside_root_is_rejected(tmp_path):
    result = await registry(tmp_path).get("read_file").run({"path": "../../etc/passwd"})
    assert "outside the working directory" in result


async def test_edit_requires_exactly_one_match(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\ny = 1\n")
    edit = registry(tmp_path).get("edit_file")
    assert "found 2 times" in await edit.run({"path": "f.py", "old": "= 1", "new": "= 2"})
    assert "found 0 times" in await edit.run({"path": "f.py", "old": "zzz", "new": ""})
    assert "edited" in await edit.run({"path": "f.py", "old": "x = 1", "new": "x = 2"})
    assert (tmp_path / "f.py").read_text() == "x = 2\ny = 1\n"


async def test_glob_lists_relative_paths_and_skips_git(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("")
    result = await registry(tmp_path).get("glob_files").run({"pattern": "**/*"})
    assert result == "src/a.py"


def test_specs_mark_optional_params(tmp_path):
    specs = {s.name: s for s in registry(tmp_path).specs()}
    assert specs["glob_files"].parameters["required"] == []
    assert specs["edit_file"].parameters["required"] == ["path", "old", "new"]


def test_only_writing_tools_are_risky(tmp_path):
    risky = {t.name for t in fs_tools(tmp_path) if t.risky}
    assert risky == {"write_file", "edit_file"}
