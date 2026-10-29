import asyncio
from asyncio.subprocess import PIPE, STDOUT
from pathlib import Path

from cire_harness.orchestration.spec import TaskSpec

TAIL_LINES = 15


async def verify(
    spec: TaskSpec, root: Path, touched: set[str], timeout: float = 120
) -> tuple[bool, str]:
    ok = True
    lines: list[str] = []
    if spec.files:
        outside = sorted(touched - set(spec.files))
        if outside:
            ok = False
            lines.append(f"touched files outside the spec: {', '.join(outside)}")
    if not spec.acceptance:
        lines.append("no acceptance commands given")
    for cmd in spec.acceptance:
        proc = await asyncio.create_subprocess_shell(cmd, cwd=root, stdout=PIPE, stderr=STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            ok = False
            lines.append(f"$ {cmd}\ntimed out after {timeout}s")
            continue
        tail = out.decode(errors="replace").strip().splitlines()[-TAIL_LINES:]
        status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
        ok = ok and proc.returncode == 0
        lines.append("\n".join([f"$ {cmd} -> {status}", *tail]))
    return ok, "\n".join(lines)
