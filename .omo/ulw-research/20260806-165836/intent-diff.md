# Intent diff

Run: 2026-08-06 · Status: closed

| intent_id | expected truth | observed reality | diff | violated invariant | intent source | supporting observations | status | claim ids |
|---|---|---|---|---|---|---|---|---|
| I1 | 기존 보고서의 8개 후보와 중복되지 않는 GitHub OSS 후보가 있다 | 10개 active entries와 별도 historical/reject 집합을 구현 gate로 선별 | 없음; 12–15개 목표는 상한으로 처리 | 없음 | 사용자 추가조사 요청 + prior synthesis | O2–O24 | true | C1,C2,C12,C13 |
| I2 | 각 후보는 README가 아니라 구현 코드와 현재 유지보수 상태로 평가할 수 있다 | active 후보마다 pinned source/test anchor, SHA, 2026-08-06 metadata가 있음; 외부 suite 미실행은 한계로 명시 | production readiness는 주장하지 않음 | 없음 | “참고할만한 오픈소스 슈퍼샘플” | O16–O24 + V1 | true | C3–C14,C16 |
| I3 | Agent Lab에 흡수할 부분과 거부할 부분을 구분할 수 있다 | pattern/experiment/reference/watch/historical taxonomy와 8개 최소 spike를 제시 | framework 전체 채택 대신 existing SSOT 보존으로 범위 축소 | Human Inbox, Oracle, restore-then-stop, worktree/merge authority 보존 | Agent Lab AGENTS/SSOT + user request | O15 + refinement groups | true | C2–C11,C15 |
