# Task 1 documentation-chain integration evidence

## Scope and source

- Target branch: `codex/ux-flow-alignment`
- Source chain: `3a088488239d2ac4e9e3cfcd5ad1cca4d60f88ff` → `057d5932573c7c9608282fc6b0d9bfec40135dcf` → `f951a207d71882fffc47bd7d2c8aeb589486ae54`
- Resulting target HEAD: `49030edf2bb679e31e9a078b5c698d2a01288a1a`
- Operation: ordered exact cherry-pick; no conflicts.

## Binary integration proof

Scenario: preserve the confirmed three-commit documentation chain without carrying original SHA ancestry.

Invocation:

```bash
git range-diff dca996c0c042fc863839a5c3c26a75161a651891..f951a207d71882fffc47bd7d2c8aeb589486ae54 HEAD~3..HEAD
git diff --exit-code f951a207d71882fffc47bd7d2c8aeb589486ae54 HEAD -- \
  .agent-lab/PROJECT.md docs/05-room-agent-roles.md docs/EXTERNAL-REFS-TRACEABILITY.md \
  docs/FLOW.md docs/NOW.md docs/USER-GUIDE.md docs/redesign-2026-07/11-ui-ux-surface-map.md
```

Observable:

```text
1:  3a088488 = 1:  c4c484f0 docs(ux): rebaseline Decision Queue lifecycle contract
2:  057d5932 = 2:  7f09f3f3 docs(ux): remove residual Work tab wording
3:  f951a207 = 3:  49030edf docs(ux): align remaining Work surface references
PASS final content for all seven intended docs exactly equals source final commit
```

Changed docs, exactly:

```text
.agent-lab/PROJECT.md
docs/05-room-agent-roles.md
docs/EXTERNAL-REFS-TRACEABILITY.md
docs/FLOW.md
docs/NOW.md
docs/USER-GUIDE.md
docs/redesign-2026-07/11-ui-ux-surface-map.md
```

Scope proof: `git diff --name-only HEAD~3..HEAD` returned precisely that list; the inverse runtime-file check was empty.

## Documentation contract and manual QA

Scenario: inspect current prose in all seven docs.

Invocation:

```bash
rg -n -i 'Decision Queue|Human Inbox|Work.{0,40}(아님|제거|숨김|history|historical|compatibility|internal)|Work tab|Work 탭|Workbench|browser acceptance|Wave B' \
  .agent-lab/PROJECT.md docs/05-room-agent-roles.md docs/EXTERNAL-REFS-TRACEABILITY.md \
  docs/FLOW.md docs/NOW.md docs/USER-GUIDE.md docs/redesign-2026-07/11-ui-ux-surface-map.md
```

Binary results:

```text
PASS WORK_NAVIGATION_HISTORICAL_COMPATIBILITY_ONLY=true
PASS DECISION_QUEUE_AND_HUMAN_INBOX_CURRENT=true
```

Clarification: this concerns the legacy visible **Work navigation/tab**. The current internal lowercase `work` lane remains an explicitly non-navigation rendering lane; it does not restore the removed Work tab.

Per-file current marker counts from the manual audit: PROJECT `1`, roles `6`, traceability `3`, FLOW `7`, NOW `2`, USER-GUIDE `38`, surface map `6`. Historical/removed Work-navigation markers are explicit wherever Work navigation appears; traceability and NOW do not make a Work-navigation claim.

## Verification

| Scenario | Invocation | Binary observable |
| --- | --- | --- |
| Relative Markdown links | Python 3 checker over the seven docs | `PASS markdown relative-link check: files=7 local_targets=93` |
| Whitespace | `git diff --check HEAD~3..HEAD` and `git diff --check` | both exited 0 |
| Stale terms | Python 3 scan for English/Korean Workbench/Work tab/Plan picker/Wave B 4/4 terms | `stale-term-matches=21 violations=0` |
| Owned-doc cleanliness | `git status --short -- <seven docs>` | empty output |
| Cherry-pick scope | `git diff --name-only HEAD~3..HEAD` plus inverse runtime-file check | exactly seven docs; no runtime/unrelated path |

## Adversarial classification

- `stale_state`: PASS — source-final tree equality and 21-match stale-term audit (`violations=0`) prevent a stale source or residual current Work-tab claim.
- `dirty_worktree`: PASS — pre-existing `web/e2e/wave-b-journey.spec.ts` edit and untracked plan/evidence/debug/venv files remained unstaged; owned-doc status is empty.
- `misleading_success_output`: PASS — success is supported by range-diff equality, byte-for-byte final-doc diff, exact path scope, and explicit red/not-browser-accepted wording rather than cherry-pick exit status alone.
- `malformed_input`: NOT_APPLICABLE — no parser, request payload, or runtime input changed; git commit identifiers were resolved before mutation.
- `mid_operation_interrupt` / `reload`: NOT_APPLICABLE — each bounded local cherry-pick completed synchronously with no server, process, or reload state.
- `auto_approval` / `trust_budget_bypass`: NOT_APPLICABLE — documentation-only git integration did not invoke a Human-action, merge, execute, or Oracle workflow.
- `clean_startup` / `long_running`: NOT_APPLICABLE — no application server, browser, or background process started.
- `generated_artifact`: PASS — this evidence file is the only integration artifact; no temporary files were created and no temporary cleanup is pending.

## Cleanup

No temporary files or processes were created. No untracked `.omo` plan/evidence, debug journal, virtual environment, or modified web test was staged or committed.
