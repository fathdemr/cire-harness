import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def echo(text: str, times: int = 1) -> str:
    return text * times


@server.tool()
def secret() -> str:
    return os.environ.get("ECHO_SECRET", "unset")


@server.tool()
def fail() -> str:
    raise ValueError("boom")


if __name__ == "__main__":
    server.run()
