# RFC: Docker execute sandbox (Harness P0)

Status: draft · Room session `2026-06-30` harness engineering thread

## Problem

Execute lane uses git worktree + host subprocess. Network, dependency installs, and env side-effects are not isolated. Kimi Work and Claude agreed this is the largest gap vs SWE-bench / OpenHands / Harbor.

`sandbox_policy.py` records `sandbox_intent="docker"` when `AGENT_LAB_SANDBOX_RUNTIME=docker`, but **no container is launched** (explicit DEFERRED).

## Goals (PoC)

1. Run plan execute steps inside a disposable container with repo worktree mounted read-write.
2. Block outbound network by default; allowlist for package mirrors if needed.
3. Record sandbox runtime + exit metadata on `run.json` without changing Human Oracle gate.

## Non-goals (PoC)

- Full SWE-bench task corpus replay
- Multi-tenant cloud workers
- Replacing worktree merge flow

## Prerequisites (Claude AMEND)

1. **eval_harness wired** — pytest JUnit → `result_map` → `score_instance` ([`eval_harness_ingest.py`](../src/agent_lab/eval_harness_ingest.py))
2. **Task corpus** — [`benchmarks/task_corpus.v1.json`](../benchmarks/task_corpus.v1.json) (not `sessions/_benchmark/` FSM fixtures)

## Proposed shape

```text
execute_lane
  └─ sandbox_policy.resolve_runtime()
       ├─ worktree (default, current)
       └─ docker (PoC)
            ├─ image: agent-lab-exec:latest (Dockerfile in docker/exec-sandbox/)
            ├─ mount: worktree → /work
            ├─ cwd: /work
            └─ env: minimal allowlist via subprocess_env()
```

## Rollout

| Phase | Scope |
|-------|--------|
| 0 | RFC + stub launcher that validates docker CLI present |
| 1 | Single-step shell execute in container, merge unchanged |
| 2 | Network policy + artifact export |
| 3 | Parallel eval workers (`AGENT_LAB_MAX_WORKERS`) |

## Open questions

- Kimi Work bridge / daimon inside container vs host-only
- macOS Docker file watch vs worktree sync latency
- How Human gate surfaces sandbox logs in Mission OS UI
