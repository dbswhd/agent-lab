# Intent diff

| intent_id | expected truth | observed reality | diff | violated invariant | intent source | supporting observations | status | claim ids |
|---|---|---|---|---|---|---|---|---|
| I1 | 최근 업계 변화가 Agent Lab의 mission lifecycle과 직접 연결된다 | MCP 2026-07-28, ACP v1, trajectory eval, operator UX가 각각 plugin/runtime/adapters/eval/UI에 대응 | 연결 확인 | 없음 | 사용자 요청, PROJECT.md | O1,O4,O5,O6 | true | C1,C4,C5 |
| I2 | 슈퍼샘플은 공개 근거와 실제 구현을 함께 가진다 | 6개 공개 저장소를 SHA 고정으로 직접 확인 | 충족 | 없음 | 사용자 요청, NORTH-STAR.md | O2,O7-O12 | true | C2 |
| I3 | 추천은 기존 shipped 기능과 중복되지 않고 다음 실험으로 이어진다 | shipped matrix 대비 호환성 감사, event spine, dialogue eval, ACP probe만 신규 | 충족 | 없음 | EXTERNAL-REFS-TRACEABILITY.md | O3,O13-O15 | true | C3,C6 |
