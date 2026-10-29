from typer.testing import CliRunner

from cire_harness import __version__
from cire_harness.cli import app
from cire_harness.providers.fake import FakeProvider
from cire_harness.providers.types import Message, Response

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
