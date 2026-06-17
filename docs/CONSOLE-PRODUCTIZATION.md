# Console Productization Plan

> **Status (2026-06-12):** Productization program SSOT. This document aligns UI IA, Hook/Response Contract UX, verification speed, and Cursor bridge lifecycle work after the core Room/Execute queues shipped.
> **Design frame:** Agent Lab is a **Human-in-the-loop agent development console**, not a chat app.
> **Related:** [UI-IA-ROADMAP.md](UI-IA-ROADMAP.md), [HOOK-COMMUNICATE-REFORM.md](HOOK-COMMUNICATE-REFORM.md), [NOTIFICATION-TAXONOMY.md](NOTIFICATION-TAXONOMY.md), [OPS-RUNBOOK.md](OPS-RUNBOOK.md).

---

## 1. Product IA Contract

### Launch Positioning Note

출시 문구에서 `AI 에이전트 오케스트레이션 플랫폼`은 상위 카테고리로만 사용한다. 첫 화면·README·세일즈 문구의 주 메시지는 **AI 개발 작업을 계획·승인·격리 실행·검증하는 Human-in-the-loop 에이전트 개발 콘솔**로 둔다.

**Primary audience:** AI-native 개발팀 / 내부 플랫폼팀의 tech lead·maintainer. 개인 취미 개발자, 일반 챗봇 사용자, 범용 운영 대시보드는 1차 타깃이 아니다.

**Outcome message:** AI 작업을 `plan.md` 계약으로 구조화하고, Human 승인 뒤 worktree 실행·merge·Oracle 검증까지 감사 가능한 단위로 묶는다.

| Surface | Product role | Must contain | Must not contain |
|---------|--------------|--------------|------------------|
| Transcript | Conversation consumption and Human popup entry | Agent response cards, raw response disclosure, Question/Build popups, Human decision events | Hook settings, merge approval, diagnostics |
| Work | Execution judgment | Action candidates, dry-run diff, approve/reject/revise, merge conflict, oracle/verify, execution-relevant hook results | General agent chatter |
| Inspector Overview | Current session state | Mission/goal, plan status, context layers, team health | Deep settings |
| Inspector Tasks | Persistent work queue | Open objections, task summaries, jump actions | Full duplicate TaskBar |
| Inspector Inbox | Human/action feed | Human Inbox + Activity segments | Separate Activity tab |
| Settings | Policy and operations configuration | Agents, workspace, commands, diagnostics, Hooks & Response Contracts | Per-turn approve/merge controls |
| Composer | Input only | message, turn profile, slash command, attachments, cost hint | Build approval, Question resolution, settings |

**Decision:** Activity is **not** a fourth Inspector tab. It lives inside **Inbox** as a segmented feed: `All | Activity | Questions | Build`.

---

## 2. Phase Map

### P0 — IA Finish, Not Redesign

**Already shipped. Do not reimplement:**

- Inspector tabs: `overview | tasks | inbox` in `workspaceTabs.ts`.
- `RoomTaskBar` docked in Transcript/Work body.
- `ContextOverviewPanel` for Overview.
- Human Inbox and Activity colocated under Inbox.

**Remaining / acceptance:**

- [x] Inspector Tasks is a jumpable summary queue, not a full TaskBar duplicate.
- [x] Inbox uses segments: `All | Activity | Questions | Build`.
- [ ] Goal/verified controls in Tasks are reviewed for overlap with the TaskBar; keep only Human action controls there.
- [ ] Composer visual treatment is documented as docked input, not floating decision surface.
- [ ] `UI-IA-ROADMAP.md` checklist matches code.

### P1 — Hook & Response Contract Observability

**Scope for P1:** observe, route, and explain. Do **not** add full editing of hooks yet.

**P1a: low-risk surfaces**

- [x] Settings `Hooks & Response` read-only section:
  - hook config path candidates
  - env flags: envelope strictness, guidance tier, native hooks
  - recent `hook_runs[]` tail
  - last failure reason
- [x] Activity first-class hook events:
  - `Stop hook blocked completion`
  - `PostToolUse formatter failed`
  - `Response contract invalid`
  - actions: `Open Work`, `Open Settings`, `View log`
- [ ] Work receives only execution-relevant contract results:
  - pre-execute blocked
  - contract invalid for pending execution
  - verify/hook evidence required for approve

**P1b: heavier contract UI**

- [x] Response Contract presets:
  - `Concise`
  - `Evidence-first`
  - `Plan-ready`
  - `Review-only`
  - `Build handoff`
- [x] First version maps to existing guidance/prompt controls through session `response_contract`.
- [x] Avoid a new writable hooks schema; hooks.toml editing remains out of scope.

**P1c: Agent Response Card**

- MVP reads existing envelope / `communicate_meta`.
- Required fields for MVP:
  - `status`
  - `summary` when available
  - `evidence` when available
  - `decisions_needed`
  - `next_actions`
- Raw markdown remains available in a collapsed disclosure.

**P1d: Failure Recovery UX** ✅

**Goal:** users recover common operational failures without reading docs or opening raw logs first.

**Scope:** expose existing recovery signals and actions in one predictable route. Do **not** reimplement backend recovery logic already owned by health, run lock, partial turn, mission resume, or Oracle repair.

| Failure | Detection source | Primary surface | Required user action | Must not do |
|---------|------------------|-----------------|----------------------|-------------|
| Auth expired | health/preflight agent row, OAuth panels | Recovery strip + Settings deep link | Re-login / reconnect, then re-run health check | Hide behind generic "agent failed" |
| Cursor bridge failed | `AgentHealthPanel` bridge fields, degraded health | Recovery strip + Settings Diagnostics | Reconnect bridge, show fallback/exclude Cursor option | Duplicate a separate bridge wizard outside Settings |
| Run lock stuck | `/api/room/run-lock`, `RoomRunStatusBar` | Composer/Transcript top strip | Release lock after stale/orphan explanation | Auto-release an active run silently |
| Partial turn | turn status `partial`, `agent_error`, preserved successful replies | Transcript turn recovery card | Retry failed agents, continue with successful replies, or open Settings | Discard successful agent output |
| Oracle fail | execution oracle verdict / mission `discuss_recovery.pending` | Work + Inspector Inbox | Reverify, start repair, or run discuss recovery | Call it "done" or bury it in logs |

**UX contract:**

- A single **Recovery** strip appears above the main work area when any blocking failure is active.
- Each item has: `what happened`, `why it blocks`, `primary action`, `secondary action`, `details`.
- The strip routes to the canonical surface:
  - auth / bridge -> Settings Diagnostics
  - run lock / partial turn -> Transcript or composer run status
  - Oracle fail / discuss recovery -> Work + Inbox
- The Inbox `Activity` segment records recovery events, but it is not the only place to act.
- Multiple failures are grouped by severity: `blocking execute` -> `blocking send` -> `degraded team` -> `informational`.

**Acceptance:**

- Trigger each failure in mock or fixture mode and verify a user can recover using only visible UI copy.
- Every recovery CTA has an API call or navigation target; no dead-end "read docs" actions.
- Raw logs remain available under details, not as the first required step.
- Existing shipped behavior remains authoritative:
  - bridge degraded health: `Bridge` traceability row
  - partial turn: `R-P0`
  - Oracle repair/reverify: `LC-L3`
  - mission discuss recovery: `ML-P4`
  - boulder/resume state: `RT-H6`

**P1e: Work Decision Surface** ✅

**Goal:** users can decide in one Work surface what needs approval, why progress is blocked, and whether the result is verified.

**Scope:** frontend integration only. Do **not** add a backend Work endpoint or duplicate merge/reverify handlers outside their canonical owners.

| Decision question | Source | Primary surface | Canonical action owner |
|-------------------|--------|-----------------|------------------------|
| What do I approve? | plan workflow, pending executions | Work decision panel + Work approval card | `PlanApprovalPanel`, `PlanExecutePanel` |
| Why is it blocked? | plan stale notice, BLOCK objections, pre-execute hooks, merge checks, runtime gates | Work decision panel + Checks/Evidence anchors | Tasks, hook/runtime gates, merge checks |
| Was it verified? | execution Oracle, `verify_after_merge`, evidence gates | Work decision panel + evidence/execute cards | `PlanExecutePanel` + evidence timeline |

**UX contract:**

- Visible tab/surface label is **Work**. Internal route id may remain `plan` for compatibility.
- Work top chrome contains the stepper plus one decision summary with `Approve`, `Blocked`, `Verified` columns.
- Tasks may summarize approval/blocking work, but full plan approval lives in Work.
- `PlanExecutePanel` remains the owner for merge approve/reject/revise/reverify.
- RecoveryStrip remains operational recovery; WorkDecisionPanel is execution judgment.

**Acceptance:**

- `HUMAN_PENDING` plan workflow shows plan approval in Work and only a Work jump in Tasks.
- Pending execution shows merge/artifact approval target at the top and anchors to the pending card.
- merge checks, pre-verify, open BLOCK, merge conflict, and Oracle FAIL explain why Work is blocked.
- Oracle PASS + completed execution reads as verified/done.
- Mobile width does not overlap decision text or CTA controls.

**P1f: First-run Onboarding Wizard** ✅

**Goal:** first-time and returning users can connect agents, choose a workspace, and start a sample session without reading setup docs.

**Scope:** frontend integration only. Reuse existing health, Settings diagnostics, reconnect actions, session setup options, folder picker, and New Session flow. Do **not** add provisioning endpoints, automatic CLI login, or auto-run sample turns.

| Setup question | Source | Primary surface | Canonical action owner |
|----------------|--------|-----------------|------------------------|
| What do I need to connect? | health agent rows, bridge readiness | Setup wizard + Settings Diagnostics | Settings / reconnect handlers |
| Why is setup blocked? | API health, agent readiness, workspace selection | Setup wizard step status | Existing health/session setup |
| How do I try it safely? | sample topic, New Session dialog | Setup wizard -> New Session | Composer send remains Human-owned |

**UX contract:**

- Setup wizard has three steps: `Connect agents` -> `Choose workspace` -> `Start sample session`.
- Cursor/Claude use existing reconnect CTAs; Codex routes to Settings/auth guidance.
- Workspace selection opens the existing New Session workspace chooser.
- Sample session pre-fills a topic; the user still reviews team/workspace and sends manually.
- Dismiss is versioned for this onboarding generation, not a permanent product-wide hide.
- RecoveryStrip remains operational recovery; WorkDecisionPanel remains approval/block/verify judgment.

**Acceptance:**

- Fresh state shows Setup wizard before the empty composer.
- Existing-session users can reopen Setup from the rail.
- Cursor/Claude degraded rows show reconnect paths, and Codex missing auth shows Settings guidance.
- Workspace missing state blocks sample until a workspace is selected.
- Sample topic is prefilled but not auto-sent.
- Mobile width does not overlap step text or CTA controls.

**P1g: Recovery Closed Loop** ✅

**Goal:** users can tell whether a recovery action actually cleared the blocker and whether it is safe to try again.

**Scope:** frontend + existing in-memory Activity store only. Do **not** add recovery endpoints or persistent audit logs.

| Loop question | Source | Primary surface | Canonical owner |
|---------------|--------|-----------------|-----------------|
| Did the blocker clear? | Recovery item diff after action + health/readiness/session refresh | RecoveryStrip resolved row | frontend lifecycle utility |
| Is it still blocked? | Same recovery item remains after action | RecoveryStrip active item + Activity event | RecoveryStrip + Settings/Work |
| Can I retry? | Composer lock + last plain text send | Composer focus / restore text CTA | Human-owned composer send |

**UX contract:**

- Recovery actions that actually check or mutate state create an attempt event.
- If the matching recovery item disappears after refresh, RecoveryStrip keeps a compact resolved row.
- If the item remains, RecoveryStrip shows “still blocked” and Activity records it.
- Retry CTA never auto-sends. It focuses the composer or restores the last attachment-free text.
- Oracle/discuss recovery routes to Work instead of composer retry.
- Activity records recovery started/resolved/still-blocked in memory; reload persistence is out of scope.

### P2 — Verification Speed

**Status:** implemented as the P2 lane split + visible diagnostics report.

**Goal:** make local status legible without waiting for the full slow suite.

- Marker policy:
  - `fast`: explicit fast tests; unmarked non-live/non-integration/non-bridge tests are also in the fast lane.
  - `integration`: mock multi-component, subprocess, worktree, or slower API tests.
  - `bridge`: Cursor bridge lifecycle / reconnect / preflight tests, excluded from fast.
  - `live`: opt-in real CLI/SDK/network checks.
- Targets:
  - `make test-fast`: `not live and not integration and not bridge`.
  - `make test-integration`: `integration and not live and not bridge`.
  - `make test-bridge`: `bridge and not live`.
  - `make ci`: PR gate, fast enough for iteration.
  - `make ci-full`: release gate, full fast + integration + bridge + smoke + score.
- Visibility:
  - lane runs write `sessions/_reports/verification-latest.json`.
  - `/api/diagnostics` exposes the latest report.
  - Settings Diagnostics and rail diagnostics show Fast / Integration / Bridge / CI full status.

### P3 — Cursor Bridge Lifecycle / Ops

**Goal:** bridge processes are visible, attributable, and cleanable.

- Bridge process registry:
  - workspace path
  - pid
  - started_at
  - owner: app / test / live-run
  - status
- Diagnostics:
  - active bridge count
  - stale candidates
  - current workspace bridge health
- Settings Diagnostics:
  - reconnect
  - cleanup stale candidates
  - view process details
- Ops scripts:
  - `scripts/check_bridge_processes.py`
  - optional `--cleanup`
- Tests:
  - temp workspace bridge teardown is mandatory for bridge-marked tests.
  - cleanup must not kill the current app workspace bridge.

---

## 3. Documentation Rules

- `CONSOLE-PRODUCTIZATION.md` owns phase numbering for productization.
- `UI-IA-ROADMAP.md` owns detailed UI migration backlog only.
- `HOOK-COMMUNICATE-REFORM.md` owns shipped hook/communicate runtime behavior.
- `OPS-RUNBOOK.md` owns manual Tier A/B/C operating routines.
- If status disagrees, code + tests + `EXTERNAL-REFS-TRACEABILITY.md` win.

---

## 4. Current Next Ticket Recommendation

**Next:** P3 — Cursor Bridge Lifecycle / Ops.

Why:

- Failure recovery, Work decision judgment, first-run setup, and verification lane visibility are now consolidated at the UI level.
- Bridge health now has a dedicated test lane, but lifecycle cleanup and operator controls still need the same product-level finish.
- P1c Agent Response Card remains display polish after the setup, decision, recovery, and verification loops are legible.
