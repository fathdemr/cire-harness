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
        assert set(by_name) == {"echo.echo", "echo.fail"}
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
