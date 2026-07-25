# F7 — repo_map / compaction 7-day dogfood protocol

> Status: **closed (ON)** · decided 2026-07-25 · dogfood-track F7 ✅  
> **Almost-final:** sample gates PASS; Human usefulness checklist still thin — **revisit once more non-lift live sessions accumulate** (do not leave limbo; this ON is the close, revisit is a later review).  
> NORTH-STAR F7

## Goal

Decide whether `AGENT_LAB_REPO_MAP` and `AGENT_LAB_COMPACT_TOOL_OUTPUT` stay **default ON** (or profile-owned ON) after a bounded real-session trial. Mock/self-eval already exist; F7 is **live quality**, not more unit tests.

## Flags

| Flag | Default (pre-decision) | After ON (2026-07-25) |
|------|------------------------|------------------------|
| `AGENT_LAB_REPO_MAP` | OFF | **ON** via profile `flags` on `small` / `balanced` / `thorough` / `autonomous` |
| `AGENT_LAB_REPO_MAP_TOKENS` | `1024` | unchanged |
| `AGENT_LAB_COMPACT_TOOL_OUTPUT` | OFF | **ON** (same profiles) |
| `AGENT_LAB_COMPACT_TOOL_CHARS` | `2000` | unchanged |

`fast` stays lean (does not apply these as defaults). Explicit env still overrides profiles.

Enable for ad-hoc API process without a profile:

```bash
eval "$(make f7-dogfood-env)"
make dev
```

Use **supervisor** preset for real work (same as S1 dogfood).

## Duration & sample

| Gate | Threshold |
|------|-----------|
| Calendar | **7 days** from start date |
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

## Decision (closed 2026-07-25)

| Field | Value |
|-------|--------|
| Start date | 2026-07-09 |
| End date | 2026-07-25 |
| Sessions (n) | 32 instrumented (`make f7-dogfood-report`) |
| repo_map coverage % | 100.0 |
| median budget_pct | 18.9 |
| Compaction Human pass (x/5+) | **deferred** — no written ≥5 checklist; revisit with live non-lift sessions |
| **Decision** | **ON** |
| Rationale | Sample gates PASS. Enable as profile defaults on small/balanced/thorough/autonomous. **Revisit later** when more non-lift live data accumulates (Human usefulness still thin; many of the 32 were lift repeats). |

Recorded in `.agent-lab/dogfood-track.json` via `make dogfood-track-f7-decision DECISION=ON`.

### Revisit (explicit — not limbo)

- **When:** after a stretch of normal supervisor work (not X2-lift fill), or if agents feel lost / garbled from compaction.
- **How:** `make f7-dogfood-report` + Human checklist lines → keep ON, narrow profiles, or flip OFF with rationale.
- **Not:** “maybe later” without this ON close. Gate is closed; revisit is a scheduled second look.

### If ON (done)

- Profile `flags` set for `small` / `balanced` / `thorough` / `autonomous`.
- NORTH-STAR gauge: context quality → D3 (with revisit note).

### If OFF (not chosen)

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
| Profile defaults | `src/agent_lab/run/profile.py` |
