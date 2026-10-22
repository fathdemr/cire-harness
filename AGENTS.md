# cire-harness

Multi-provider CLI agent harness in Python. A planner model plans and verifies; cheaper executor models do the work. Context is stored in a local SQLite database instead of living entirely in the prompt.

## Hard rules
- No code comments of any kind: no inline comments, no docstrings, no commented-out code.
- Commit messages: one short imperative line, no body unless essential, no emoji, no trailers.
- The word "claude" (any casing) must never appear in a commit message or a branch name. No Co-Authored-By or "Generated with" lines.
- Branch names: type/short-topic, for example feat/provider-layer.
- Never commit secrets. API keys come from environment variables only.

## Stack
- Python 3.12, uv, src layout (src/cire_harness/), console command `cire`
- Typer (CLI), Textual + Rich (TUI), httpx, pydantic, sqlite3 with FTS5, official mcp Python SDK
- pytest, ruff, GitHub Actions CI

## Working agreement
- Follow docs/PLAN.md phase by phase. One phase per session. Stop at the phase exit criteria and report.
- Before coding a phase, propose a short design and wait for approval.
- Small commits, one logical change each. Run `uv run ruff check . && uv run pytest` before every commit.
- Keep dependencies minimal and justify any new one.
- Small, typed, testable modules. All model calls go through the Provider interface; tests use a fake provider.

## Commands
- uv sync
- uv run cire
- uv run pytest
- uv run ruff check .