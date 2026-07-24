# Dogfood readiness — current status

> **Current operational status:** `OPEN` (2026-07-24). This is the canonical concise status pointer for the Task 7 readiness packet; it is not a shipped/complete operational rollout claim.

## Evidence split

| Tier | Result | Scope | Source artifact |
| --- | --- | --- | --- |
| mock | `PASS`, `n=2` | deterministic regression success and repair fixtures | `sessions/_regression/worktree_merge_ok/run.json`; `sessions/_regression/execute_verify_loop/run.json` |
| browser | `PASS`, `n=4` | Wave B browser UI contract; API routes are mocked | [`docs/evidence/dogfood-readiness/browser-contract.txt`](evidence/dogfood-readiness/browser-contract.txt) |
| live | `OPEN`, `n=0` | credentialed operational success and FAIL→repair/re-discuss evidence is absent | [`docs/evidence/dogfood-readiness/manifest.json`](evidence/dogfood-readiness/manifest.json) |

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
  MANIFEST=docs/evidence/dogfood-readiness/manifest.json \
  OUT_DIR=/tmp/agent-lab-dogfood-readiness
```

Binary observable: command exits `0`, the generated packet reports `readiness=OPEN`, and `default_change_authorized=false`.

The manifest is tracked and records the source commit used to author this fixture. Generated output is disposable and must not be read as provenance for a future commit.
