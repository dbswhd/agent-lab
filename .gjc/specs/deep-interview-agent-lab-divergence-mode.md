# Deep Interview Spec: agent-lab '발산(Divergence)' 모드 — 본인 도그푸딩 가치 1차

## Metadata
- Interview ID: 27b9b02d-1d77-46c3-a270-f93e54cc131d
- Rounds: 11 (+ Round 0 topology gate)
- Final Ambiguity Score: 11%
- Type: brownfield
- Generated: 2026-06-17T12:36:47.036104+00:00
- Threshold: 0.05
- Threshold Source: default
- Initial Context Summarized: yes
- Status: BELOW_THRESHOLD_EARLY_EXIT (요구사항은 모두 확정; 잔여 11%는 설계 영역으로 ralplan 위임)
- Auto-Researched Rounds: []
- Auto-Answered Rounds: []
- Architect Failures: 0
- Lateral Reviews: 2 (R5 progress 전환 — 4페르소나 spawn 실패; R9 refined 전환 — 사전 인프라 실패로 skip, 수동 폴딩)
- Lateral Panel Failures: 4
- Refined Rounds: [2, 4]
- Closure Overrides: none
- Restated Goal: 명시적 '발산' 턴 프로파일로 조기합의 없는 구분된 대안 2~4개(≥1 미처 못 한 것)를 옵션 목록으로 제시·정지해, 도그푸딩 사용자에게 'raw로는 못 했을' 창의적 발산 가치를 제공 (마찰·토큰·execute·도구화는 1차 비목표)

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.90 | 0.35 | 0.315 |
| Constraint Clarity | 0.88 | 0.25 | 0.220 |
| Success Criteria | 0.88 | 0.25 | 0.220 |
| Context Clarity | 0.88 | 0.15 | 0.132 |
| **Total Clarity** | | | **0.887** |
| **Ambiguity** | | | **0.113 (11%)** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 차별적 가치 (differentiated-value) | active | raw 단일 에이전트 대비 굳이 agent-lab을 쓸 이유 = 다중 에이전트 토론을 통한 발산적/창의적 대안 제시 | 가치=1순위 발산 ideation, 산출물=대안 옵션 목록, 선택=Human, 가치테스트=세션당 미처 못 한 대안 ≥1 |
| 핵심 루프 실효성 (core-loop-efficacy) | active | Room→토론 루프가 1순위 가치(발산)를 실제로 산출 | 발산 턴 프로파일; 합격조건 3종; discussion-phase에서 옵션 목록까지, execute 비연계 |
| 일상 사용 마찰 (daily-friction) | deferred | 매일 사용 시 execute·복구·세션재개 마찰 + 토큰 비용 | 1차 비목표 — 발산 모드 검증 후 별도 차수 (R7 확정) |
| 자기개선 루프 (dogfooding-feedback) | deferred | 사용 중 가치/마찰을 측정해 개발 우선순위로 환류 | 1차 비목표 — ValueMoment는 Human 주관 판단만, 도구화는 나중 (R10 확정) |

## Established Facts
- (R0) production의 정의 = 배포가 아니라 본인 도그푸딩 사용 시의 유용성·실효성  
  evidence: user clarification message
- (R0) 당장 배포/멀티유저/호스팅은 범위 밖, 단일 사용자 로컬 사용 전제  
  evidence: user clarification message
- (R1) 현재 차별적 가치는 약하며 이를 정의/창출하는 것이 1순위 문제  
  evidence: user option pick
- (R2) 차별가치 우선순위: ①토론기반 창의적 아이디어 ②장시간 자율진행 ③격리·검증 머지 ④멀티에이전트 교차검증  
  evidence: user ranking
- (R2) 1순위 가치(발산적 창의 ideation)는 현재 검증중심 아키텍처(Oracle/BLOCK)와 결이 다름 — 관찰  
  evidence: derived observation
- (R3) 가치 테스트 = 정량지표보다 '이건 raw로는 못 했겠다'는 주관적 순간의 빈도(방향만, 미확정). 자기개선 루프의 핵심 작업 = 그 순간 포착 메커니즘  
  evidence: user (option4-leaning, hedged)
- (R4) 실사용 블로커 3종: ①초반 조기합의로 창의 죽음(수렴구조가 차별가치 방해) ②중반 execute·복구·마찰 ③최근 토큰 과소비로 세션 지속 불가  
  evidence: user (Send as-is)
- (R4) 토큰 비용/효율이 지속가능성의 새 제약 (예산·목표 미정)  
  evidence: user
- (R5) MVP-of-usefulness(다시 쓰게 만들 단일 개선) = 조기 합의 억제로 토론이 발산하게 만들기. 차별가치 1순위(창의)와 직결  
  evidence: user pick
- (R6) 창의적 산출물 형태 = 내가 미처 못 한 '대안 접근/설계 옵션' 목록, 선택은 Human. 가치테스트 운영화: 세션당 미처 못 한 대안 ≥1 표면화 여부  
  evidence: user pick
- (R7) 1차 개발 범위 = 발산 모드만. execute·복구 마찰 + 토큰 효율 = 1차 명시적 비목표, 검증 후 별도 차수  
  evidence: user pick
- (R8) 발산 모드 합격 조건 = ①접근-수준 구분 대안 N개 ②조기합의 없이 서로 다른 입장 유지 ③≥1개가 Human이 미처 못 한 접근(가치테스트 통과)  
  evidence: user pick
- (R9) 발산 모드 = discussion-phase 산출물; 출력은 N개 대안 옵션 목록에서 정지; 선택·실행은 Human 별도; 1차 execute/plan 연계 = 비목표  
  evidence: user pick
- (R10) 1차 가치테스트 = Human 주관 판단만(도구화 비목표). 자기개선 루프 도구화 deferral. 1차 = 발산 모드 그 자체  
  evidence: user pick
- (R11) 발산 모드 호출 = 명시적 '발산' 턴 프로파일(turn_modes.py 신규); 출력 = 서로 다른 대안 2~4개  
  evidence: user pick
- (R11) 통합 seam(확인됨): 발산=turn_modes.py 신규 프로파일 + consensus_policy.py(min_endorse_agents/조기 endorse·exit) 억제 변종 + 해당 라운드 consensus auto-scribe/BLOCK 스킵  
  evidence: agent code read (fact)

## Trigger Metadata
- R4: trigger D (scope expansion — 토큰 비용/효율 신규 제약). status: unresolved → 이후 R7에서 명시적 비목표로 deferral되어 해소. 동일 답변이 조기수렴·실행/복구 블로커를 진단 해소해 전체 모호도는 순감소.
- 그 외 라운드: 트리거 없음 (단조 수렴). 모든 가치/스코프 결정은 직접 사용자 판단(refined R2·R4 포함).

## Lateral Review Panel
- R5 (initial→progress 전환): researcher·contrarian·simplifier·architect 4인 병렬 dispatch → 전원 인프라 레벨 spawn 실패(0B, ~1-2s). 폴백: contrarian 렌즈("발산만으로는 가치가 안 된다 — 선택/기준 단계 필요")를 수동 접합해 R6에서 산출물 형태·선택 기준 질문으로 전환.
- R9 (progress→refined 전환): 직전 하드 인프라 실패로 재가동 생략, 수동 폴딩.
- Lateral Panel Failures: 4

## Goal
agent-lab에 명시적 '발산(divergence)' 턴 프로파일을 추가해, Room의 다중 에이전트(Cursor·Codex·Claude)가 조기 합의 없이 서로 다른 입장을 유지하며 접근-수준으로 구분되는 대안 2~4개(그중 ≥1개는 사용자가 미처 못 한 접근)를 옵션 목록으로 제시하고 거기서 멈춤으로써, 사용자가 매일 도그푸딩하며 '이건 raw 단일 에이전트로는 못 했겠다'를 체감하는 창의적 발산 가치를 제공한다.

## Constraints
- 명시적 호출: 사용자가 '발산' 턴 프로파일을 직접 선택 (자동/반자동 아님). `turn_modes.py`의 quick/team/loop 옆 신규 프로파일로 통합.
- 출력: 서로 다른(접근-수준 구분, 단순 표현차 아님) 대안 2~4개.
- 정지 지점: 옵션 목록 제시 후 정지 — 선택·다음 단계는 Human이 별도 수행.
- 조기 합의 억제: `consensus_policy.py`의 N-of-M endorse/조기 exit를 발산 라운드 동안 억제; 해당 라운드 consensus auto-scribe/BLOCK 스킵.
- 가치 테스트: Human 주관 판단(세션당 '미처 못 한 대안 ≥1 표면화' 여부). 별도 도구 없음.
- 단일 사용자·로컬 도그푸딩 전제 (배포·멀티유저·호스팅 전부 범위 밖).

## Non-Goals
- execute/복구/세션 재개 등 일상 사용 마찰 개선 (1차 비목표 → 별도 차수).
- 토큰 효율/비용 최적화 (1차 비목표 → 별도 차수).
- 발산 결과를 plan.md → execute → verify 파이프라인으로 연계 (1차 비목표).
- ValueMoment 포착/기록/대시보드 등 자기개선 루프 도구화 (1차 비목표).
- 배포·코드서명·멀티유저·인증 (이번 'production' 정의에서 명시적 제외).

## Acceptance Criteria
- [ ] '발산' 턴 프로파일을 사용자가 명시적으로 선택할 수 있다 (mode_contract_catalog / GET /api/room/modes에 노출).
- [ ] 발산 라운드에서 에이전트들이 조기 합의(N-of-M endorse/early exit) 없이 서로 다른 입장을 유지한다.
- [ ] 한 번 실행 시 접근-수준으로 구분되는 대안 2~4개가 옵션 목록으로 산출된다 (단순 표현차이는 동일 대안으로 취급).
- [ ] 산출 후 실행/머지로 자동 진행하지 않고 옵션 목록에서 정지한다 (execute 비연계).
- [ ] 도그푸딩 세션에서 사용자가 주관적으로 '≥1개는 내가 미처 못 한 접근'이라고 판단할 수 있는 산출이 재현된다 (가치 테스트).

## Deferrals
- 일상 사용 마찰(execute·복구·세션재개) — 발산 모드 검증 후 별도 차수.
- 토큰 효율/비용 — 발산 모드 검증 후 별도 차수.
- execute 연계 / ValueMoment 도구화 / 자기개선 대시보드 — 별도 차수.
- Convergence Pacing 보류: min-round floor, score-drop cap, confidence dampening 등 인위적 페이싱 브레이크는 추가하지 않음 — 양방향(bidirectional) 스코어링이 페이싱 메커니즘.

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 'production' = 배포 준비도 | 사용자 재정의: 본인 사용 가치/실효성 | value-in-use 기준으로 전환, 배포 비목표 |
| agent-lab은 이미 차별적 가치가 있다 | R1: 굳이 쓸 이유가 약하다(본인 인정) | 차별가치 창출이 1순위 문제로 확정 |
| 차별가치=검증/안전(Oracle·BLOCK) | R2 우선순위: 발산적 창의가 1순위, 교차검증 최하위 | 발산 ideation을 킬러 가치로 재정렬 |
| 합의·BLOCK·Oracle 수렴 구조가 가치를 돕는다 | R4 실사용: 조기 합의가 창의를 죽임 | 수렴 구조가 1순위 가치를 방해 → 발산 모드 필요 |
| 발산만 하면 가치다 | (contrarian 폴딩) 발산엔 선택/기준 필요 | 산출물=대안 옵션 목록 + Human 선택 + ≥1 미처 못 한 것 기준 |
| 1차에 마찰·토큰·도구화까지 | R7·R10: 범위 분산 위험 | 발산 모드만 1차, 나머지 deferral |

## Technical Context (brownfield, agent-code 확인)
- 턴 프로파일/토폴로지: `src/agent_lab/turn_modes.py` — UserMode(quick/team/loop), LoopTopology(route_auto/specialist/verified), `mode_contract_catalog()` → GET /api/room/modes. → 발산 프로파일의 통합 지점.
- 조기 합의 강제: `src/agent_lab/consensus_policy.py` — `ConsensusPolicy(min_endorse_agents, …)` N-of-M endorse + skip/exit 규칙, `default_consensus_policy()`. → 발산 라운드 동안 억제할 정책 지점.
- 합의 라운드 흐름: `src/agent_lab/room_consensus_rounds.py`(~771 LOC), consensus auto-scribe(SSE `consensus_dry_run_proposal`), BLOCK→execute 409 거버넌스. → 발산 라운드에서 스킵 대상.
- 병렬 라운드: `src/agent_lab/room_parallel_rounds.py`. (정확한 최소 개입 함수/플래그는 ralplan 설계 단계에서 확정)
- 백엔드 라우터: `app/server/routers/room.py` (POST /api/room/runs, SSE). 턴 프로파일은 deps의 TURN_PROFILES frozenset에도 등록 필요.

## Ontology (Key Entities — 최종 라운드)
| Entity | Type | Note |
|--------|------|------|
| User(개발자 본인) | core domain | 단일 도그푸딩 사용자, 가치 판정자 |
| AgentLab | core domain | 콘솔 |
| Room/Agents(Debate) | core domain | Cursor·Codex·Claude 토론 |
| DivergenceMode | core domain | 1차 산출물 — 발산 턴 프로파일 |
| DifferentiatedValue | core domain | 발산적 창의 = 굳이 쓸 이유 |
| CreativeIdeation | core domain | 발산적 아이디어 생성 |
| AlternativeApproach | core domain | 산출물 단위 = 구분되는 대안 옵션 |
| ValueMoment | supporting | 'raw로 못 했을' 주관적 순간 (가치 테스트, 도구화는 deferred) |
| RawAgents | external system | 비교 대안 (단독 Cursor/Codex) |
| AutonomousProgress / CostBudget / Plan / Execute(Worktree) / Oracle/Verify | supporting/deferred | 1차 비목표 영역 |

## Ontology Convergence
| Round | Entity Count | Stability Ratio | Matching |
|-------|-------------|-----------------|----------|
| 1 | 8 | - |  |
| 2 | 10 | 80% | matched 8 by name; new: CreativeIdeation, AutonomousProgress |
| 3 | 11 | 91% | matched 10 by name; new: ValueMoment |
| 4 | 12 | 92% | matched 11 by name; new: CostBudget |
| 5 | 12 | 92% | no new entities; all 12 stable |
| 6 | 13 | 92% | matched 12; new: AlternativeApproach |
| 7 | 14 | 93% | matched 13; new: DivergenceMode |
| 8 | 14 | 100% | no new entities; all 14 stable (converged) |
| 9 | 14 | 100% | no new entities; all 14 stable |
| 10 | 14 | 100% | no new entities; all stable |
| 11 | 14 | 100% | no new entities; all stable |

## Interview Transcript
<details>
<summary>Full Q&A (11 rounds + Round 0 topology)</summary>

**Round 0 (Topology):** 4 컴포넌트 확정 — 차별가치·핵심루프·일상마찰·자기개선.

### Round 1 — differentiated-value / goal
**Q:** 최근 굳이 agent-lab을 켠/켜고 싶었던 작업과 raw 대신 택한 이유
**A:** 솔직히 아직 굳이 쓸 이유가 약하다 — 그게 문제다
**Ambiguity:** 76% (Goal 0.2, Con 0.15, Crit 0.1, Ctx 0.7)

### Round 2 — differentiated-value / goal
**Q:** agent-lab이 'raw로는 안 되는' 순간 = 킬러 가치 후보 + 우선순위
**A:** 차별가치=4복합 / 우선순위 ①토론기반 창의적 아이디어 ②장시간 자율진행 ③격리·검증 머지 ④멀티에이전트 교차검증
**Ambiguity:** 70% (Goal 0.3, Con 0.2, Crit 0.15, Ctx 0.7)

### Round 3 — dogfooding-feedback / criteria
**Q:** '이번 주 agent-lab은 쓸모 있었다'를 무엇으로 판정? 특히 토론기반 창의 아이디어가 나왔는지
**A:** 아직 잘 모르겠으나 4번에 가까움 = 정량지표보다 '이건 raw로 못 했겠다' 주관적 순간의 빈도
**Ambiguity:** 69% (Goal 0.3, Con 0.2, Crit 0.2, Ctx 0.7)

### Round 4 — core-loop-efficacy / goal
**Q:** 지금까지 실제 사용 정도 + Room 토론이 발산적이었나 수렴해버렸나
**A:** 초반 조기합의로 창의 죽음 / 중반 execute·복구·마찰 어려움 / 최근 토큰 과소비로 오래 못 씀
**Ambiguity:** 63% (Goal 0.4, Con 0.25, Crit 0.25, Ctx 0.7)

### Round 5 — dogfooding-feedback / goal
**Q:** '이거 하나만 좋아져도 다시 쓰겠다'는 단일 개선
**A:** 조기 합의를 막아 토론이 발산하게 만드는 것 (1순위 가치 살리기)
**Ambiguity:** 56% (Goal 0.5, Con 0.35, Crit 0.25, Ctx 0.7)

### Round 6 — differentiated-value / criteria
**Q:** 창의적 산출물의 형태 + 좋은 것 선택 방식 (패널 맹점: 발산엔 선택단계 필요)
**A:** 내가 미처 못 한 '대안 접근/설계 옵션' 목록 — 선택은 내가 한다
**Ambiguity:** 52% (Goal 0.56, Con 0.39, Crit 0.35, Ctx 0.7)

### Round 7 — daily-friction / constraints
**Q:** 나머지 블로커(마찰·토큰)를 1차 범위에 넣을지
**A:** 1차는 발산 모드만. 마찰·토큰은 검증 후 별도 차수 (지금은 비목표)
**Ambiguity:** 40% (Goal 0.67, Con 0.53, Crit 0.53, Ctx 0.7)

### Round 8 — core-loop-efficacy / criteria
**Q:** 발산 모드 한 번 돌렸을 때 '제대로 발산'의 합격 조건
**A:** 셋 다: 구분되는 대안 N개 + 조기수렴 안 함 + ≥1개 미처 못 한 것
**Ambiguity:** 33% (Goal 0.73, Con 0.58, Crit 0.68, Ctx 0.7)

### Round 9 — core-loop-efficacy / constraints
**Q:** 발산 모드의 끝은 어디 — 옵션 목록에서 멈추나, plan→execute로 잇나
**A:** 옵션 목록에서 멈춘다 — 선택·실행은 내가 별도로 (1차 execute 연계 비목표)
**Ambiguity:** 28% (Goal 0.75, Con 0.67, Crit 0.72, Ctx 0.7)

### Round 10 — dogfooding-feedback / goal
**Q:** ValueMoment를 1차에서 도구화할지 / 주관 판단만 둘지
**A:** 1차는 주관 판단만 — 도구화는 비목표(나중). 발산 모드 자체에 집중
**Ambiguity:** 16% (Goal 0.86, Con 0.85, Crit 0.83, Ctx 0.8)

### Round 11 — core-loop-efficacy / goal
**Q:** 발산 모드 호출 방식 + 대안 개수
**A:** 명시적 '발산' 턴 프로파일 + 대안 2~4개
**Ambiguity:** 11% (Goal 0.9, Con 0.88, Crit 0.88, Ctx 0.88)

</details>
