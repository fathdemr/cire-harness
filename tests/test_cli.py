from typer.testing import CliRunner

from cire_harness import __version__
from cire_harness.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"cire {__version__}"
