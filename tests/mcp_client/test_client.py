import sys
from pathlib import Path

from cire_harness.config import MCPServer
from cire_harness.mcp.client import MCPManager

ECHO = MCPServer(command=sys.executable, args=[str(Path(__file__).parent / "echo_server.py")])


async def test_connect_adapts_tools_and_reports_failures():
    manager = MCPManager()
    tools = await manager.connect({"echo": ECHO, "bad": MCPServer(command="no-such-cmd-xyz")})
    try:
        by_name = {t.name: t for t in tools}
        assert set(by_name) == {"echo.echo", "echo.secret", "echo.fail"}
        assert by_name["echo.echo"].risky is True
        assert by_name["echo.echo"].spec.parameters["required"] == ["text"]
        assert await by_name["echo.echo"].run({"text": "ab", "times": 2}) == "abab"
        assert (await by_name["echo.fail"].run({})).startswith("error:")
        assert list(manager.errors) == ["bad"]
    finally:
        await manager.close()
    assert manager.closed


async def test_trusted_server_tools_are_not_risky():
    manager = MCPManager()
    tools = await manager.connect({"echo": ECHO.model_copy(update={"trusted": True})})
    try:
        assert all(not t.risky for t in tools)
    finally:
        await manager.close()


async def test_env_names_are_passed_through(monkeypatch):
    monkeypatch.setenv("ECHO_SECRET", "s3cret")
    manager = MCPManager()
    tools = await manager.connect({"echo": ECHO.model_copy(update={"env": ["ECHO_SECRET"]})})
    try:
        secret = next(t for t in tools if t.name == "echo.secret")
        assert await secret.run({}) == "s3cret"
    finally:
        await manager.close()


async def test_env_not_passed_unless_listed(monkeypatch):
    monkeypatch.setenv("ECHO_SECRET", "s3cret")
    manager = MCPManager()
    tools = await manager.connect({"echo": ECHO})
    try:
        secret = next(t for t in tools if t.name == "echo.secret")
        assert await secret.run({}) == "unset"
    finally:
        await manager.close()


async def test_missing_env_is_reported_not_fatal(monkeypatch):
    monkeypatch.delenv("NOPE_TOKEN", raising=False)
    manager = MCPManager()
    tools = await manager.connect({"echo": ECHO.model_copy(update={"env": ["NOPE_TOKEN"]})})
    await manager.close()
    assert tools == []
    assert "NOPE_TOKEN" in manager.errors["echo"]
