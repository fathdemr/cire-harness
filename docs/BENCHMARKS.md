# Benchmarks

Modes: **single** runs one model with all tools. **split** runs the planner with the `delegate` tool and a cheaper executor doing the file work in a fresh context. Success is decided only by each task's acceptance commands.

Cost is estimated from the price table in `cire_harness/telemetry.py` (USD per million tokens); Ollama counts as free. A `?` means a model without a known price. Token counts in split mode add planner and executor together.

## 2026-10-29 15:35 at commit `ae3e1cb`

| Role | Model |
| --- | --- |
| baseline (single) | `bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| planner (split) | `bedrock:openai.gpt-oss-120b-1:0` |
| executor (split) | `ollama:llama3.1` |

| Task | Mode | Passed | Avg cost (USD) | Avg tokens in / out | Avg seconds |
| --- | --- | --- | --- | --- | --- |
| add-cli-flag | single | 1/1 | 0.0556 | 13064 / 1092 | 22 |
| add-cli-flag | split | 1/1 | 0.0047 | 28187 / 2209 | 47 |
| add-tests | single | 1/1 | 0.0709 | 14882 / 1750 | 27 |
| add-tests | split | 1/1 | 0.0062 | 34130 / 3870 | 81 |
| fix-failing-test | single | 1/1 | 0.0470 | 12041 / 726 | 18 |
| fix-failing-test | split | 1/1 | 0.0024 | 15210 / 1134 | 27 |
| rename-across-files | single | 1/1 | 0.0725 | 16451 / 1541 | 25 |
| rename-across-files | split | 1/1 | 0.0013 | 11839 / 965 | 28 |
| write-module-from-spec | single | 1/1 | 0.0578 | 13678 / 1118 | 22 |
| write-module-from-spec | split | 1/1 | 0.0034 | 6815 / 3968 | 30 |
| **all** | single | 5/5 | 0.0608 | 14023 / 1245 | 23 |
| **all** | split | 5/5 | 0.0036 | 19236 / 2429 | 42 |

```
uv run cire bench run --baseline bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0 --repeat 1
```
