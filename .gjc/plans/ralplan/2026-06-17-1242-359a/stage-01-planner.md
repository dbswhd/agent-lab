# RALPLAN Planner — agent-lab '발산(Divergence)' 턴 프로파일 (stage 1, short mode)

원천: `.gjc/specs/deep-interview-agent-lab-divergence-mode.md` (ambiguity 11%, BELOW_THRESHOLD_EARLY_EXIT). 코드 확인: turn_modes.py, consensus_policy.py, room_consensus_rounds.py, room_parallel_rounds.py, app/server/deps.py, app/server/routers/room.py.

## Principles
1. 기존 수렴(verified/consensus) 경로 불변: 발산은 *추가* 모드이며 BLOCK→execute 409 거버넌스를 약화하지 않는다.
2. 발산 라운드는 독립 병렬 제안을 보존한다 — anchor + "이의 없습니다" 수렴 시퀀스에 진입하지 않는다.
3. discussion-phase에서 정지: 옵션 목록까지가 산출물, execute/plan 연계 없음.
4. 최소 침습: 771 LOC `room_consensus_rounds`를 난도질하지 않고 얇은 분기/신규 경로로 추가.
5. 가치 테스트는 Human 주관 — 도구화/측정 자동화는 1차 비목표.

## Decision Drivers (top 3)
1. 발산 보존 vs 기존 수렴 구조의 충돌 회피 (가장 큰 설계 긴장).
2. 통합 seam의 명확성: turn_modes(프로파일) → mode contract → round 실행 → SSE.
3. 회귀 안전성: verified 모드의 BLOCK/Oracle 거버넌스가 그대로 유지됨을 테스트로 고정.

## Viable Options
**Option A — consensus_policy 변종만 게이팅.** `divergence_consensus_policy()` (min_endorse_agents를 매우 크게→`should_exit_round`의 endorse_threshold 미발화, allow_recombination=False 유지)로 발산 프로파일에서 조기 endorse exit만 억제.
- Pro: 최소 diff, 정책 seam 재사용.
- Con: 여전히 `run_consensus_agent_rounds`의 anchor + "이의 없습니다" 순차 수렴 루프를 타므로 구조적으로 수렴을 밀어붙임 → 진정한 발산 미보존. endorse 억제만으로 불충분.

**Option B — 전용 발산 경로(round-flow 분기). [CHOSEN]** 발산 프로파일 → mode contract(consensus_mode=False, review_mode=False, 신규 `divergence=True`) → `run_consensus_agent_rounds`를 우회하고 `run_parallel_round`(독립 병렬 제안)를 N라운드 사용, anchor/endorse/auto-scribe/BLOCK 전부 스킵, 2~4개 구분 제안을 옵션 목록으로 포맷 후 정지.
- Pro: 발산을 깨끗이 보존(병렬 독립), "옵션 목록서 정지" 충족, 수렴 경로 무손상.
- Con: 신규 코드 경로 추가, 분기점 정의 필요.

**Option C — parallel-rounds 레이어의 최소 플래그.** 공유 round runner에 발산 boolean을 주입해 순차 수렴만 끈다.
- Pro: 가장 작은 diff.
- Con: 발산 관심사가 공유 runner로 누수 → verified/team 등 다른 모드 동작 위험. 회귀 표면 확대.

**Invalidation:** A는 수렴 루프 구조를 못 벗어나 1순위 가치(발산) 미달. C는 공유 경로 오염으로 Principle 1(수렴 경로 불변) 위반 위험. → **B 채택.**

## Chosen Approach — 파일별 변경
1. `src/agent_lab/turn_modes.py`: "발산"/"divergence"를 turn_profile로 인식(`_user_mode`/`_runtime_profile`/`_topology`). `resolve_mode_contract`에 divergence 분기 추가 — consensus_mode=False, review_mode=False, agents=전체, agent_rounds=N(기본 1 parallel + 옵션 1 refine), `ModeContract`에 `divergence: bool` 필드 추가(기본 False). `mode_contract_catalog()`에 발산 항목 추가.
2. `app/server/deps.py`: `TURN_PROFILES` frozenset에 "발산"/"divergence" 추가.
3. `src/agent_lab/consensus_policy.py`: (Option B에서 consensus 루프를 우회하므로 최소) 필요 시 `divergence_consensus_policy()` 헬퍼만 추가하되, 기본 경로는 미진입.
4. `src/agent_lab/room_consensus_rounds.py` / `room_parallel_rounds.py` / 턴 플로우(`room_turn_flow.py`): `contract.divergence`일 때 `run_consensus_agent_rounds` 대신 `run_parallel_round` 기반 발산 러너로 분기; consensus auto-scribe(`consensus_dry_run_proposal`)·BLOCK 게이팅 스킵. **스킵은 divergence 분기 안에서만**.
5. `app/server/routers/room.py`: `POST /api/room/runs`가 발산 프로파일을 contract로 전달, SSE로 옵션 목록 이벤트 방출, execute 트리거 비연계.
6. 출력: 발산 결과 = 2~4개 구분 대안(각: 접근 + 근거 + 무엇이 다른지) 옵션 목록 → 정지.

## Acceptance Criteria (spec 5종 미러, mock-only)
- [ ] '발산' 프로파일을 사용자가 선택 가능 (TURN_PROFILES 멤버 + mode_contract_catalog/GET /api/room/modes 노출).
- [ ] 발산 라운드가 조기 수렴하지 않음 (endorse_threshold/consensus_reached exit 미발화; 에이전트 입장 상이 유지).
- [ ] 접근-수준 구분 대안 2~4개 산출.
- [ ] 옵션 목록서 정지 — execute/merge 자동 진행 없음.
- [ ] mock 실행에서 구분 옵션 N개가 transcript/SSE로 표면화 (≥1 미처 못 한 것은 Human 주관 판정).

## Test Plan (mock-only, AGENT_LAB_MOCK_AGENTS=1)
- Unit: turn_modes divergence contract(consensus_mode=False, divergence=True); TURN_PROFILES 멤버십; mode_contract_catalog 항목; (있다면) divergence_consensus_policy의 endorse-exit 미발화.
- Mock integration: 발산 run이 N개 구분 옵션 산출 + consensus/BLOCK/execute 미진입; verified run은 BLOCK→409 그대로(회귀). 레인: test-fast(unit) + test-integration(run).

## Non-Goals (계획 금지)
execute/복구 마찰, 토큰 비용 효율, execute/plan 파이프라인 연계, ValueMoment 도구화, 배포.

## Risks + Mitigations
- R1 verified 거버넌스 약화: 모든 스킵을 `contract.divergence`에만 게이팅 + verified BLOCK→409 회귀 테스트로 고정.
- R2 "구분 대안" dedup 모호: 요구수준 합격=Human 판정; 경량 distinctness 휴리스틱만, 정밀 dedup은 설계로.
- R3 room_consensus_rounds(771 LOC) 결합도: 침습 편집 대신 얇은 신규 발산 경로 선호, 수렴 경로 무수정.
- R4 catalog/프론트 모드 목록 드리프트: catalog + TURN_PROFILES 테스트 포함.
