---
target: Plan Execute delegate bar
total_score: 21
p0_count: 1
p1_count: 3
timestamp: 2026-09-01T10-57-33Z
slug: web-src-components-delegateexecutebar-tsx
---
# Plan Execute Delegate Bar — Design Critique

**Target:** `web/src/components/DelegateExecuteBar.tsx` (+ pending card integration)
**Date:** 2026-09-01
**Register:** product (Mission OS execute surface)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Long delegate runs show only button label "실행 중…"; no elapsed time, log stream, or completion announcement |
| 2 | Match System / Real World | 2 | Jargon ("delegate", "handoff", "CLI"); allowlist hint points to non-existent "Tools → Plugins" path |
| 3 | User Control and Freedom | 2 | No cancel during subprocess; no undo of delegate run (only merge reject) |
| 4 | Consistency and Standards | 2 | Room slash external commands use confirm modal; delegate bar fires immediately with `confirm: true` |
| 5 | Error Prevention | 1 | One-click launches external CLI that can modify worktree — no prompt preview or second confirm |
| 6 | Recognition Rather Than Recall | 2 | Setup requires remembering env + yaml + Settings allowlist; hint misroutes users |
| 7 | Flexibility and Efficiency | 2 | No prompt edit, no keyboard accelerator, no "run again" shortcut |
| 8 | Aesthetic and Minimalist Design | 2 | Handoff status repeated 3×; bar always visible on every pending worktree even when feature off |
| 9 | Error Recovery | 3 | Errors surface in `role="alert"` with server detail; user can retry |
| 10 | Help and Documentation | 3 | Inline hints exist and are task-focused — but one is factually wrong |
| **Total** | | **21/40** | **Acceptable (low)** |

**Cognitive load:** 4 checklist failures (single focus, working memory, progressive disclosure, visual hierarchy) → **high extraneous load** for a spike feature.

## Anti-Patterns Verdict

**LLM assessment:** Does not read as generic AI slop (no purple gradients, no card-in-card stacks). It reads as an **internal spike grafted onto a mature execute panel** — correct tokens, dashed optional affordance, but inconsistent copy and interaction patterns with the rest of Agent Lab.

**Deterministic scan:** Component files clean (`[]`). Related `plan-execute.css` elsewhere has unrelated `side-tab` and `layout-transition` warnings (lines 465, 2669) — not in delegate bar block itself.

**Browser visualization:** Skipped — dev server not running; surface requires live session with `pending_approval` worktree execution.

## Overall Impression

The delegate bar is in the **right place** (pending worktree card, before merge) and uses the existing plan-execute vocabulary. But it behaves like a **developer toggle**, not a **human gate**: wrong setup directions, no execution preview, and redundant handoff chrome undermine the product's "one decision surface" principle.

**Biggest opportunity:** Turn delegate into a **single high-stakes action with preview + confirm**, and hide the entire affordance until the feature is actually configured.

## What's Working

1. **Contextual placement** — Only renders on `pending_approval` + worktree executions.
2. **Progressive tool filtering** — Correct gates on allowlist, stub status, runner enabled.
3. **Handoff result design** — Badge/strip with checks summary and changed files is readable for merge review.

## Priority Issues

### [P0] Wrong allowlist navigation hint
- **Fix:** Correct path to Settings → 플러그인 → External; add deep-link button.
- **Suggested command:** `$impeccable clarify DelegateExecuteBar`

### [P1] No confirm / prompt preview before external CLI
- **Fix:** Reuse MacAlert confirm with prompt preview and worktree path.
- **Suggested command:** `$impeccable harden DelegateExecuteBar`

### [P1] Feature-off noise on every pending card
- **Fix:** Hide bar when global runner disabled.
- **Suggested command:** `$impeccable quieter DelegateExecuteBar`

### [P1] Triplicate handoff status
- **Fix:** One primary handoff location; action-only bar after attach.
- **Suggested command:** `$impeccable distill Plan Execute handoff display`

### [P2] Mixed language and developer copy
- **Fix:** Korean user-facing labels; env details in Settings only.
- **Suggested command:** `$impeccable clarify DelegateExecuteBar`

## Persona Red Flags

**Alex:** No prompt edit, no keyboard shortcut, wrong-path hints waste space.

**Jordan:** Jargon unexplained; hint path doesn't exist; no visible success confirmation.

**Sam:** No `aria-live` for delegate completion; `aria-busy` missing during run.

**Mission Operator:** Multiple competing surfaces on pending card violates one-decision-surface principle.

## Minor Observations

- Dashed border correctly signals optional path.
- `buildDelegatePrompt()` mixes EN/KR.
- PluginPanel External group collapsed by default.

## Questions to Consider

- Secondary action behind "More execute options" until first use?
- Editable prompt preview before send?
- Hide delegate bar after handoff attaches?
