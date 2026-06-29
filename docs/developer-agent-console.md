# Agent Lab — Human-in-the-loop Agent Development Console

> **Document tier:** Tier 3 — current console UI. Index: [README.md](./README.md)

> **현재 UI 기준 문서.** 이전 messenger/iMessage RFP는 [`02-ui-ux-handoff.md`](./02-ui-ux-handoff.md) (legacy)를 참고만 하세요.

## 제품 정의

Agent Lab은 **AI 개발 작업을 계획·승인·격리 실행·검증하는 Human-in-the-loop 에이전트 개발 콘솔**입니다. 메신저가 아니라 세션·`plan.md` 계약·diff·run·verify 결과를 한 작업 흐름으로 묶는 도구입니다.

## Shell 레이아웃

```text
┌──────────────┬────────────────────────────────┬────────────────┐
│ Session rail │ Transcript                     │ Workbench      │
│              ├────────────────────────────────┤ Overview       │
│ Sessions     │ ComposerEventStack + Composer  │ Tools (Diff…)  │
└──────────────┴────────────────────────────────┴────────────────┘
```

## Workspace

| 영역 | 역할 |
|------|------|
| **Transcript** | append-only 대화 로그 |
| **ComposerEventStack** | Human Inbox resolve · plan approval · execute queue · consensus gate · `PlanExecutePanel` |
| **Composer** | message · preset · Plan toggle · attachments |
| **ComposerNoticeCard** | recovery · connection · non-actionable alerts only |
| **ComposerActivityPanel** | collapsible notification feed (구 Inbox Activity) |

## Workbench (Inspector)

| 모드 | 내용 |
|------|------|
| **Overview** | mission · plan meta · context layers · diagnostics |
| **Tools** | Diff · Files · Background · Preview · Terminal |

Work / Inbox / Tasks **탭은 제거됨**. execute judgment는 composer stack SSOT.

## Tools 탭

| 탭 | 내용 |
|----|------|
| **Diff** | active execution `SideBySideDiff` |
| **Files** | workspace files · `plan.md` |
| **Background** | bg tasks |
| **Preview** / **Terminal** | dev preview · xterm |

## 기본 탭 선택

- dry-run diff 있음 → **Diff**
- else → **Transcript** (composer stack이 pending action 처리)

## 코드 맵

| 영역 | 파일 |
|------|------|
| Shell | `web/src/App.tsx` |
| Workspace | `web/src/components/RoomChat.tsx` |
| Event stack | `web/src/components/ComposerEventStack.tsx` |
| Execute | `web/src/components/PlanExecutePanel.tsx` |
| Tabs | `web/src/utils/workspaceTabs.ts` |
