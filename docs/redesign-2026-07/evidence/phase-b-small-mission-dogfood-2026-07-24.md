# Phase B Small Mission dogfood — Time-to-trust (MC-TT) — 2026-07-24

> **Verdict:** **PASS** — Human accept authorized; `MC-TT` closed.  
> **Profile:** `AGENT_LAB_RUN_PROFILE=small`  
> **Not claimed:** Phase C autonomy · 1–2h live supervisor soak beyond this surface packet · gate bypass

## Command

```bash
bash scripts/run_phase_b_small_mission_dogfood.sh
```

## Surfaces exercised

| Item | Surface | Observed |
|------|---------|----------|
| B1 | `status_line.human_gate_*` + Waiting chip | runtime `plan_approval` open; UI `대기 중`; `decision_latency_open=1` |
| B2 | ExecuteQueueBar evidence strip | diff stat + Oracle labels visible |
| B3 | Needs input age + steer queue | `needs-input-age` visible; `POST /steer` queued |
| B4 | F8 cost chip | `session-cost-chip` with `$` under mission budget |

Also: run profile chip shows `small`.

## Results (2026-07-24)

```
PHASE_B_SMALL_MISSION_DOGFOOD: PASS
Playwright 2/2 + API smoke (runtime human_gate + score latency open)
```

## Artifacts

- Seed: `scripts/seed_phase_b_small_mission_dogfood.py`
- Runner: `scripts/run_phase_b_small_mission_dogfood.sh`
- E2E: `web/e2e/phase-b-small-mission-dogfood.spec.ts`
- Config: `web/playwright.phase-b-small.config.ts`
