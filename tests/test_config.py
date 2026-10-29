import pytest
from pydantic import ValidationError

from cire_harness.config import load_config


def test_missing_file_gives_empty_config(tmp_path):
    assert load_config(tmp_path / "nope.toml").mcp == {}


def test_parses_stdio_and_http_servers(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[mcp.fs]\ncommand = "npx"\nargs = ["-y", "server-fs"]\ntrusted = true\n'
        '[mcp.remote]\nurl = "http://localhost:8000/mcp"\n'
    )
    config = load_config(path)
    assert config.mcp["fs"].args == ["-y", "server-fs"]
    assert config.mcp["fs"].trusted is True
    assert config.mcp["remote"].url == "http://localhost:8000/mcp"
    assert config.mcp["remote"].trusted is False


@pytest.mark.parametrize("body", ["[mcp.x]\n", '[mcp.x]\ncommand = "a"\nurl = "b"\n'])
def test_server_needs_exactly_one_transport(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body)
    with pytest.raises(ValidationError):
        load_config(path)
