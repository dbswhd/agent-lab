# Work Tab IA

Plan과 Review를 하나의 **Work** surface로 통합한다. 사용자는 “Plan 탭 vs Review 탭”이 아니라 **지금 이 작업이 어떤 단계인지**를 본다.

## 메인 탭

| Tab | 역할 |
|-----|------|
| Transcript | 전체 세션 대화 기록 |
| Work | plan.md + execute/review/approval |
| Run | 현재 턴 실행 (topology + 에이전트 출력) |
| Artifacts | 세션 산출물 |

## Work 내부 상태 (stepper)

```
PlanDraft → ReviewNeeded → ExecutePending → MergeVerify → Done
```

| 상태 | 강조 UI |
|------|---------|
| PlanDraft | WorkDecisionPanel + Plan 문서 + 「지금 정리」 |
| ReviewNeeded | WorkDecisionPanel + consensus/dry-run gate + Plan 문서 |
| ExecutePending | WorkDecisionPanel + PlanApprovalPanel/PlanExecutePanel |
| MergeVerify | WorkDecisionPanel + PlanExecutePanel (verify 상태) |
| Done | WorkDecisionPanel verified 상태 + evidence |

상태는 `planMd`, `consensusProposal`, `hasPendingExecution`, `session.run`에서 파생한다.

## Plan 정보 중복 제거 원칙

1. **Work 헤더 1곳**: freshness / pending agreement / review turn — `WorkStatusBar`
2. **Work 판단 요약 1곳**: 승인 대상 / 차단 이유 / 검증 상태 — `WorkDecisionPanel`
3. **Transcript**: consensus system line 1줄 (기존 SSE notice 유지)
4. **Tasks**: full approval UI를 중복하지 않고 Work 점프만 제공
5. **제거**: collapsible 「plan 알림」 패널, composer plan toggle (Work toolbar만)
6. **단일 CTA**: 「지금 정리」는 PlanTabToolbar 버튼 하나

## 레이아웃

```
┌─ WorkStatusBar (stepper + meta) ─────────────┐
├─ WorkDecisionPanel (Approve/Blocked/Verified)┤
├─ [PlanApprovalPanel] (HUMAN_PENDING) ─────────┤
├─ PlanTabToolbar ────────────────────────────┤
├─ [ExecuteQueue | ConsensusGate] (조건부) ─────┤
├─ PlanDocument ──────────────────────────────┤
└─ PlanExecutePanel (review/execute 영역) ──────┘
```

Inspector **Tasks**는 Work와 분리 — 블로커·objection·goal loop.
