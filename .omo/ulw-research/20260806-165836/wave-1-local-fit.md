# Wave 1 — Agent Lab integration map

- External ingress belongs in `gateway/adapters.py`; provider/runtime events in `runtime/events.py`; approval in `human_inbox.py`; resumability in `checkpoint_store.py`; evidence in `evidence_ledger.py`; eval in `session/score.py`; UI events through typed Room SSE.
- Non-negotiable exclusions: Discuss read-only; Human Inbox gate authority; independent Oracle; fail-closed worktree; checkpoint restore-then-stop; subprocess env allowlist; no quant/trading core expansion.
- Local anchors: `src/agent_lab/runtime/events.py:8-59`, `src/agent_lab/worktree_hooks.py:21-205`, `src/agent_lab/human_inbox.py:37-184`, `src/agent_lab/checkpoint_store.py:1-168`, `src/agent_lab/evidence_ledger.py:15-78`, `src/agent_lab/session/score.py:122-170,396-489`, `web/src/hooks/useRoomSseHandler.ts:219+`.

## EXPAND
- LEAD: evaluate each shortlisted sample against these seams — WHY: avoid architecture replacement — ANGLE: fit matrix.

