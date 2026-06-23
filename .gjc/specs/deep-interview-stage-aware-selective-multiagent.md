# Deep Interview Spec: 단계-인지 선택적 멀티에이전트 + anti-drift 방어

## Metadata
- Interview ID: di-agentlab-direction-0001
- Rounds: 6 (+ Round 0 topology)
- Final Ambiguity Score: 16.5%
- Type: brownfield (agent-lab)
- Threshold: 0.05
- Threshold Source: default
- Status: BELOW_THRESHOLD_EARLY_EXIT (user-accepted)
- Lateral Reviews: 2 (R2 progress, R5 refined; inline 3-lens)
- Restated Goal: confirmed (see Goal)

## Clarity Breakdown (overall = min across active components)
| Dimension | Score | Weight | Weighted |
|---|---|---|---|
| Goal | 0.85 | 0.35 | 0.2975 |
| Constraints | 0.82 | 0.25 | 0.2050 |
| Success Criteria | 0.85 | 0.25 | 0.2125 |
| Context | 0.80 | 0.15 | 0.1200 |
| Total Clarity | | | 0.835 |
| Ambiguity | | | 0.165 |

## Topology
| Component | Status | Description | Coverage / Deferral |
|---|---|---|---|
| 단계-인지 선택적 멀티에이전트 | active | phase별 단일 vs 패널 라우팅 (mode_router phase-aware 확장) | Goal 0.90 / Con 0.82 / Cri 0.85 |
| anti-drift 방어 | active | 장기세션 흔들림·편향·에코챔버 방어 (재주입 + 만장일치-의심 red-team; fresh-eyes=감사패널 좌석) | Goal 0.85 / Con 0.88 / Cri 0.85 |
| 동적 모델 풀 + 주권 | deferred | dynamic_room 연장, Fugu식 비종속 | Round 0 사용자 확정 deferral |

## Established Facts
1. (R1) 단계 = 기존 FSM phase(mission_loop/plan_workflow) 직접 매핑, 단일/패널은 phase별 결정적 규칙 테이블.
2. (R2) anti-drift MUST = A(상태 외부화 재주입) + B(만장일치-의심 강제 red-team). C(fresh-eyes)는 컴포넌트①의 감사=패널 단계 좌석으로 흡수.
3. (R3) 기존 mode_router.select_mode를 phase-aware로 확장(새 레이어 X), execute/단순=solo 최소형. 사용자 명시 turn profile 선택은 라우팅 기본값을 항상 오버라이드 -> additive·OFF-parity.
4. (R4) 수용 = 결정적 발동 단위테스트(게이트: N턴 재주입, 만장일치->red-team 1회, OFF-parity 회귀) + 텔레메트리(관찰용).
5. (R5) phase->mode 표: 패널=DISCUSS/DRAFT/PEER_REVIEW/REFINE/divergence; 단일=EXECUTE/dry-run/merge·verify/quick/scribe; CLARIFY=하이브리드(clarity 엔진 단일 기본, ambiguity 높을 때만 패널).
6. (R6) 발동 = B는 패널 단계에서만; A는 패널=매 턴, solo=가벼운 1회. 설정값 없는 단순 기본.

## Goal
agent-lab의 멀티에이전트를 '전 구간 동시'에서 '단계-인지 선택적'으로 전환한다 - 기존 mode_router를 phase-aware로 확장해 수렴·실행 단계(EXECUTE/merge·verify/quick/scribe)는 단일 모델, 발산·감사 단계(DISCUSS/DRAFT/PEER_REVIEW/REFINE/divergence)는 패널로 라우팅하고(사용자 명시 선택은 항상 오버라이드), 그 패널·장기 세션에 anti-drift 방어(상태 외부화 재주입 + 만장일치-의심 red-team, fresh-eyes critic을 감사 패널 좌석으로)를 결정적 발동 단위테스트 게이트와 OFF-parity로 추가한다. 동적 모델 풀·주권은 이번 범위에서 defer.

## Constraints
- 기존 mode_router.select_mode의 확장으로 구현 - 새 병렬 라우팅 레이어 금지.
- 사용자 명시 turn profile 선택은 라우팅 기본값을 항상 오버라이드.
- 전부 additive + 플래그 게이트 + OFF-parity(플래그 OFF 시 바이트 동일).
- B는 패널 단계만; A는 패널=매 턴/solo=가벼운 1회.
- fresh-eyes critic은 감사 패널 좌석으로 구성(별도 주기 투입 X).
- consensus/divergence/verified-loop/approval spine(_mirror_verified_loop_status/approve_plan) 불변.

## Non-Goals
- 학습된 오케스트레이터 모델 제작(Fugu/Trinity/Conductor) - 결정적 화이트박스 규칙으로.
- 동적 모델 풀/주권(dynamic_room 연장) - defer.
- 드리프트 감소 행동 메트릭을 수용 게이트로 - 텔레메트리는 관찰용.
- 턴마다 동적 수렴/발산 분류 - 결정적 phase 매핑으로 대체.

## Acceptance Criteria
- [ ] phase->mode 매핑대로 라우팅되는 단위테스트.
- [ ] 사용자 명시 선택이 라우팅 기본값을 오버라이드하는 테스트.
- [ ] 플래그 OFF 시 OFF-parity 회귀 테스트.
- [ ] A: 패널 단계에서 established_facts/ledger 블록 매 턴 재주입 검증.
- [ ] B: 패널 단계 만장일치 시 red-team 1라운드 강제(solo는 미발동) 테스트.
- [ ] fresh-eyes critic이 감사 패널에 원목표+산출물만으로 참여하는 테스트.
- [ ] RoutingDecisionLog 텔레메트리 기록(관찰용).
- [ ] 전체 fast lane green + mypy/ruff clean.

## Deferrals
- 동적 모델 풀 + 주권 (Round 0 사용자 확정).
- 재주입 N 튜닝 - 기본 단순 규칙 후 텔레메트리로 후속.
- Convergence Pacing 브레이크 미도입 - 양방향 스코어링이 페이싱.

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|---|---|---|
| 새 라우팅 레이어 필요 | 기존과 중복/충돌 | mode_router 확장 |
| 멀티는 항상 3개 동시 | Fugu: 적응적이 효율 | 발산·감사만 패널 |
| 만장일치는 좋은 신호 | 에코챔버 위험 | 만장일치=의심 red-team |
| 드리프트는 모델로만 방어 | 학습모델 불가 | 구조로 방어 |
| anti-drift 전 턴 적용 | 과발동·비용 | 패널 단계 집중 |

## Technical Context (brownfield)
- 라우팅: mode_router.select_mode (phase-aware 확장 대상).
- 단계 출처: mission_loop/mission_advance FSM, plan_workflow FSM, turn_modes(team/discuss/divergence/loop/verified).
- anti-drift substrate: clarity.established_facts/format_facts_block, ledger, consensus_gate/room_consensus_rounds(만장일치 감지), ralplan fresh architect/critic 패턴(fresh-eyes 원형), divergence profile.
- 승인 spine(불변): plan_workflow._mirror_verified_loop_status, approve_plan.
- 직전 작업: CLARIFY 통합(clarity 엔진이 server clarifier 백킹) - CLARIFY 하이브리드와 정합.

## Ontology (Key Entities)
| Entity | Type | Relationships |
|---|---|---|
| Stage/Phase | core | RuleTable로 Mode 매핑 |
| Router(mode_router) | core | Phase 읽고 UserOverride 존중 |
| Panel | core | 발산·감사 Phase, fresh-eyes 좌석 포함 |
| SoloMode | core | 수렴·실행 Phase |
| AntiDriftGuard | core | 재주입(A)+만장일치의심(B), 패널/장기세션 |
| FreshEyesCritic | supporting | 감사 패널 좌석, cold context |
| EstablishedFacts/Ledger | supporting | A가 재주입 |
| RedTeamRound | supporting | B가 패널 단계서 강제 |
| RoutingDecisionLog | telemetry | 관찰용(게이트 X) |
| UserOverride | supporting | Router 기본값보다 우선 |

## Ontology Convergence
| Round | Entities | Stability |
|---|---|---|
| 1 | 11 | N/A |
| 2 | 12 | ~0.82 |
| 3 | 13 | ~0.85 |
| 4-6 | 13 | ~0.90 -> 0.95 |

## Interview Transcript
Round 0: 토폴로지 - ③ 동적 풀 defer, ①② 집중.
Round 1 (C① Goal): 단계=FSM phase 직접 매핑. 100->72%.
Round 2 (C② Goal): A+B MUST, C=감사패널 좌석. 72->53%.
Round 3 (C① Constraints): mode_router 확장 + 사용자 오버라이드. 53->48%.
Round 4 (C② Criteria): 발동 단위테스트(게이트)+텔레메트리. 48->36%.
Round 5 (C① Goal/Cri): phase->mode 표 확정. 36->28%.
Round 6 (C② Constraints): 패널 단계 집중+단순 기본. 28->16.5%.
