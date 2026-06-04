# LC-L4 — Adversarial gate (live Claude opt-in)

Dry-run approve UI shows a **non-blocking** adversarial note from `adversarial_gate.py`.

## Default (CI / dev)

- `AGENT_LAB_ADVERSARIAL_LIVE` unset → **mock** reviewer (`source: mock`)
- No API keys required; `make ci` safe

## Live Claude

```bash
export AGENT_LAB_ADVERSARIAL_LIVE=1
# claude login required — uses claude_cli.invoke("adversarial-reviewer", ...)
```

- `source: live` on execution evidence
- Same prompt as mock: max 3 failure reasons or `LGTM`
- Does **not** block approve — Human decides

## UI

- `PlanExecutePanel.tsx` — `AdversarialBadge` (lgtm / warning tone)
- Regression: `sessions/_regression/adversarial_gate_lgtm/`

## Related

- `docs/EXTERNAL-REFS-PLAN.md` §1.5
- `tests/test_lc_l4_runtime.py`
