# cire-harness

[![M8ven Score](https://m8ven.ai/badge/mcp/fathdemr-cire-harness-spfj31?v=037b2209a018f964b0704446e4ef47ba)](https://m8ven.ai/mcp/fathdemr-cire-harness-spfj31?s=readme)

A multi-provider CLI agent harness. A strong **planner** model plans the work and verifies the results, while cheaper **executor** models do the heavy lifting. All context lives in a local SQLite store.

## Why

- **Lower cost:** expensive models only plan and verify, cheap models execute.
- **Multi-provider:** mix Anthropic and OpenAI models in a single run.
- **Local-first:** context is stored in SQLite on your machine, nothing is sent anywhere except to the model providers you configure.

## How it works

```
task -> planner (plan) -> executors (do the steps) -> planner (verify) -> result
                               |
                         local SQLite context
```

1. The planner breaks the task into steps.
2. Executor models run each step.
3. The planner verifies the output and requests fixes if needed.
4. Plans, steps and results are persisted in SQLite.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- At least one model: an Anthropic or OpenAI API key, or a local [Ollama](https://ollama.com) install

## Installation

```bash
git clone https://github.com/fathdemr/cire-harness.git
cd cire-harness
uv sync
uv run cire --version
```

## Configuration

### API keys live in your shell, never in a file

cire reads provider keys from environment variables at runtime. There is no key field anywhere in its config, and nothing you type is written to disk except your chat history.

```bash
export ANTHROPIC_API_KEY=your_key
export OPENAI_API_KEY=your_key
```

| Variable | Used for |
| --- | --- |
| `ANTHROPIC_API_KEY` | `anthropic:<model>` providers |
| `OPENAI_API_KEY` | `openai:<model>` providers |

Ollama needs no key. Each key is sent only to its own provider.

### MCP servers

MCP servers are registered in `~/.cire/config.toml`. Use the CLI instead of editing the file:

```bash
# a local server started as a subprocess (everything after -- is the command)
uv run cire mcp add fs -- npx -y @modelcontextprotocol/server-filesystem .

# a server that needs a secret: name the variable, set its value in your shell
export GITHUB_TOKEN=ghp_...
uv run cire mcp add github --env GITHUB_TOKEN -- npx -y @modelcontextprotocol/server-github

# a remote Streamable HTTP server
uv run cire mcp add remote --url https://example.com/mcp

# skip the confirmation prompt for a server you trust
uv run cire mcp add fetch --trusted -- uvx mcp-server-fetch

uv run cire mcp list
uv run cire mcp remove remote
```

`--env` takes variable **names** only. The config stores the name, the value is read from your shell when the server starts, and cire refuses to save anything that looks like `NAME=value`. Subprocess servers start with a minimal environment, so a variable reaches a server only if you list it.

Tools from a server appear as `<server>.<tool>`, for example `fs.read_file`. Every MCP tool asks for confirmation before it runs unless the server was added with `--trusted`. Type `/tools` in the chat to see what is loaded.

The resulting file looks like this:

```toml
[mcp."github"]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = ["GITHUB_TOKEN"]
```

## Usage

```bash
uv run cire chat                          # chat TUI, default provider ollama:llama3.1
uv run cire chat -p anthropic:claude-sonnet-4-5
uv run cire chat -s 20261029-140045      # resume a session
uv run cire run "list the python files" --yes
```

Slash commands in the chat: `/model`, `/sessions`, `/stats`, `/tools`, `/compact`. Press `Esc` to stop a running turn.

Large tool outputs are stored in SQLite and replaced in the prompt by a short preview and an id. The model fetches them back with the `recall` tool. When the context passes the token budget (`--budget`, default 8000) older messages are summarised automatically.

## Project structure

```
src/cire_harness/
  cli.py        cire run / chat / mcp
  config.py     ~/.cire/config.toml
  providers/    Anthropic, OpenAI-compatible, Ollama, prompt-based tool fallback
  loop/         agent loop and tool execution
  tools/        read, write, edit, bash, grep
  mcp/          MCP client and tool adapter
  context/      SQLite store, masking, recall, compaction
  tui/          Textual chat app
```

## Security

- **No stored credentials.** Provider keys and MCP secrets are read from environment variables when needed. The config file holds variable names, never values.
- **Minimal environment for MCP servers.** A subprocess server sees only `PATH`, `HOME` and the variables you listed with `--env`.
- **Confirmation for risky tools.** Shell commands, file writes and all MCP tools prompt before running unless you opt out per server.
- **Sandboxed file tools.** Built-in file and grep tools refuse paths outside the working directory.
- **Local context.** Sessions and tool results stay in `~/.cire/cire.db` on your machine and go only to the provider you chose.
- Independent trust analysis: [M8ven report](https://m8ven.ai/mcp/fathdemr/cire-harness)

## Contributing

Issues and pull requests are welcome.

## License

TODO: license name (see `LICENSE`)
