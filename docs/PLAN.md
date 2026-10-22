# cire-harness plan

Goal: a working, portfolio-quality CLI agent harness with a chat TUI, multi-provider support (including local models), MCP tools, SQLite-backed context management, and planner/executor routing with cost measurement. Every release must run and be demoable.

## Layout
src/cire_harness/
  cli.py            Typer entry, command `cire`
  config.py         TOML config, roles, providers
  telemetry.py      per-call usage and cost records
  tui/              Textual app, slash commands
  agent/            loop, permissions, prompts
  providers/        base, anthropic, openai_compat (OpenAI, Ollama, others via base_url)
  tools/            read, write, edit, bash, grep, glob
  mcp/              client manager, tool adapter
  context/          store, masking, compactor, retrieval
  orchestration/    spec, planner, executor, escalation
tests/

## Design decisions
- Providers: own thin Provider interface with normalized Message, ToolCall, Usage types. Two real adapters: Anthropic Messages and OpenAI-compatible. Ollama uses the OpenAI-compatible adapter at its /v1 endpoint. Small local models get a prompt-based tool-call fallback because native tool calling is unreliable.
- Roles in config: planner, executor, compactor. Each maps to provider:model. The compactor may be a local model.
- Context: the model only sees the prompt. SQLite is an external store. Large tool outputs are written to the DB and replaced in the prompt by a short summary and an id. A recall tool retrieves them. FTS5 searches past messages and tool results. Compaction triggers at a token threshold and writes a summary row.
- Planner/executor: the planner writes a frozen spec (goal, files, constraints, acceptance commands, budget). The executor runs in a fresh small context with limited tools and returns a short report and diff. Verification is deterministic first (tests, lint, diff size). Escalate to the planner only on failure, passing the report, not the history.
- Measurement: every model call is recorded (role, provider, model, input, output, cached tokens, estimated cost, duration). `cire stats` shows totals.

## v0.1 core
Phase 0 setup
- uv project, src layout, pyproject with `cire` script, ruff, pytest, CI workflow, .gitignore, MIT license, minimal README
- Exit: `uv run cire --version` works, CI green

Phase 1 providers
- Normalized types, Anthropic adapter, OpenAI-compatible adapter, streaming, usage recording, prompt-based tool-call fallback, fake provider for tests
- Exit: the same conversation runs on Anthropic, OpenAI-compatible cloud, and Ollama

Phase 2 agent loop and tools
- Loop with tool execution, read/write/edit/bash/grep/glob, permission prompts for risky commands, tests with the fake provider
- Exit: agent can read a repo, edit a file, and run tests end to end

Phase 3 TUI and sessions
- Textual chat screen with streaming, slash commands (/model, /compact, /sessions, /stats), session save and restore
- Exit: usable daily as a basic coding agent

## v0.2 context and MCP
Phase 4 SQLite context
- Schema: sessions, messages, tool_results, summaries, FTS index. Masking, recall tool, threshold compaction, optional local compactor
- Exit: long session stays under a token budget with measurable reduction

Phase 5 MCP
- Official Python SDK client, stdio and Streamable HTTP, config file, lazy tool loading, permissions for MCP tools
- Exit: at least two real MCP servers usable from the TUI

## v0.3 orchestration
Phase 6 planner/executor
- delegate tool, spec schema, executor loop, deterministic verification, escalation path, role config
- Exit: a multi-file task completes with planner and executor on different models

Phase 7 measurement
- Benchmark set of small repo tasks, single-model baseline vs planner/executor, cost and success table in the README
- Exit: reproducible numbers in docs/BENCHMARKS.md

## Polish
- Terminal demo recording at the top of the README, architecture diagram, design rationale section, example config, one-command install via uv tool, CI badge
- Optional last step: publish to PyPI with trusted publishing, separate build and publish jobs