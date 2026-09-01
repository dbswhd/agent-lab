# Delegate spike — external CLI in worktree

> **Status:** Phase 1 spike (2026-09) · **SSOT code:** `external_tools.py` · `external_handoff.py` · `runtime/external_runner.py`

## C0 blocker (resolved)

| Blocker | Before | After |
|---------|--------|-------|
| `cwd: worktree` in tools.yaml | Parsed but treated as workspace fallback | `resolve_external_tool_cwd()` reads open execution `worktree_path` |
| `{worktree_path}` placeholder | N/A | Expanded in command argv |
| Delegate tool catalog | GJC stubs only | `external:codex-delegate` · `external:claude-delegate` defaults (stub until configured) |

**Unchanged (by design):** Human confirm · merge gate · Oracle · BLOCK→409. Delegate does not bypass execute flow.

## Enable

```bash
export AGENT_LAB_EXTERNAL_TOOLS=1
export AGENT_LAB_RUN_PROFILE=balanced   # optional — Oracle live + S1 trio
cp .agent-lab/tools.yaml.example ~/.agent-lab/tools.yaml
# Edit CODEX_BIN / CLAUDE_BIN paths if needed
```

Session allowlist:

```http
PATCH /api/sessions/{id}/external-tools
{ "enabled": ["external:codex-delegate"] }
```

## Flow

```
plan approved → execute dry-run (worktree created, pending_approval)
      → /codex-delegate or /claude-delegate (confirm=true)
      → subprocess cwd = executions[].worktree_path
      → stdout handoff JSON → executions[].external_handoff (auto)
      → Human diff review → merge → Oracle
```

## Handoff JSON (agent must emit)

```json
{
  "stopped_cleanly": true,
  "changed_files": ["src/foo.py"],
  "checks": [{"cmd": "make test-fast", "exit": 0}],
  "evidence_summary": "Implemented plan action; tests pass.",
  "risks": []
}
```

Fenced block or trailing JSON on stdout both work (`parse_handoff_payload`). Alternatively write `external_handoff.json` in the session folder.

## Prompt tail (suggested)

Append to delegate args:

```
When done, print ONLY a JSON object with keys:
stopped_cleanly, changed_files, checks, evidence_summary, risks.
```

## Failure modes

| Symptom | Cause |
|---------|-------|
| `worktree_cwd_unavailable` | No open execution or missing `worktree_path` |
| `not_allowlisted` | Tool not in session `external_tools.enabled` |
| `pending_human` | `human_approve: true` without `confirm=true` |
| `no_pending_execution` (handoff) | Handoff valid but no `pending_approval` execution |

## Tests

```bash
pytest tests/test_delegate_spike.py tests/test_external_handoff.py -q
```

## Out of scope (Phase 1)

- Claude as native execute-lane agent (`EXECUTE_AGENT_IDS` still cursor\|codex)
- Streaming event ingest from codex JSONL
- Auto-merge without Human diff review
