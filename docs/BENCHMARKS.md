# Benchmarks

Modes: **single** runs one model with all tools. **split** runs the planner with the `delegate` tool and a cheaper executor doing the file work in a fresh context. Success is decided only by each task's acceptance commands.

Cost is estimated from the price table in `cire_harness/telemetry.py` (USD per million tokens); Ollama counts as free. A `?` means a model without a known price. Token counts in split mode add planner and executor together.

## 2026-10-29 15:52 at commit `1b984ff`

| Role | Model |
| --- | --- |
| baseline (single) | `bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| planner (split) | `bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| executor (split) | `ollama:llama3.1` |

| Task | Mode | Passed | Avg cost (USD) | Avg tokens in / out | Avg seconds |
| --- | --- | --- | --- | --- | --- |
| add-cli-flag | single | 1/1 | 0.0603 | 13550 / 1307 | 24 |
| add-cli-flag | split | 1/1 | 0.0844 | 70109 / 4405 | 300 |
| add-tests | single | 1/1 | 0.0525 | 10533 / 1394 | 21 |
| add-tests | split | 1/1 | 0.1282 | 47218 / 4452 | 165 |
| fix-failing-test | single | 1/1 | 0.0457 | 11939 / 658 | 16 |
| fix-failing-test | split | 1/1 | 0.0778 | 39305 / 3103 | 138 |
| rename-across-files | single | 1/1 | 0.0689 | 16087 / 1374 | 24 |
| rename-across-files | split | 1/1 | 0.0474 | 15927 / 1314 | 40 |
| write-module-from-spec | single | 1/1 | 0.0582 | 13862 / 1106 | 22 |
| write-module-from-spec | split | 1/1 | 0.0998 | 33429 / 2522 | 90 |
| **all** | single | 5/5 | 0.0571 | 13194 / 1168 | 21 |
| **all** | split | 5/5 | 0.0875 | 41198 / 3159 | 147 |

```
uv run cire bench run --baseline bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0 --repeat 1
```

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
