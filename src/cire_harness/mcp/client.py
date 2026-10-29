import os
import re
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamable_http_client

from cire_harness.config import MCPServer
from cire_harness.providers.types import ToolSpec
from cire_harness.tools import Tool


class MCPManager:
    def __init__(self) -> None:
        self.stacks: list[AsyncExitStack] = []
        self.errors: dict[str, str] = {}
        self.closed = False

    async def connect(self, servers: dict[str, MCPServer]) -> list[Tool]:
        tools: list[Tool] = []
        for name, server in servers.items():
            try:
                tools += await self.connect_one(name, server)
            except FileNotFoundError:
                self.errors[name] = f"command not found: {server.command}"
            except Exception as exc:
                self.errors[name] = f"{type(exc).__name__}: {exc}"
        return tools

    async def connect_one(self, name: str, server: MCPServer) -> list[Tool]:
        stack = AsyncExitStack()
        try:
            if server.command:
                missing = [k for k in server.env if k not in os.environ]
                if missing:
                    raise ValueError(f"missing environment variable(s): {', '.join(missing)}")
                env = get_default_environment() | {k: os.environ[k] for k in server.env}
                params = StdioServerParameters(command=server.command, args=server.args, env=env)
                read, write = await stack.enter_async_context(stdio_client(params, sys.stderr))
            else:
                read, write, *_ = await stack.enter_async_context(
                    streamable_http_client(server.url)
                )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
        except BaseException:
            await stack.aclose()
            raise
        self.stacks.append(stack)
        return [self.adapt(name, session, t, server.trusted) for t in listed.tools]

    @staticmethod
    def adapt(server: str, session: ClientSession, tool: Any, trusted: bool) -> Tool:
        async def run(args: dict[str, Any]) -> str:
            result = await session.call_tool(tool.name, args)
            text = "\n".join(
                getattr(part, "text", "") for part in getattr(result, "content", [])
            ).strip()
            if getattr(result, "is_error", False):
                return f"error: {text}"
            return text

        spec = ToolSpec(
            name=re.sub(r"[^A-Za-z0-9_-]", "_", f"{server}_{tool.name}"),
            description=tool.description or "",
            parameters=tool.input_schema,
        )
        return Tool(spec, run, risky=not trusted)

    async def close(self) -> None:
        for stack in reversed(self.stacks):
            await stack.aclose()
        self.closed = True
