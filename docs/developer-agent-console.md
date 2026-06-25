# Agent Lab — Human-in-the-loop Agent Development Console

> **Document tier:** Tier 3 — current console UI. Index: [README.md](./README.md)

> **현재 UI 기준 문서.** 이전 messenger/iMessage RFP는 [`02-ui-ux-handoff.md`](./02-ui-ux-handoff.md) (legacy)를 참고만 하세요.

## 제품 정의

Agent Lab은 **AI 개발 작업을 계획·승인·격리 실행·검증하는 Human-in-the-loop 에이전트 개발 콘솔**입니다. 메신저가 아니라 세션·`plan.md` 계약·diff·run·verify 결과를 한 작업 흐름으로 묶는 도구입니다.

`AI 에이전트 오케스트레이션 플랫폼`은 상위 카테고리 표현으로만 사용합니다. launch-facing 표면의 주 메시지는 Human 승인, worktree 격리 실행, Oracle 검증입니다.

| 참고 | 가져온 것 |
|------|-----------|
| Conductor / Codex | 담백한 chrome, plan/diff/review 중심 |
| Cursor | Session rail · Workspace · Inspector 3-pane |
| Claude | 긴 문서/대화 가독성 |

## Shell 레이아웃

```text
┌──────────────┬────────────────────────────────┬────────────────┐
│ Session rail │ Workspace tabs + main content  │ Inspector      │
│              ├────────────────────────────────┤ Context/Tasks  │
│ Sessions     │ Transcript · Plan · Review     │ Run/Settings   │
│ Status chip  │ · Run · Artifacts              │                │
│              ├────────────────────────────────┤                │
│              │ Composer                        │                │
└──────────────┴────────────────────────────────┴────────────────┘
```

## Workspace 탭

| 탭 | 내용 |
|----|------|
| **Transcript** | append-only 대화 로그 |
| **Work** | plan.md + execute / review / approval (Plan + Review 통합) |
| **Run** | 턴 topology, orchestration progress |
| **Artifacts** | 세션 산출물 요약 |

### Work 탭 내부 stepper

```
PlanDraft → ReviewNeeded → ExecutePending → MergeVerify → Done
```

| 상태 | 강조 UI |
|------|---------|
| PlanDraft | WorkDecisionPanel + Plan 문서 + 「지금 정리」 |
| ReviewNeeded | WorkDecisionPanel + consensus/dry-run gate + Plan 문서 |
| ExecutePending | WorkDecisionPanel + PlanApprovalPanel / PlanExecutePanel |
| MergeVerify | WorkDecisionPanel + PlanExecutePanel (verify 상태) |
| Done | WorkDecisionPanel verified 상태 + evidence |

상태는 `planMd`, `consensusProposal`, `hasPendingExecution`, `session.run`에서 파생.

### Plan 정보 중복 제거 원칙

1. **Work 헤더 1곳** — freshness / pending agreement / review turn (`WorkStatusBar`)
2. **Work 판단 요약 1곳** — 승인 대상 / 차단 이유 / 검증 상태 (`WorkDecisionPanel`)
3. **Transcript** — consensus system line 1줄 (기존 SSE notice 유지)
4. **Tasks** — full approval UI 중복 없이 Work 점프만
5. **제거** — collapsible 「plan 알림」 패널, composer plan toggle

### Work 레이아웃

```
┌─ WorkStatusBar (stepper + meta) ─────────────┐
├─ WorkDecisionPanel (Approve/Blocked/Verified) ┤
├─ [PlanApprovalPanel] (HUMAN_PENDING) ─────────┤
├─ PlanTabToolbar ────────────────────────────┤
├─ [ExecuteQueue | ConsensusGate] (조건부) ─────┤
├─ PlanDocument ──────────────────────────────┤
└─ PlanExecutePanel (review/execute 영역) ──────┘
```

Inspector **Tasks**는 Work와 분리 — 블로커·objection·goal loop.

## Inspector 탭

| 탭 | 내용 |
|----|------|
| **Context** | 에이전트 컨텍스트 미리보기 |
| **Tasks** | 팀 할 일, goal loop |
| **Run** | cancel, lock 해제, run status |
| **Settings** | 에이전트 cwd/권한 |

## 기본 탭 선택

```ts
workspaceTab =
  running ? "run" :
  hasPendingExecution || hasDryRunDiff ? "review" :
  planMd.trim() ? "plan" :
  "transcript";

inspectorTab =
  hasBlocker ? "tasks" :
  running ? "run" :
  "context";
```

사용자가 탭을 직접 바꾼 뒤에는 **세션 동안 sticky**. auto-switch는 run start/complete, pending approval 등장, blocker 등장 때만.

## 단축키

| 키 | 동작 |
|----|------|
| ⌘N | 새 Session |
| ⌘1–5 | Workspace 탭 |
| ⌘K | Command palette |

## Surface 정책

- **Solid**: transcript, plan, review, run 본문, composer
- **Glass (chrome only)**: titlebar, rail, inspector chrome, popover

토큰: `web/src/styles/tokens.css` (구 `developer-console.css` / `app.css` import 체인은 삭제됨)

## 코드 맵

| 영역 | 파일 |
|------|------|
| Shell | `web/src/App.tsx` |
| Workspace | `web/src/components/RoomChat.tsx` |
| 탭 계약 | `web/src/utils/workspaceTabs.ts`, `hooks/useWorkspaceTabs.ts` |
| Inspector | `web/src/components/InspectorPane.tsx` |
