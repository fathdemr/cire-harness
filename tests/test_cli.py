from typer.testing import CliRunner

from cire_harness import __version__
from cire_harness.cli import app
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response, ToolCall, Usage

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"cire {__version__}"


def test_run_prints_answer(monkeypatch):
    fake = FakeProvider([Response(message=Message(role="assistant", content="hi there"))])
    monkeypatch.setattr("cire_harness.cli.get_provider", lambda spec: fake)
    result = runner.invoke(app, ["run", "hello", "--yes"])
    assert result.exit_code == 0
    assert result.output.strip() == "hi there"


def test_run_reports_provider_error():
    result = runner.invoke(app, ["run", "x", "--provider", "bogus"])
    assert result.exit_code == 1
    assert "error:" in result.output


def test_mcp_add_list_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(
        app, ["mcp", "add", "gh", "--env", "GITHUB_TOKEN", "--trusted", "--", "npx", "-y", "srv"]
    )
    assert result.exit_code == 0, result.output
    assert "GITHUB_TOKEN" in result.output
    assert runner.invoke(app, ["mcp", "add", "r", "--url", "http://h/mcp"]).exit_code == 0
    listed = runner.invoke(app, ["mcp", "list"]).output
    assert "gh: npx -y srv  [env=GITHUB_TOKEN trusted]" in listed
    assert "r: http://h/mcp" in listed
    assert (tmp_path / ".cire" / "config.toml").exists()
    assert runner.invoke(app, ["mcp", "remove", "gh"]).exit_code == 0
    assert "gh" not in runner.invoke(app, ["mcp", "list"]).output
    assert runner.invoke(app, ["mcp", "remove", "gh"]).exit_code == 1


def test_mcp_add_rejects_env_values_and_missing_transport(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["mcp", "add", "x", "--env", "TOKEN=abc", "--", "cmd"])
    assert result.exit_code == 1
    assert "never a value" in result.output
    assert runner.invoke(app, ["mcp", "add", "x"]).exit_code == 1


def test_role_set_list_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert runner.invoke(app, ["role", "set", "executor", "ollama:llama3.1"]).exit_code == 0
    assert runner.invoke(app, ["role", "set", "boss", "ollama:x"]).exit_code == 1
    assert runner.invoke(app, ["role", "set", "planner", "nonsense"]).exit_code == 1
    listed = runner.invoke(app, ["role", "list"]).output
    assert "executor: ollama:llama3.1" in listed and "planner: (unset)" in listed
    assert runner.invoke(app, ["role", "unset", "executor"]).exit_code == 0
    assert runner.invoke(app, ["role", "unset", "executor"]).exit_code == 1


def test_run_uses_planner_role_and_registers_delegate(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(app, ["role", "set", "planner", "ollama:big"])
    runner.invoke(app, ["role", "set", "executor", "ollama:small"])
    fake = FakeProvider([Response(message=Message(role="assistant", content="hi there"))])
    seen = []
    monkeypatch.setattr("cire_harness.cli.get_provider", lambda spec: seen.append(spec) or fake)
    result = runner.invoke(app, ["run", "hello", "--yes"])
    assert result.exit_code == 0, result.output
    assert seen == ["ollama:big", "ollama:small"]
    assert "delegate" in [t.name for t in fake.calls[0][1]]


def test_run_records_calls_and_stats_prints_them(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    fake = FakeProvider(
        [
            Response(
                message=Message(role="assistant", content="hi"), usage=Usage(input_tokens=1_000_000)
            )
        ]
    )
    monkeypatch.setattr("cire_harness.cli.get_provider", lambda spec: fake)
    assert runner.invoke(app, ["run", "hello", "--yes"]).exit_code == 0
    out = runner.invoke(app, ["stats"]).output
    assert "planner" in out and "fake-model" in out
    assert "unknown prices" in out
    (tmp_path / ".cire" / "config.toml").write_text(
        '[prices."fake-model"]\ninput = 2.0\noutput = 1.0\n'
    )
    out = runner.invoke(app, ["stats"]).output
    assert "total estimated cost: 2.0000 usd" in out
    assert runner.invoke(app, ["stats", "-s", "nope"]).output.strip() == "no recorded calls"


def test_bench_run_writes_report(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    fixture = tmp_path / "tasks" / "demo" / "repo"
    fixture.mkdir(parents=True)
    (fixture / "note.txt").write_text("todo\n")
    (tmp_path / "tasks" / "demo" / "task.toml").write_text(
        'prompt = "flip it"\nacceptance = ["grep -qx done note.txt"]\n'
    )
    write = ToolCall(id="w", name="write_file", arguments={"path": "note.txt", "content": "done\n"})
    monkeypatch.setattr(
        "cire_harness.cli.get_provider",
        lambda spec: FakeProvider(
            [
                Response(message=Message(role="assistant", tool_calls=[write])),
                Response(message=Message(role="assistant", content="ok")),
            ]
        ),
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "bench",
            "run",
            "--baseline",
            "fake:x",
            "--modes",
            "single",
            "--tasks",
            "tasks",
            "--out",
            "out/B.md",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "demo [single] run 1/1 ... ok" in result.output
    assert "| demo | single | 1/1 |" in (tmp_path / "out" / "B.md").read_text()
    assert list((tmp_path / "benchmarks" / "results").glob("*.json"))
    (tmp_path / "out" / "B.md").unlink()
    assert runner.invoke(app, ["bench", "report", "--out", "out/B.md"]).exit_code == 0
    assert "| demo | single | 1/1 |" in (tmp_path / "out" / "B.md").read_text()
    result = runner.invoke(app, ["bench", "run", "--baseline", "fake:x", "--tasks", "tasks"])
    assert result.exit_code == 1 and "split mode needs" in result.output
