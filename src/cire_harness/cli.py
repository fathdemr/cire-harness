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

app = typer.Typer(
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="Multi-provider coding agent: a planner model plans and verifies, cheaper executors "
    "do the work, context lives in a local SQLite store.",
    epilog="Examples:\n\n"
    "  cire chat                                  chat TUI\n\n"
    "  cire run 'list the python files' -y        one-shot task\n\n"
    "  cire role set executor ollama:llama3.1     local executor\n\n"
    "  cire mcp add fs -- npx -y @modelcontextprotocol/server-filesystem .\n\n"
    "Keys are read from the environment only: ANTHROPIC_API_KEY, OPENAI_API_KEY, "
    "AWS_BEARER_TOKEN_BEDROCK with AWS_REGION.",
)
mcp_app = typer.Typer(no_args_is_help=True, help="Manage MCP servers in ~/.cire/config.toml")
app.add_typer(mcp_app, name="mcp")
role_app = typer.Typer(no_args_is_help=True, help="Map planner/executor roles to provider:model")
app.add_typer(role_app, name="role")
bench_app = typer.Typer(no_args_is_help=True, help="Run the benchmark task set")
app.add_typer(bench_app, name="bench")
RESULTS_DIR = Path("benchmarks/results")
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


@app.command(help="Run one task in the current directory and print the answer.")
def run(
    prompt: str = typer.Argument(..., help="What to do, in plain language"),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="kind:model, overrides the planner role"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve risky tools without asking"),
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


@app.command(help="Open the chat TUI. Type / to see slash commands, Esc stops a turn.")
def chat(
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="kind:model, overrides the planner role"
    ),
    session: str | None = typer.Option(
        None, "--session", "-s", help="Resume a saved session id (see /sessions)"
    ),
    budget: int = typer.Option(
        8000, "--budget", help="Approximate token budget before older messages are summarised"
    ),
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


@mcp_app.command(
    "add",
    help="Register an MCP server. Put the command after --, or give --url for Streamable HTTP.",
)
def mcp_add(
    name: str = typer.Argument(..., help="Short name, becomes the tool prefix: name_tool"),
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


@mcp_app.command("list", help="List registered MCP servers.")
def mcp_list() -> None:
    config = read_config()
    for name, server in config.mcp.items():
        target = server.url or " ".join([server.command, *server.args])
        flags = [f"env={','.join(server.env)}"] if server.env else []
        if server.trusted:
            flags.append("trusted")
        typer.echo(f"{name}: {target}" + (f"  [{' '.join(flags)}]" if flags else ""))


@mcp_app.command("remove", help="Remove an MCP server from the config.")
def mcp_remove(name: str = typer.Argument(..., help="Server name")) -> None:
    config = load_config()
    if name not in config.mcp:
        typer.echo(f"error: no server {name}", err=True)
        raise typer.Exit(1)
    del config.mcp[name]
    save_config(config)
    typer.echo(f"removed {name}")


@role_app.command(
    "set", help="Map a role to a model, for example: role set executor ollama:llama3.1"
)
def role_set(
    name: str = typer.Argument(..., help="planner, executor or compactor"),
    spec: str = typer.Argument(..., help="kind:model, kinds: anthropic, openai, ollama, bedrock"),
) -> None:
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


@role_app.command("list", help="Show which model each role uses.")
def role_list() -> None:
    config = read_config()
    for name in ROLES:
        typer.echo(f"{name}: {config.roles.get(name, '(unset)')}")


@role_app.command("unset", help="Remove a role mapping.")
def role_unset(name: str = typer.Argument(..., help="planner, executor or compactor")) -> None:
    config = read_config()
    if name not in config.roles:
        typer.echo(f"error: role {name} is not set", err=True)
        raise typer.Exit(1)
    del config.roles[name]
    save_config(config)
    typer.echo(f"unset {name}")


@app.command(help="Show recorded token usage and estimated cost per role and model.")
def stats(
    session: str | None = typer.Option(None, "--session", "-s", help="Limit to one session id"),
) -> None:
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


@bench_app.command(
    "run",
    help="Run every benchmark task in single and split mode and write docs/BENCHMARKS.md.",
)
def bench_run(
    baseline: str = typer.Option(..., "--baseline", help="provider:model for single mode"),
    planner: str | None = typer.Option(None, "--planner", help="defaults to the planner role"),
    executor: str | None = typer.Option(None, "--executor", help="defaults to the executor role"),
    repeat: int = typer.Option(1, "--repeat", min=1, help="Runs per task and mode"),
    tasks_dir: Annotated[Path, typer.Option("--tasks", help="Folder with task subfolders")] = Path(
        "benchmarks/tasks"
    ),
    only: Annotated[list[str] | None, typer.Option("--only", help="task name (repeatable)")] = None,
    out: Annotated[Path, typer.Option("--out", help="Markdown report path")] = Path(
        "docs/BENCHMARKS.md"
    ),
    modes: str = typer.Option("single,split", "--modes", help="Comma separated: single, split"),
) -> None:
    import sys

    from cire_harness.bench.report import save_results
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
    command = "uv run cire " + " ".join(sys.argv[1:])
    raw = save_results(results, RESULTS_DIR, models, command)
    write_report(out, config)
    typer.echo(f"wrote {raw} and {out}")


def write_report(out: Path, config) -> None:
    from cire_harness.bench.report import render_markdown

    prices = {k: v.model_dump() for k, v in config.prices.items()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(RESULTS_DIR, prices), encoding="utf-8")


@bench_app.command("report", help="Rebuild the markdown report from saved benchmark results.")
def bench_report(
    out: Annotated[Path, typer.Option("--out", help="Markdown report path")] = Path(
        "docs/BENCHMARKS.md"
    ),
) -> None:
    write_report(out, read_config())
    typer.echo(f"wrote {out}")
