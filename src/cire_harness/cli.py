import asyncio
from datetime import datetime
from pathlib import Path

import typer

from cire_harness import __version__
from cire_harness.loop.loop import run_agent
from cire_harness.providers import ProviderError, get_provider
from cire_harness.providers.types import Message, ToolCall
from cire_harness.session import load_session
from cire_harness.tools import ToolRegistry
from cire_harness.tools.bash import bash_tools
from cire_harness.tools.fs import fs_tools
from cire_harness.tools.grep import grep_tools
from cire_harness.tui.app import ChatApp

app = typer.Typer(no_args_is_help=True)


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
) -> None:

    root = Path.cwd()
    registry = ToolRegistry(fs_tools(root) + bash_tools(root) + grep_tools(root))

    try:
        messages = load_session(session) if session else []
    except FileNotFoundError:
        typer.echo(f"error: no session {session}", err=True)
        raise typer.Exit(1) from None

    session_id = session or datetime.now().strftime("%Y%m%d-%H%M%S")

    try:
        ChatApp(get_provider(provider), registry, messages, session_id).run()
    except ProviderError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
