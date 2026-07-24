# Wave B browser acceptance — 2026-07-24

> **Verdict:** **PASS** — live uvicorn + Vite Decision Queue journeys green.  
> **Scope:** UX-WAVE-B ship gate (Composer Decision Queue CTAs on real API).  
> **Not claimed:** M6 hard delete · mission-authority full cutover · Oracle worktree repair E2E · “replaces Cursor”.

## Commands

```bash
# Mock regression (CI)
cd web && npx playwright test e2e/wave-b-journey.spec.ts

# Live acceptance (ship proof)
bash scripts/run_wave_b_live_acceptance.sh
```

Live runner: seeds four English Dogfood sessions → API `:18765` with
`AGENT_LAB_MOCK_AGENTS=1`, `AGENT_LAB_MISSION_UI_READ_MODEL=1`,
`AGENT_LAB_MISSION_AUTHORITY=1` (human-resume allowlist) → Vite `:4173`
proxied to that API → Playwright **without** `/api` route mocks.

## Results (2026-07-24)

| Suite | Result |
|-------|--------|
| `wave-b-journey.spec.ts` (mocked API) | 4/4 PASS |
| `wave-b-live-journey.spec.ts` (real API) | 4/4 PASS (`WAVE_B_LIVE_ACCEPTANCE: PASS`) |

| Journey | CTA | Observed |
|---------|-----|----------|
| plan-reject | 수정 요청 | `POST …/plan/reject` 2xx |
| diff-approve | ExecuteQueueBar 승인 | `POST …/execute/resolve` 2xx |
| oracle-repair | ExecuteQueueBar Oracle 재검증 | `POST …/execute/reverify` (200 or 409 — pending seed; wiring only; full worktree repair out of scope) |
| human-resume | Inbox 제출 | `POST …/inbox/…/resolve` 2xx with `decision_id` · `mission_id` · `expected_version` · `selected: ["safe"]` |

## Supporting code

- Seed: [`scripts/seed_wave_b_live_sessions.py`](../../../scripts/seed_wave_b_live_sessions.py)
- Runner: [`scripts/run_wave_b_live_acceptance.sh`](../../../scripts/run_wave_b_live_acceptance.sh)
- Live e2e: [`web/e2e/wave-b-live-journey.spec.ts`](../../../web/e2e/wave-b-live-journey.spec.ts)
- Inbox `decision_version: 0` on create ([`human_inbox.new_inbox_item`](../../../src/agent_lab/human_inbox.py)); composer version-guard falls back to `sessionId` for `mission_id`

## Honesty notes

- Mock e2e remains CI regression only.
- This packet is the browser ship proof for Decision Queue journeys.
- Oracle live seed uses **pending + fail** (ExecuteQueueBar). Merged worktree repair against Cursor SDK is intentionally not part of this gate.
