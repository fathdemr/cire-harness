import json
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from cire_harness.bench.runner import RunResult

HEADER = [
    "# Benchmarks",
    "",
    "Modes: **single** runs one model with all tools. **split** runs the planner with the "
    "`delegate` tool and a cheaper executor doing the file work in a fresh context. Success is "
    "decided only by each task's acceptance commands.",
    "",
    "Cost is estimated from the price table in `cire_harness/telemetry.py` (USD per million "
    "tokens); Ollama counts as free. A `?` means a model without a known price. Token counts in "
    "split mode add planner and executor together.",
    "",
]


def fmt_cost(value: float | None) -> str:
    return "?" if value is None else f"{value:.4f}"


def summarize(results: list[RunResult], prices=None) -> list[dict]:
    groups: dict[tuple[str, str], list[RunResult]] = defaultdict(list)
    for r in results:
        groups[(r.task, r.mode)].append(r)
    rows = []
    for (task, mode), runs in sorted(groups.items()):
        costs = [r.cost(prices) for r in runs]
        rows.append(
            {
                "task": task,
                "mode": mode,
                "runs": len(runs),
                "passed": sum(r.ok for r in runs),
                "avg_cost": None if any(c is None for c in costs) else sum(costs) / len(runs),
                "avg_in": sum(r.tokens()[0] for r in runs) / len(runs),
                "avg_out": sum(r.tokens()[1] for r in runs) / len(runs),
                "avg_seconds": sum(r.seconds for r in runs) / len(runs),
            }
        )
    return rows


def totals(rows: list[dict]) -> list[dict]:
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)
    out = []
    for mode, group in sorted(by_mode.items()):
        runs = sum(r["runs"] for r in group)
        costs = [r["avg_cost"] for r in group]
        out.append(
            {
                "task": "**all**",
                "mode": mode,
                "runs": runs,
                "passed": sum(r["passed"] for r in group),
                "avg_cost": None
                if any(c is None for c in costs)
                else sum(c * r["runs"] for c, r in zip(costs, group, strict=True)) / runs,
                "avg_in": sum(r["avg_in"] * r["runs"] for r in group) / runs,
                "avg_out": sum(r["avg_out"] * r["runs"] for r in group) / runs,
                "avg_seconds": sum(r["avg_seconds"] * r["runs"] for r in group) / runs,
            }
        )
    return out


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def render_section(payload: dict, prices=None) -> list[str]:
    results = [RunResult.model_validate(r) for r in payload["results"]]
    rows = summarize(results, prices)
    lines = [
        f"## {payload['generated']} at commit `{payload['commit']}`",
        "",
        "| Role | Model |",
        "| --- | --- |",
        *[f"| {role} | `{spec}` |" for role, spec in payload["models"].items()],
        "",
        "| Task | Mode | Passed | Avg cost (USD) | Avg tokens in / out | Avg seconds |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows + totals(rows):
        lines.append(
            f"| {row['task']} | {row['mode']} | {row['passed']}/{row['runs']} | "
            f"{fmt_cost(row['avg_cost'])} | {row['avg_in']:.0f} / {row['avg_out']:.0f} | "
            f"{row['avg_seconds']:.0f} |"
        )
    lines += ["", "```", payload["command"], "```", ""]
    return lines


def render_markdown(results_dir: Path, prices=None) -> str:
    files = sorted(results_dir.glob("*.json"), reverse=True)
    lines = list(HEADER)
    for path in files:
        lines += render_section(json.loads(path.read_text(encoding="utf-8")), prices)
    if not files:
        lines.append("No results yet. Run `cire bench run`.")
    return "\n".join(lines)


def save_results(
    results: list[RunResult], folder: Path, models: dict[str, str], command: str
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = folder / f"{now:%Y%m%d-%H%M%S}.json"
    payload = {
        "generated": f"{now:%Y-%m-%d %H:%M}",
        "commit": git_commit(),
        "command": command,
        "models": models,
        "results": [r.model_dump() for r in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
