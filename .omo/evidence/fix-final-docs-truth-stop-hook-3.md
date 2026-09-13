# Stop-hook pass 3 — F4 documentation truth

## Actual verification command

```text
cd web
npx playwright test e2e/wave-b-journey.spec.ts --reporter=line
git -C .. show --check --format=oneline 37619204
jq -r '"readiness=\(.readiness) browser=\(.evidence_by_tier.browser.status):n\(.evidence_by_tier.browser.sample_size) live=\(.evidence_by_tier.live.status):n\(.evidence_by_tier.live.sample_size) default_change_authorized=\(.default_change_authorized)"' ../.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/dogfood-readiness.json
rg stale-current-browser predicate over ../.agent-lab/PROJECT.md and ../docs (excluding archive and JSON)
git -C .. diff --quiet HEAD -- <10 committed documentation paths>
```

## Captured output

```text
Running 4 tests using 1 worker
[1/4] plan reject journey sends reject request and enters refine phase
[2/4] diff approve journey resolves pending execution
[3/4] Oracle repair journey re-verifies failed execution
[4/4] human resume journey answers inbox question
4 passed (4.3s)
376192040e00e771d43aa2c9b7ccbc393c047cce docs(ux): align browser and readiness status
readiness=OPEN browser=PASS:n4 live=OPEN:n0 default_change_authorized=false
VERDICT=PASS browser_contract=green task7_operational=OPEN default_routing_authority=Human_GO_only committed_docs_clean=true
```

## Judgment

PASS. Browser-contract acceptance is green. The Task 7 live/operational tier is still `OPEN` with `n=0`; default routing/authority remains unauthorized without explicit Human GO. The committed documentation files are clean, and the current-doc stale-browser-red audit returned no matches.
