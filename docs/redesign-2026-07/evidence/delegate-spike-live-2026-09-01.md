# Delegate spike live dry-run — C5 evidence (2026-09-01)

## Scope

Validate end-to-end delegate path:

```
execute dry-run (worktree, pending_approval)
  → external:codex-delegate (cwd=worktree)
  → stdout handoff JSON auto-attach
  → main repo stays clean
```

## Commands

```bash
# Mock delegate (default — no Codex call)
AGENT_LAB_EXTERNAL_TOOLS=1 python scripts/live_delegate_dry_run.py

# Live Codex (requires ~/.agent-lab/tools.yaml + supported Codex model)
AGENT_LAB_EXTERNAL_TOOLS=1 AGENT_LAB_RUN_LIVE=1 python scripts/live_delegate_dry_run.py

# Pytest (mock only)
pytest tests/test_live_delegate_spike.py::test_live_delegate_spike_mock_go -q
```

## Results

| Mode | Verdict | Notes |
|------|---------|-------|
| **mock** | **GO** | All 9 checks pass; handoff attached; marker only in worktree |
| **codex live** | **NO_GO (env)** | Codex CLI starts but model rejected by ChatGPT account |

### Mock run (2026-09-01)

```
Live delegate dry-run (mock): GO
  pending_approval: OK
  worktree_exists: OK
  delegate_ok: OK
  handoff_attached: OK
  marker_in_worktree: OK
  marker_not_on_main: OK
  main_clean_after_delegate: OK
  handoff: Delegate spike attached LIVE_DELEGATE_OK
```

### Live Codex run (2026-09-01)

- Preflight: `codex` available at `~/.nvm/.../codex.js`
- Dry-run + worktree creation: OK
- Delegate subprocess exit non-zero
- Root cause (Codex stderr):

```
The 'gpt-5.6-sol' model is not supported when using Codex with a ChatGPT account.
```

`~/.codex/config.toml` sets `model = "gpt-5.6-sol"`. Manual `codex exec -m gpt-5.4` fails with the same class of error.

**Unblock for live Codex:** switch Codex auth/model to a supported configuration (API key or ChatGPT-supported model), then re-run:

```bash
AGENT_LAB_EXTERNAL_TOOLS=1 AGENT_LAB_RUN_LIVE=1 make live-delegate-dry-run
```

## Artifacts

| File | Role |
|------|------|
| `scripts/soak/live_delegate_spike.py` | Core spike logic |
| `scripts/live_delegate_dry_run.py` | CLI entry |
| `tests/test_live_delegate_spike.py` | Mock regression test |

## C5 verdict

**Pipeline GO (mock).** Worktree isolation, external runner, and handoff attach are proven without Codex dependency. Live Codex delegate remains a **Human env follow-up** (model/auth), not a code blocker.
