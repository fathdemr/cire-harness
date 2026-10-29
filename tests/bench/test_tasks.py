import shutil
from pathlib import Path

import pytest

from cire_harness.bench.tasks import load_tasks
from cire_harness.orchestration.spec import TaskSpec
from cire_harness.orchestration.verify import verify

TASKS = Path(__file__).parents[2] / "benchmarks" / "tasks"


def test_all_tasks_load():
    names = [t.name for t in load_tasks(TASKS)]
    assert names == [
        "add-cli-flag",
        "add-tests",
        "fix-failing-test",
        "rename-across-files",
        "write-module-from-spec",
    ]
    assert [t.name for t in load_tasks(TASKS, ["add-tests"])] == ["add-tests"]
    with pytest.raises(ValueError):
        load_tasks(TASKS, ["nope"])


@pytest.mark.parametrize("task", load_tasks(TASKS), ids=lambda t: t.name)
async def test_unsolved_fixture_fails_acceptance(task, tmp_path):
    shutil.copytree(task.fixture, tmp_path, dirs_exist_ok=True)
    ok, report = await verify(
        TaskSpec(goal=task.prompt, acceptance=task.acceptance), tmp_path, set()
    )
    assert not ok, report


SOLUTIONS = {
    "fix-failing-test": {
        "calc.py": (
            '"division by zero")\n    return a * b',
            '"division by zero")\n    return a / b',
        )
    },
    "rename-across-files": {
        "shapes.py": ("calc_area", "area"),
        "main.py": ("calc_area", "area"),
        "report.py": ("calc_area", "area"),
    },
    "add-cli-flag": {
        "tool.py": (
            'parser.add_argument("--upper", action="store_true", help="uppercase the text")\n',
            'parser.add_argument("--upper", action="store_true", help="uppercase the text")\n'
            '    parser.add_argument("--reverse", action="store_true", help="reverse the text")\n',
        )
    },
}
EXTRA = {
    "add-cli-flag": {
        "tool.py": [
            (
                "def transform(text, upper=False):",
                "def transform(text, upper=False, reverse=False):",
            ),
            ("    return text\n", "    if reverse:\n        text = text[::-1]\n    return text\n"),
            ("upper=args.upper)", "upper=args.upper, reverse=args.reverse)"),
        ]
    }
}
NEW_FILES = {
    "write-module-from-spec": {
        "slugify.py": (
            "import re\n\n\ndef slugify(text, max_length=50):\n"
            "    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n"
            "    if len(slug) > max_length:\n        slug = slug[:max_length].rstrip('-')\n"
            "    return slug\n"
        )
    },
    "add-tests": {
        "tests/test_stack.py": (
            "import sys\nsys.path.insert(0, '.')\nfrom stack import Stack\n\n"
            "s = Stack()\nassert s.is_empty() and s.size() == 0\n"
            "s.push(1); s.push(2)\nassert s.peek() == 2 and s.size() == 2\n"
            "assert s.pop() == 2 and s.pop() == 1\n"
            "for fn in (s.pop, s.peek):\n    try:\n        fn()\n"
            "    except IndexError:\n        pass\n"
            "    else:\n        raise AssertionError\nprint('ok')\n"
        )
    },
}


@pytest.mark.parametrize("task", load_tasks(TASKS), ids=lambda t: t.name)
async def test_reference_solution_passes_acceptance(task, tmp_path):
    shutil.copytree(task.fixture, tmp_path, dirs_exist_ok=True)
    for name, (old, new) in SOLUTIONS.get(task.name, {}).items():
        path = tmp_path / name
        path.write_text(path.read_text().replace(old, new))
    for name, edits in EXTRA.get(task.name, {}).items():
        path = tmp_path / name
        text = path.read_text()
        for old, new in edits:
            assert old in text, old
            text = text.replace(old, new)
        path.write_text(text)
    for name, content in NEW_FILES.get(task.name, {}).items():
        (tmp_path / name).write_text(content)
    ok, report = await verify(
        TaskSpec(goal=task.prompt, acceptance=task.acceptance), tmp_path, set()
    )
    assert ok, report
