# F7 — repo_map / compaction 7-day dogfood protocol

> Status: **ready to run** · NORTH-STAR F7 · decision due end of week (ON or OFF — no limbo)

## Goal

Decide whether `AGENT_LAB_REPO_MAP` and `AGENT_LAB_COMPACT_TOOL_OUTPUT` stay **default ON** (or profile-owned ON) after a bounded real-session trial. Mock/self-eval already exist; F7 is **live quality**, not more unit tests.

## Flags

| Flag | Default | Dogfood week |
|------|---------|--------------|
| `AGENT_LAB_REPO_MAP` | OFF | **ON** (`=1`) |
| `AGENT_LAB_REPO_MAP_TOKENS` | `1024` | keep or `1536` if maps feel thin |
| `AGENT_LAB_COMPACT_TOOL_OUTPUT` | OFF | **ON** (`=1`) |
| `AGENT_LAB_COMPACT_TOOL_CHARS` | `2000` | keep |

Enable for the API process (and any child agents inherit via server env):

```bash
# shell before `make dev` / API start
export AGENT_LAB_REPO_MAP=1
export AGENT_LAB_COMPACT_TOOL_OUTPUT=1
make dev
```

Or one-shot:

```bash
make f7-dogfood-env   # prints export lines
eval "$(make f7-dogfood-env)"
make dev
```

Use **supervisor** preset for real work (same as S1 dogfood).

## Duration & sample

| Gate | Threshold |
|------|-----------|
| Calendar | **7 days** from start date (record below) |
| Sessions | **≥ 10** sessions with at least one agent turn and `last_context_bundle` |
| Repo-map coverage | **≥ 70%** of those sessions have `repo_layer == "repo_map"` |
| Budget health | median `budget_pct` **&lt; 90** (not stuck in critical) |
| Compaction Human | checklist pass on **≥ 5** sessions (see below) |

**Context hit rate (proxy, no LLM judge):** share of instrumented sessions where repo-map was active and non-empty context was recorded (`repo_layer=repo_map` and `last_context_bundle` present). Target **≥ 70%**.

## Daily checklist (Human)

For each working session, note in one line (session id optional):

```text
date · session · repo_map useful? (y/n/?) · compaction ok? (y/n/garbled) · notes
```

Compaction **ok** means: long tool/fence output was shortened without losing the ability to continue the task; **garbled** means you needed the full log from `chat.jsonl` and the truncation hurt.

## Report

```bash
make f7-dogfood-report
# optional:
make f7-dogfood-report SESSIONS=sessions DAYS=7
make f7-dogfood-report JSON=1
```

Reads `sessions/*/run.json` → `last_context_bundle` / `context_quality_log` (stamped when agents build context).

## Decision (end of day 7)

Fill and commit (or paste into NORTH-STAR §3.1 note):

| Field | Value |
|-------|--------|
| Start date | YYYY-MM-DD |
| End date | YYYY-MM-DD |
| Sessions (n) | |
| repo_map coverage % | |
| median budget_pct | |
| Compaction Human pass (x/5+) | |
| **Decision** | **ON** / **OFF** |
| Rationale (1–2 sentences) | |

### If ON

- Keep env defaults or set profile `owns`/`flags` so `thorough` (and optionally `balanced`) enable both flags.
- Update NORTH-STAR gauge: context quality D2→D3.

### If OFF

- Leave flags default OFF; document why in this file’s Decision table.
- Do **not** leave “maybe later” without a date — F7 forbids limbo.

## Out of scope

- Live LLM judge (optional if credits allow; not required for decision)
- Multi-language repo-map
- Changing compaction algorithm

## Code SSOT

| Piece | Path |
|-------|------|
| Repo-map | `src/agent_lab/repo_map.py`, `repo_map_core.py` |
| Compaction | `src/agent_lab/room/context/message_trim.py` |
| Metrics stamp | `context/bundle.py` → `last_context_bundle`, `context_quality_log` |
| Report | `scripts/f7_dogfood_report.py` |
