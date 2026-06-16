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

**Next:** P1c — Agent Response Card MVP from existing envelope / `communicate_meta`.

Why:

- P1a now exposes hook runs, envelope flags, and hook/contract Activity routing.
- P1b now persists a session response contract and injects its guidance into agent payloads.
- The next product gap is display: Transcript still mostly renders markdown rather than a parsed response card.
