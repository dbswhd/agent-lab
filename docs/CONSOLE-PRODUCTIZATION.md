# Console Productization Plan

> **Status (2026-06-12):** Productization program SSOT. This document aligns UI IA, Hook/Response Contract UX, verification speed, and Cursor bridge lifecycle work after the core Room/Execute queues shipped.
> **Design frame:** Agent Lab is a **Developer Agent Console**, not a chat app.
> **Related:** [UI-IA-ROADMAP.md](UI-IA-ROADMAP.md), [HOOK-COMMUNICATE-REFORM.md](HOOK-COMMUNICATE-REFORM.md), [NOTIFICATION-TAXONOMY.md](NOTIFICATION-TAXONOMY.md), [OPS-RUNBOOK.md](OPS-RUNBOOK.md).

---

## 1. Product IA Contract

### Launch Positioning Note

출시 문구에서 `AI 에이전트 오케스트레이션 플랫폼`은 상위 카테고리로만 사용한다. 첫 화면·README·세일즈 문구의 주 메시지는 **Human-in-the-loop 에이전트 개발 콘솔**로 둔다: AI 개발 작업을 `plan.md`로 구조화하고, Human 승인 뒤 worktree에서 격리 실행·merge·Oracle 검증까지 감사 가능하게 잇는 제품.

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

**P1e: Work Decision Surface**

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

### P2 — Verification Speed

**Goal:** make local status legible without waiting for the full slow suite.

- Add or formalize pytest markers:
  - `fast`
  - `integration`
  - `bridge`
  - existing `live`
- Targets:
  - `make test-fast`: pure unit, no bridge, no subprocess-heavy worktree runs.
  - `make test-integration`: git/worktree/subprocess mock integration.
  - `make ci-full`: current full non-live suite + smoke + score.
- Keep current `make ci` behavior only if runtime stays acceptable; otherwise move slow score/bridge groups to `ci-full`.
- Add duration reporting:
  - `pytest --durations=25`
  - optional markdown/json under `sessions/_reports/`.

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

**Next:** P1e — Work Decision Surface.

Why:

- Failure recovery is now consolidated; the next launch-readiness gap is deciding approval/block/verify state without scanning separate panels.
- Work already owns execute judgment, but plan approval and verification state need one top-level decision summary.
- P1c Agent Response Card remains display polish after the core Work decision loop is legible.
