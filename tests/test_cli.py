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
