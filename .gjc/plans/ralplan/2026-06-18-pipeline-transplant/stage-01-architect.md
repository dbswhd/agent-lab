# Architect Review — 파이프라인 이식 (stage_n 1, deliberate)

**Verdict: CLEAR / APPROVE** — Option A는 load-bearing 머지 FSM에 대한 올바른 리스크 자세. 빅뱅 압박검증 결론 타당. 1개 정제(플래그 제거 마일스톤) 필수, blocker 아님.

## Steelman 안티테제 (사용자의 빅뱅 옹호)
사용자는 "통째 재배선"을 명시했다. 가산·플래그 게이트(A)는 그 의도를 배신하는가? — 아니다. **플래그 ON = 4개 컴포넌트 완비 파이프라인**이 곧 사용자가 원한 END STATE이며, 차이는 *경로*(가역적)와 *OFF-parity 안전망*뿐이다. 파괴적 재작성(B)이 주는 추가 가치는 "중간 이중경로 제거"인데, 이는 load-bearing 머지 코드에서 비가역·무안전망 silent-bug 리스크와 1101 lane 상실을 대가로 한다 — 정당화되지 않는다. 직전 Phase 1·2에서 막 분해·커밋한 mission_loop를 곧장 파괴적 재작성하는 것은 그 분해 투자도 무위로 돌린다.

## Tradeoff tension
가역성/안전망(A 선호) vs 단일-경로 청결성(B 선호). 선언적 transition table + 기존 env-플래그 관행이 A를 저비용으로 만들어 이 긴장을 A 쪽으로 해소. 단 **이중 경로(OFF/ON)가 영구화되면** A의 청결성 이점이 소실 → 아래 R1.

## Refinements
- **R1 (필수, WATCH): 플래그 제거 마일스톤 명문화.** `AGENT_LAB_PIPELINE` ON이 안정화되면 default-on 전환 → OFF 경로/플래그 분기 삭제까지를 AC/시퀀싱에 못박아 영구 이중유지부채를 방지. 미완 시 두 오케스트레이션 경로가 상존하는 안티패턴.
- **R2 (확인): 전이 테이블 계약.** 신규 `CLARIFY` 페이즈는 `MissionPhase` Literal + `GuardKind` + `test_runtime_transition_table`(핸들러 importable 검증)에 통합돼야 함 — 통합 리스크 표면, AC7로 커버됨. 양호.

## 검증된 결정
- 합의 역할매핑(특정 에이전트 1:1 대신 Room 합의 라운드 재사용): agent-lab의 Room이 곧 다중에이전트 합의 substrate이므로 타당.
- goal-ledger를 run.json/patch_run_meta에 가산: 기존 영속화 경로 재사용, 신규 스토어 회피 — 타당.
- CLARIFY를 DISCUSS 앞단에 가산 + 구체-신호 스킵: HITL·기존 흐름 보존하며 명료화만 추가 — 타당.

## Status
CLEAR. R1을 final에 반영 조건으로 APPROVE. Critic으로.
