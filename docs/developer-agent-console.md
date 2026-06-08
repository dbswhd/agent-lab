# Agent Lab — Developer Agent Console

> **Document tier:** Tier 3 — current console UI. Index: [README.md](./README.md)

> **현재 UI 기준 문서.** 이전 messenger/iMessage RFP는 [`02-ui-ux-handoff.md`](./02-ui-ux-handoff.md) (legacy)를 참고만 하세요.

## 제품 정의

Agent Lab은 **developer agent console**입니다. 메신저가 아니라 세션·plan·diff·run·artifacts를 orchestration하는 작업 도구입니다.

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
| **Plan** | `plan.md` 문서 (`PlanDocument`) |
| **Review** | dry-run diff, 승인, `PlanExecutePanel` |
| **Run** | 턴 topology, orchestration progress |
| **Artifacts** | 세션 산출물 요약 |

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

토큰: `web/src/styles/developer-console.css`, `workspace-shell.css`

## 코드 맵

| 영역 | 파일 |
|------|------|
| Shell | `web/src/App.tsx` |
| Workspace | `web/src/components/RoomChat.tsx` |
| 탭 계약 | `web/src/utils/workspaceTabs.ts`, `hooks/useWorkspaceTabs.ts` |
| Inspector | `web/src/components/InspectorPane.tsx` |
