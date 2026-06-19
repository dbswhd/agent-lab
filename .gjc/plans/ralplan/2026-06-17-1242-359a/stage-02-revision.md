# RALPLAN Planner Revision — stage 2 (Architect+Critic 반영)

이전 stage-01 계획에 Architect/Critic 피드백 5건을 반영. 변경분만 기재(나머지는 stage-01 유지).

## Options에 추가 — Option D: 프롬프트-온리 baseline
발산 전용 system instruction("서로 다른 접근 제시, 조기 동의 금지")만 주입하고 메커니즘은 불변.
- Pro: 제로 구조 변경, 가장 싼 가설.
- **Invalidation:** `consensus_policy.should_exit_round`의 `endorse_count >= min_endorse_agents(=2)`가 여전히 라운드를 조기 종료시키고, `run_consensus_agent_rounds`의 anchor + "이의 없습니다" 시퀀스가 수렴을 강제한다. 프롬프트만으론 합격기준 #2(조기수렴 안 함) 미달. → **메커니즘(B) + 프롬프트 둘 다 필요.**

## Principle 4 긴장 해소 (Option B 재정의)
발산 러너는 병렬 로직을 **재구현하지 않고 `room_parallel_rounds.run_parallel_round`를 재사용**한다. 발산 경로 = (a) 기존 parallel round runner 호출 + (b) consensus anchor/endorse/scribe/BLOCK 분기 미진입 + (c) 옵션 목록 포맷. 신규 코드는 얇은 오케스트레이션 + 포맷터로 한정, 공유 runner·수렴 경로 무수정.

## 파일별 변경 — 추가/보강
- `src/agent_lab/agents/prompts.py` (신규 반영): 발산 전용 instruction 추가 — 조기 동의 금지, 접근-수준 차별화 요구, 합의 금지. context_bundle/reply_policy가 발산 contract일 때 이 instruction을 주입.
- `src/agent_lab/turn_modes.py`: (stage-01과 동일) + `patch_run_mode_contract`/run.json 직렬화가 신규 `divergence` 필드를 보존하는지 점검·테스트.
- 정지 경로: router뿐 아니라 **consensus auto-scribe(`consensus_dry_run_proposal`)·plan 합성(`synthesize_session_plan`) 트리거가 발산 run에서 미발화**함을 명시적으로 보장(분기 가드 + 테스트).
- 나머지(deps TURN_PROFILES, consensus_policy 변종 옵션, mode_contract_catalog, room.py SSE)는 stage-01 유지.

## Risks 추가
- **R5 에이전트 프롬프트 수렴 편향:** 기존 프롬프트가 합의/plan 합성을 유도 → 메커니즘만 끄면 여전히 수렴. 완화: 발산 전용 instruction(위) + 통합 테스트가 "메커니즘 미발화 **AND** 실제 상이 입장 N개 유지"를 둘 다 검증.

## Acceptance Criteria 보강
- [ ] #2 검증 = (a) endorse_threshold/consensus_reached exit 미발화 **AND** (b) 산출 옵션들이 접근-수준으로 상이(mock에서 N개 구분 제안 관측).
- [ ] 발산 run에서 auto-scribe/plan-합성/BLOCK/execute 어느 것도 트리거되지 않음 (회귀: verified run은 BLOCK→409 유지).

## Test Plan 보강
- Unit 추가: 발산 contract 직렬화 라운드트립(run.json); 발산 instruction이 발산 contract에서만 주입.
- Mock integration 추가: 발산 run → N개 구분 옵션 + scribe/plan/BLOCK/execute 0회; verified run BLOCK→409 회귀 1건.
