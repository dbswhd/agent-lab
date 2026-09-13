# F4 documentation truth repair — direct verification

Verified after commit `376192040e00e771d43aa2c9b7ccbc393c047cce`.

## 1. Wave B browser-contract acceptance

Scenario: run the current Wave B journey in a real Playwright browser.

Invocation:

```bash
cd web && npx playwright test e2e/wave-b-journey.spec.ts --reporter=line
```

Captured output:

```text
Running 4 tests using 1 worker
[1/4] plan reject journey sends reject request and enters refine phase
[2/4] diff approve journey resolves pending execution
[3/4] Oracle repair journey re-verifies failed execution
[4/4] human resume journey answers inbox question
4 passed (5.5s)
```

Verdict: PASS. This proves the browser UI contract only; its API routes are mocked.

## 2. Task 7 readiness split

Scenario: read the Task 7 packet fields directly, rather than relying on its prose report.

Invocation:

```bash
jq -e '.readiness == "OPEN" and .default_change_authorized == false and .evidence_by_tier.browser.status == "PASS" and .evidence_by_tier.browser.sample_size == 4 and .evidence_by_tier.live.status == "OPEN" and .evidence_by_tier.live.sample_size == 0' \
  .omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/dogfood-readiness.json
```

Captured output: command exited `0` with no stdout.

Verdict: PASS. The packet records browser `PASS` (`n=4`), but live `OPEN` (`n=0`) and `default_change_authorized=false`.

## 3. Committed documentation truth, links, and scope

Scenario: validate the committed file list, whitespace, stale browser-red statements, required green/OPEN/Human-GO truth, link targets, and absence of new owned-doc edits.

Invocation:

```bash
git show --check --format=oneline 37619204
# compare its name-only output to the 10 intended documentation paths
# run focused rg/test -f predicates for the current-state truth and links
git diff --quiet HEAD -- <the 10 committed documentation paths>
```

Captured output:

```text
376192040e00e771d43aa2c9b7ccbc393c047cce docs(ux): align browser and readiness status
PASS browser_contract=4/4 task7_packet_split=true committed_scope=10 current_doc_semantics=true links=true owned_docs_clean=true
```

Verdict: PASS. Current docs say browser acceptance is green while Task 7 operational/live readiness is `OPEN`; they retain explicit Human GO for default routing/authority. The Work navigation tab and Composer Plan picker/toggle audits remain qualified as removed, hidden, internal, legacy, or history-only.

Raw Task 7 evidence remains untracked and was not included in the commit. The concise tracked pointer is `docs/DOGFOOD-READINESS-STATUS.md`.

## 4. Fresh stop-hook verification

Scenario: repeat the browser run and all claimed current-state/commit predicates after the previous completion report.

Invocation:

```bash
cd web
npx playwright test e2e/wave-b-journey.spec.ts --reporter=line
git -C .. show --check --format=oneline 37619204
jq -e '<Task 7 browser PASS n=4; live OPEN n=0; default false predicate>' \
  ../.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/dogfood-readiness.json
# focused rg stale-current-browser audit, readiness-pointer existence,
# and git diff --quiet for the 10 committed documentation paths
```

Captured output:

```text
Running 4 tests using 1 worker
[1/4] plan reject journey sends reject request and enters refine phase
[2/4] diff approve journey resolves pending execution
[3/4] Oracle repair journey re-verifies failed execution
[4/4] human resume journey answers inbox question
4 passed (6.4s)
376192040e00e771d43aa2c9b7ccbc393c047cce docs(ux): align browser and readiness status
PASS fresh_direct_verification browser=4/4 packet=OPEN:n0:false commit_scope_clean=true stale_current_browser_red=0 readiness_pointer=true
```

Verdict: PASS. The fresh result independently matches the prior evidence; no failure was found.
