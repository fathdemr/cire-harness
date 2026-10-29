import asyncio
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Annotated

import typer

from cire_harness import __version__
from cire_harness.config import ROLES, MCPServer, load_config, save_config
from cire_harness.context.recall import recall_tools
from cire_harness.context.store import ContextStore
from cire_harness.loop.loop import run_agent
from cire_harness.orchestration.delegate import delegate_tool
from cire_harness.providers import KINDS, ProviderError, get_provider
from cire_harness.providers.types import Message, ToolCall
from cire_harness.telemetry import Metered, estimate_cost
from cire_harness.tools import ToolRegistry
from cire_harness.tools.bash import bash_tools
from cire_harness.tools.fs import fs_tools
from cire_harness.tools.grep import grep_tools
from cire_harness.tui.app import ChatApp

app = typer.Typer(no_args_is_help=True)
mcp_app = typer.Typer(no_args_is_help=True, help="Manage MCP servers in ~/.cire/config.toml")
app.add_typer(mcp_app, name="mcp")
role_app = typer.Typer(no_args_is_help=True, help="Map planner/executor roles to provider:model")
app.add_typer(role_app, name="role")
bench_app = typer.Typer(no_args_is_help=True, help="Run the benchmark task set")
app.add_typer(bench_app, name="bench")
DEFAULT_PROVIDER = "ollama:llama3.1"


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


def read_config():
    try:
        return load_config()
    except ValueError as exc:
        typer.echo(f"error: bad config: {exc}", err=True)
        raise typer.Exit(1) from None


@app.command()
def run(
    prompt: str,
    provider: str | None = typer.Option(None, "--provider", "-p"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip permission prompts"),
) -> None:

    config = read_config()
    store = ContextStore()
    session_id = "run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path.cwd()
    registry = ToolRegistry(fs_tools(root) + grep_tools(root) + bash_tools(root))
    messages = [Message(role="user", content=prompt)]

    approve = always if yes else confirm

    def meter(spec: str, role: str):
        return Metered(get_provider(spec), role, partial(store.save_call, session_id))

    try:
        planner = meter(provider or config.roles.get("planner", DEFAULT_PROVIDER), "planner")
        if executor := config.roles.get("executor"):
            tool = delegate_tool(meter(executor, "executor"), root, approve)
            registry.tools[tool.name] = tool
        result = asyncio.run(run_agent(planner, registry, messages, approve))
        typer.echo(result)
    except ProviderError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None


@app.command()
def chat(
    provider: str | None = typer.Option(None, "--provider", "-p"),
    session: str | None = typer.Option(None, "--session", "-s"),
    budget: int = typer.Option(8000, "--budget", help="Token budget before compaction"),
) -> None:

    config = read_config()
    store = ContextStore()
    try:
        messages = store.load_messages(session) if session else []
    except KeyError:
        typer.echo(f"error: no session {session}", err=True)
        raise typer.Exit(1) from None

    session_id = session or datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path.cwd()
    registry = ToolRegistry(
        fs_tools(root) + bash_tools(root) + grep_tools(root) + recall_tools(store, session_id)
    )

    def meter(spec: str, role: str):
        return Metered(get_provider(spec), role, partial(store.save_call, session_id))

    try:
        planner = meter(provider or config.roles.get("planner", DEFAULT_PROVIDER), "planner")
        delegate = None
        if executor := config.roles.get("executor"):
            delegate = partial(delegate_tool, meter(executor, "executor"), root)
        ChatApp(planner, registry, messages, session_id, store, budget, config.mcp, delegate).run()
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
    config = read_config()
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


@role_app.command("set")
def role_set(name: str, spec: str) -> None:
    if name not in ROLES:
        typer.echo(f"error: unknown role {name!r}, expected one of {', '.join(ROLES)}", err=True)
        raise typer.Exit(1)
    kind, _, model = spec.partition(":")
    if kind not in KINDS or not model:
        typer.echo(
            f"error: spec must look like kind:model with kind in {', '.join(KINDS)}", err=True
        )
        raise typer.Exit(1)
    config = read_config()
    config.roles[name] = spec
    typer.echo(f"{name} = {spec} saved to {save_config(config)}")


@role_app.command("list")
def role_list() -> None:
    config = read_config()
    for name in ROLES:
        typer.echo(f"{name}: {config.roles.get(name, '(unset)')}")


@role_app.command("unset")
def role_unset(name: str) -> None:
    config = read_config()
    if name not in config.roles:
        typer.echo(f"error: role {name} is not set", err=True)
        raise typer.Exit(1)
    del config.roles[name]
    save_config(config)
    typer.echo(f"unset {name}")


@app.command()
def stats(session: str | None = typer.Option(None, "--session", "-s")) -> None:
    config = read_config()
    prices = {k: v.model_dump() for k, v in config.prices.items()}
    rows = ContextStore().call_totals(session)
    if not rows:
        typer.echo("no recorded calls")
        return
    typer.echo(
        f"{'role':<9}{'provider':<10}{'model':<44}{'calls':>6}{'in':>9}{'out':>8}{'cached':>8}{'secs':>8}{'usd':>9}"
    )
    total = 0.0
    unknown = False
    for role, provider, model, calls, tin, tout, tcached, secs in rows:
        cost = estimate_cost(provider, model, tin, tout, prices)
        if cost is None:
            unknown = True
            shown = "?"
        else:
            total += cost
            shown = f"{cost:.4f}"
        typer.echo(
            f"{role:<9}{provider:<10}{model[:43]:<44}{calls:>6}{tin:>9}{tout:>8}{tcached:>8}{secs:>8.1f}{shown:>9}"
        )
    note = " (+ unknown prices, add [prices] to config)" if unknown else ""
    typer.echo(f"total estimated cost: {total:.4f} usd{note}")


@bench_app.command("run")
def bench_run(
    baseline: str = typer.Option(..., "--baseline", help="provider:model for single mode"),
    planner: str | None = typer.Option(None, "--planner", help="defaults to the planner role"),
    executor: str | None = typer.Option(None, "--executor", help="defaults to the executor role"),
    repeat: int = typer.Option(1, "--repeat", min=1),
    tasks_dir: Annotated[Path, typer.Option("--tasks")] = Path("benchmarks/tasks"),
    only: Annotated[list[str] | None, typer.Option("--only", help="task name (repeatable)")] = None,
    out: Annotated[Path, typer.Option("--out")] = Path("docs/BENCHMARKS.md"),
    modes: str = typer.Option("single,split", "--modes"),
) -> None:
    import sys

    from cire_harness.bench.report import render_markdown, save_results
    from cire_harness.bench.runner import run_task
    from cire_harness.bench.tasks import load_tasks

    config = read_config()
    planner = planner or config.roles.get("planner")
    executor = executor or config.roles.get("executor")
    wanted = [m.strip() for m in modes.split(",") if m.strip()]
    if "split" in wanted and not (planner and executor):
        typer.echo(
            "error: split mode needs --planner and --executor (or roles in config)", err=True
        )
        raise typer.Exit(1)
    try:
        tasks = load_tasks(tasks_dir, only)
        for spec in filter(None, [baseline, planner, executor]):
            get_provider(spec)
    except (ValueError, ProviderError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None

    models = {"baseline (single)": baseline}
    if "split" in wanted:
        models.update({"planner (split)": planner, "executor (split)": executor})

    async def run_all():
        results = []
        for task in tasks:
            for mode in wanted:
                for i in range(repeat):
                    typer.echo(f"{task.name} [{mode}] run {i + 1}/{repeat} ... ", nl=False)
                    if mode == "single":
                        result = await run_task(task, "single", lambda: get_provider(baseline))
                    else:
                        result = await run_task(
                            task,
                            "split",
                            lambda: get_provider(planner),
                            lambda: get_provider(executor),
                        )
                    cost = result.cost({k: v.model_dump() for k, v in config.prices.items()})
                    typer.echo(
                        f"{'ok' if result.ok else 'FAIL'} {result.seconds:.0f}s "
                        f"cost={'?' if cost is None else f'{cost:.4f}'}"
                    )
                    results.append(result)
        return results

    results = asyncio.run(run_all())
    prices = {k: v.model_dump() for k, v in config.prices.items()}
    command = "uv run cire " + " ".join(sys.argv[1:])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(results, models, command, prices), encoding="utf-8")
    raw = save_results(results, Path("benchmarks/results"), models)
    typer.echo(f"wrote {out} and {raw}")
