# Trading Mission — 주간 wire-up (offline lane)

날짜(KST): {{DATE_KST}}

## 목표

1. `research/kr/results` → artifact cards 동기화
2. PASS 후보 검토 → **WireUpDecision** (`active_refs`, `watch_refs`, `blocked_refs`)
3. runtime ingest: `pipeline/data/agentic/wireup_decision.json` + playbook 갱신
4. proposal ingest **없음** (주간은 카드·playbook만)

## 제약

- Read-only pipeline tools; no orders, no LIVE arm
- FAIL verdict는 `active_refs`에 넣지 말 것
- Room 토론 시 1~2라운드 cap; 산출은 `artifacts/wireup_decision.json`

## 합의 (plan.md)

- wireup_ready: true | false
- active_strategies: [ref slug 목록]
- blocking_reason: (cards sync 실패 시)
