# RALPLAN Final Plan (pending approval) — agent-lab '발산(Divergence)' 턴 프로파일

원천 spec: `.gjc/specs/deep-interview-agent-lab-divergence-mode.md` · 합의: Planner→Architect→Critic, iteration 2에서 APPROVE.

## ADR
- **Decision:** agent-lab에 명시적 '발산(divergence)' 턴 프로파일을 추가한다. 발산 run은 `run_parallel_round`를 재사용한 독립 병렬 제안 경로로 동작하며, consensus anchor/endorse·auto-scribe·BLOCK 게이팅을 발산 분기에 한해 우회하고, 2~4개 접근-수준 구분 대안을 옵션 목록으로 산출한 뒤 정지한다(execute 비연계). 발산 전용 system instruction을 함께 주입한다.
- **Drivers:** (1) 발산 보존 vs 기존 수렴 구조 충돌 회피, (2) 통합 seam 명확성(turn_modes→contract→round→SSE), (3) verified BLOCK→409 거버넌스 회귀 안전성.
- **Alternatives considered:** A(consensus_policy 변종만)·C(공유 runner 플래그)·D(프롬프트-온리). A는 수렴 루프 구조 미탈출, C는 공유 경로 오염(P4 위반), D는 endorse-threshold 메커니즘이 여전히 조기 종료 → 모두 단독으론 부족.
- **Why chosen (B+프롬프트):** 메커니즘 우회(run_parallel_round 재사용) + 발산 instruction을 결합해야 합격기준 #2(조기수렴 안 함)·#3(구분 대안)을 동시 충족하며, 수렴 경로를 무손상으로 유지.
- **Consequences:** 두 번째(얇은) 라운드 경로 추가; ModeContract에 `divergence` 필드(기본 False) 신설로 전 생성 분기·직렬화 점검 필요; 발산 instruction과 3에이전트 역할 프롬프트의 우선순위 설계 필요.
- **Follow-ups (별도 차수, 1차 비목표):** execute/복구 마찰, 토큰 효율, execute/plan 연계, ValueMoment 도구화, 배포. distinctness 휴리스틱 정밀화. 발산 instruction×역할 프롬프트 충돌 조정.

## 구현 계획 (mock-only 검증)
1. `app/server/deps.py`: `TURN_PROFILES`에 "발산"/"divergence" 추가.
2. `src/agent_lab/turn_modes.py`: turn_profile 인식 + `resolve_mode_contract` divergence 분기(consensus_mode=False, review_mode=False, agents=전체, agent_rounds=N), `ModeContract.divergence: bool=False` 신설, `mode_contract_catalog()` 항목 추가; `patch_run_mode_contract`/run.json 직렬화 라운드트립 보존.
3. `src/agent_lab/agents/prompts.py` (+ context_bundle/reply_policy 주입): 발산 전용 instruction(조기 동의 금지·접근 차별화 요구), 발산 contract에서만 주입.
4. 라운드 경로(`room_turn_flow.py`/`room_parallel_rounds.py`): `contract.divergence`일 때 `run_consensus_agent_rounds` 대신 `run_parallel_round` 재사용 발산 러너로 분기; consensus anchor/endorse·`consensus_dry_run_proposal` auto-scribe·`synthesize_session_plan`·BLOCK 미트리거(분기 가드). 스킵은 divergence 분기에서만.
5. `app/server/routers/room.py`: `POST /api/room/runs`가 발산 프로파일 전달, SSE 옵션 목록 방출, execute 비연계.
6. 출력 포맷터: 2~4개 대안(접근+근거+차이점) 옵션 목록 → 정지.

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] '발산' 프로파일 선택 가능(TURN_PROFILES + GET /api/room/modes 노출).
- [ ] #2 = endorse_threshold/consensus_reached exit 미발화 **AND** 산출 옵션이 접근-수준 상이(N개 구분 관측).
- [ ] 접근-구분 대안 2~4개 산출.
- [ ] 옵션 목록서 정지 — auto-scribe/plan-합성/BLOCK/execute 0회.
- [ ] verified run은 BLOCK→409 유지(회귀).

## Test Plan
- Unit: divergence contract(consensus_mode=False, divergence=True)·직렬화 라운드트립; TURN_PROFILES 멤버십; mode_contract_catalog 항목; 발산 instruction이 발산 contract에서만 주입.
- Mock integration: 발산 run → N개 구분 옵션 + scribe/plan/BLOCK/execute 0회; verified run BLOCK→409 회귀 1건. 레인: test-fast + test-integration.

## Non-Goals
execute/복구 마찰 · 토큰 비용 효율 · execute/plan 연계 · ValueMoment 도구화 · 배포.

## Risks
- R1 verified 거버넌스 약화 → 스킵을 `contract.divergence`에만 게이팅 + BLOCK→409 회귀 테스트.
- R2 dedup 모호 → Human 판정 합격선, 경량 휴리스틱만.
- R3 결합도 → run_parallel_round 재사용, 수렴 경로 무수정.
- R4 catalog/프론트 드리프트 → catalog+TURN_PROFILES 테스트.
- R5 프롬프트 수렴 편향 → 발산 instruction + 상이입장 유지 검증 테스트.

## 상태: PENDING APPROVAL — 실행은 별도 승인 필요. 자동 실행/위임 없음.
