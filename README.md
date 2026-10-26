# cire-harness

[![M8ven Score](https://m8ven.ai/badge/mcp/fathdemr/cire-harness?variant=verified)](https://m8ven.ai/mcp/fathdemr/cire-harness?s=readme)

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

- Python TODO (version)
- An API key for at least one provider

## Installation

```bash
git clone https://github.com/fathdemr/cire-harness.git
cd cire-harness
pip install -e .
```

## Configuration

Set the keys for the providers you use:

```bash
export ANTHROPIC_API_KEY=your_key
export OPENAI_API_KEY=your_key
```

Keys are read from the environment at runtime and only sent to the matching provider.

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Anthropic models |
| `OPENAI_API_KEY` | OpenAI models |

## Usage

```bash
TODO: main command, e.g. cire-harness run "your task"
```

TODO: planner/executor model selection example.

## Project structure

```
TODO: short tree of the main modules
```

## Security

- No credentials are stored; keys are read from the environment.
- Context is stored locally in SQLite.
- Independent trust analysis: [M8ven report](https://m8ven.ai/mcp/fathdemr/cire-harness)

## Contributing

Issues and pull requests are welcome.

## License

TODO: license name (see `LICENSE`)
