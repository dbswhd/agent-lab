# Dogfood readiness — current status

> **Current operational status:** `OPEN` (2026-07-24). This is the canonical concise status pointer for the Task 7 readiness packet; it is not a shipped/complete operational rollout claim.

## Evidence split

| Tier | Result | Scope | Source artifact |
| --- | --- | --- | --- |
| mock | `PASS`, `n=2` | deterministic regression success and repair fixtures | `sessions/_regression/worktree_merge_ok/run.json`; `sessions/_regression/execute_verify_loop/run.json` |
| browser | `PASS`, `n=4` | Wave B browser UI contract; API routes are mocked | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/wave-b-browser.txt` |
| live | `OPEN`, `n=0` | credentialed operational success and FAIL→repair/re-discuss evidence is absent | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/dogfood-readiness.json` |

The browser result means **browser-contract acceptance is green**. It is not live evidence and does not close operational readiness.

## Authority boundary

- The packet records `readiness=OPEN` and `default_change_authorized=false`.
- No live cohort IDs were recorded; default routing/authority remains unchanged.
- A default routing/authority change, full-traffic cutover, or equivalent operational completion claim requires an explicit Human GO after the live gates pass.
- F7, N4-D3, and HS-M5 remain `OPEN`, each with an owner and next gate in the packet.

## Reproduction and traceability

Scenario: aggregate mock, browser, and live evidence without promoting browser evidence to live readiness.

Invocation:

```bash
make dogfood-readiness-report \
  MANIFEST=.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/manifest.json \
  OUT_DIR=.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7
```

Binary observable: command exits `0`, the generated packet reports `readiness=OPEN`, and `default_change_authorized=false`.

The `.omo` paths above are raw, non-tracked evidence kept out of Git intentionally; this concise tracked pointer preserves their current-state interpretation.
