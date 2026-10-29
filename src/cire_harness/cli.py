import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from cire_harness import __version__
from cire_harness.config import MCPServer, load_config, save_config
from cire_harness.context.recall import recall_tools
from cire_harness.context.store import ContextStore
from cire_harness.loop.loop import run_agent
from cire_harness.providers import ProviderError, get_provider
from cire_harness.providers.types import Message, ToolCall
from cire_harness.tools import ToolRegistry
from cire_harness.tools.bash import bash_tools
from cire_harness.tools.fs import fs_tools
from cire_harness.tools.grep import grep_tools
from cire_harness.tui.app import ChatApp

app = typer.Typer(no_args_is_help=True)
mcp_app = typer.Typer(no_args_is_help=True, help="Manage MCP servers in ~/.cire/config.toml")
app.add_typer(mcp_app, name="mcp")


async def always(call: ToolCall) -> bool:
    return True


async def confirm(call: ToolCall) -> bool:
    return typer.confirm(f"run {call.name} {call.arguments}?")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cire {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=version_callback, is_eager=True, help="Show version"
    ),
) -> None:
    pass


@app.command()
def run(
    prompt: str,
    provider: str = typer.Option("ollama:llama3.1", "--provider", "-p"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip permission prompts"),
) -> None:

    root = Path.cwd()
    registry = ToolRegistry(fs_tools(root) + grep_tools(root) + bash_tools(root))
    messages = [Message(role="user", content=prompt)]

    approve = always if yes else confirm

    try:
        result = asyncio.run(run_agent(get_provider(provider), registry, messages, approve))
        typer.echo(result)
    except ProviderError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None


@app.command()
def chat(
    provider: str = typer.Option("ollama:llama3.1", "--provider", "-p"),
    session: str | None = typer.Option(None, "--session", "-s"),
    budget: int = typer.Option(8000, "--budget", help="Token budget before compaction"),
) -> None:

    store = ContextStore()
    try:
        config = load_config()
        messages = store.load_messages(session) if session else []
    except ValueError as exc:
        typer.echo(f"error: bad config: {exc}", err=True)
        raise typer.Exit(1) from None
    except KeyError:
        typer.echo(f"error: no session {session}", err=True)
        raise typer.Exit(1) from None

    session_id = session or datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path.cwd()
    registry = ToolRegistry(
        fs_tools(root) + bash_tools(root) + grep_tools(root) + recall_tools(store, session_id)
    )

    try:
        ChatApp(
            get_provider(provider), registry, messages, session_id, store, budget, config.mcp
        ).run()
    except ProviderError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None


@mcp_app.command("add")
def mcp_add(
    name: str,
    command: Annotated[list[str] | None, typer.Argument(help="Command and args, after --")] = None,
    url: str = typer.Option("", "--url", help="Streamable HTTP endpoint instead of a command"),
    env: Annotated[
        list[str] | None,
        typer.Option("--env", "-e", help="Environment variable NAME to pass through (repeatable)"),
    ] = None,
    trusted: bool = typer.Option(False, "--trusted", help="Skip confirmation for its tools"),
) -> None:
    try:
        server = MCPServer(
            command=command[0] if command else "",
            args=command[1:] if command else [],
            url=url,
            env=env or [],
            trusted=trusted,
        )
        config = load_config()
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    config.mcp[name] = server
    path = save_config(config)
    typer.echo(f"added {name} to {path}")
    if env:
        typer.echo(f"make sure these are set in your shell: {' '.join(env)}")


@mcp_app.command("list")
def mcp_list() -> None:
    try:
        config = load_config()
    except ValueError as exc:
        typer.echo(f"error: bad config: {exc}", err=True)
        raise typer.Exit(1) from None
    for name, server in config.mcp.items():
        target = server.url or " ".join([server.command, *server.args])
        flags = [f"env={','.join(server.env)}"] if server.env else []
        if server.trusted:
            flags.append("trusted")
        typer.echo(f"{name}: {target}" + (f"  [{' '.join(flags)}]" if flags else ""))


@mcp_app.command("remove")
def mcp_remove(name: str) -> None:
    config = load_config()
    if name not in config.mcp:
        typer.echo(f"error: no server {name}", err=True)
        raise typer.Exit(1)
    del config.mcp[name]
    save_config(config)
    typer.echo(f"removed {name}")
