# Deep Interview Spec: agent-lab에 GJC 파이프라인 체계 이식

## Metadata
- Interview ID: 27d4d624-da76-4ea5-a4f4-34ffcf5d6a9a
- Rounds: 4 (+ Round 0 토폴로지)
- Final Ambiguity Score: 37%
- Type: brownfield
- Generated: 2026-06-18T08:48:11Z
- Threshold: 0.05
- Threshold Source: default
- Initial Context Summarized: no
- Status: BELOW_THRESHOLD_EARLY_EXIT
- Auto-Researched Rounds: []
- Auto-Answered Rounds: []
- Architect Failures: 0
- Lateral Reviews: 1 (Round 1, initial→progress, 오케스트레이터 직접 적용)
- Lateral Panel Failures: 1 (subagent 디스패치 결함 — 패널을 오케스트레이터가 직접 lens 적용으로 대체)
- Refined Rounds: [2]
- Closure Overrides: 1 (조기 종료 — 잔여 gap을 ralplan 타당성 게이트로 라우팅)
- Restated Goal: agent-lab의 mission_loop 오케스트레이션을 deep-interview식 명료화 게이트(전용 LLM scorer) → ralplan식 합의(기존 Room 융합) → ultragoal식 목표추적 실행(기존 worktree 격리·Oracle 검증 유지)으로 전면 재배선하고, 오케스트레이터가 상황에 맞는 모드를 자율 선택하되 기존 Human 질문·승인 게이트는 그대로 보존한다.

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.75 | 0.35 | 0.2625 |
| Constraint Clarity | 0.60 | 0.25 | 0.15 |
| Success Criteria | 0.45 | 0.25 | 0.1125 |
| Context Clarity | 0.72 | 0.15 | 0.108 |
| **Total Clarity** | | | **0.633** |
| **Ambiguity** | | | **0.367 (37%)** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 명료화 게이트 (deep-interview 상응) | active | 작업 착수 전 모호성 게이트 (신규) | 전용 LLM scorer 네이티브 구현, 임계 아래면 통과. 점수 산정 세부는 ralplan |
| 합의 엔진 (ralplan 상응) | active | 기존 Room 다중에이전트를 합의-until-agreement로 정렬 | Room 유지·승격. Cursor/Codex/Claude→역할 매핑은 ralplan |
| 목표추적 실행 (ultragoal 상응) | active | mission_loop 실행 백본 + 내구성 goal 원장 + 품질 게이트 | worktree 격리·Oracle 검증·crash_recovery 유지. 원장 저장소는 ralplan |
| 자율 모드 라우팅 + 습관적 규율 | active | 상황→모드 자율 선택 + 게이팅 습관화 (신규 메타) | 자율=모드 선택, Human 질문·승인 게이트 보존. 라우터 결정 신호는 ralplan |

## Established Facts
- (R1) 이식 대상 = agent-lab **제품 오케스트레이션**(mission/room) 자체. Human이 dev 작업을 주면 명료화→합의→추적실행 단계를 자동 운영. [근거: Round 1]
- (R2) 자율성 = **모드 선택/전환**에 한정. 기존 Human 질문·승인 게이트(plan 승인, merge 승인) 보존 = HITL 유지. GJC 상호작용 패턴 그대로. [근거: Round 2, refined]
- (R3) 명료화 게이트 = **전용 단일 LLM 점수자 네이티브 구현**(GJC식), 기존 Room과 별개. [근거: Round 3]
- (R4) 범위 = **빅뱅** — 4개 컴포넌트로 mission_loop 오케스트레이션 전면 재배선. [근거: Round 4]

## Trigger Metadata
- Round 1~4 모두 mechanism A(해당 차원 명료도 상승 → 모호성 하강)로 단조 수렴. 모순/내부불일치/회피/범위확장 트리거 없음. Round 4(빅뱅)는 범위 결정으로 scope를 좁혔으나 신규 컴포넌트 추가 아님(트리거 D 아님).

## Lateral Review Panel
- Round 1 (initial→progress 전환): contrarian lens — "agent-lab은 본질적으로 HITL인데 GJC 자율성과의 경계?" → Round 2 질문으로 폴딩, (a)+HITL보존으로 해소.
- Round 4: architect/contrarian lens — "빅뱅 전면 재배선은 load-bearing mission_loop(격리 머지·Oracle 구동)라 고위험" → 타당성 영역으로 ralplan에 이관 권고.
- subagent 디스패치 결함으로 패널은 병렬 페르소나 대신 오케스트레이터가 직접 lens 적용(lateral_panel_failures: 1).

## Goal
agent-lab의 mission_loop 오케스트레이션을 deep-interview식 명료화 게이트(전용 LLM scorer) → ralplan식 합의(기존 Room 융합) → ultragoal식 목표추적 실행(기존 worktree 격리·Oracle 검증 유지)으로 전면 재배선하고, 오케스트레이터가 상황에 맞는 모드를 자율 선택하되 기존 Human 질문·승인 게이트는 그대로 보존한다.

## Constraints
- 자율성은 모드 선택/전환까지만. plan 승인·merge 승인 Human 게이트는 자동 통과 없이 보존.
- 명료화 점수자는 기존 Room과 별개의 전용 LLM scorer로 네이티브 구현.
- 기존 자산 유지(KEEP/FUSE): worktree 격리 실행·merge(`plan_execute_worktree.py`/`plan_execute_merge.py`/`auto_merge.py`), Oracle 검증·repair(`plan_execute_verify.py`, VERIFY/REPAIR), 멀티에이전트 Room(`room.py`, `consensus_policy.py`), divergence(`divergence.py`), plan.md 계약+Human 게이트(`plan_workflow.py`/`plan_pending.py`/`human_inbox.py`), 운영 견고성(`crash_recovery.py`/`run_control.py`/`cost_ledger.py`).
- GJC 런타임 의존 없이 agent-lab 네이티브 재구현.

## Non-Goals
- agent-lab의 worktree 격리·Oracle 검증·Room·divergence 역량 대체 (유지·융합 대상).
- Human 승인 게이트 제거 또는 자동 승인.
- GJC 바이너리/런타임에 대한 런타임 의존.

## Acceptance Criteria
- [ ] vague dev 작업 투입 시 mission 앞단에서 명료화 게이트(전용 scorer)가 자동 발동하고, 모호성이 임계 아래로 떨어지면 DISCUSS/합의로 전환한다.
- [ ] 오케스트레이터가 상황에 따라 명료화/합의/실행 모드를 자율 선택·전환한다.
- [ ] plan 승인·merge 승인 Human 게이트가 자동 통과 없이 유지된다(HITL).
- [ ] 기존 worktree 격리·Oracle 검증·crash_recovery 경로가 재배선 후에도 동작한다.
- [ ] goal 진행이 내구성 원장으로 추적된다.
- [ ] (세부 수용기준·합의 역할매핑·라우터 신호·원장 저장소는 ralplan 합의에서 구체화)

## Deferrals
- ralplan으로 이관(타당성/아키텍처): (1) 합의 역할매핑(Room agents→Planner/Architect/Critic), (2) goal 원장 저장소(run.json/mission_loop 재사용 vs 신규), (3) mode-router 결정 신호, (4) 빅뱅 vs 점진 타당성 압박 검증, (5) 세부 수용기준.
- Convergence Pacing: min-round floor/score-drop cap/dampening 없음 — bidirectional 점수화가 pacing 기제.
- 조기 종료(37%): 잔여 모호성은 명료도가 아니라 타당성 영역이라 ralplan이 해소.

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "이식"이 무엇을 지배하는가 불명 | 제품 오케스트레이션 vs 내부 스킬 vs 도그푸딩 규율 | 제품 오케스트레이션(mission/room) 자체 (R1) |
| 자율성이 Human 게이트를 약화하는가 | HITL 원칙과의 충돌 (contrarian) | 자율=모드만, 질문·승인 게이트 보존 (R2) |
| 명료화 점수를 누가 매기나 | Room 재사용 vs 신규 scorer vs 휴리스틱 | 전용 LLM scorer 네이티브 (R3) |
| 전면 교체인가 점진인가 | 빅뱅 리스크 (architect) | 빅뱅 전면 재배선 — 단, 타당성은 ralplan 검증 (R4) |

## Technical Context (brownfield)
- 대체 대상 백본: `mission_loop.py` FSM(MISSION_DEFINE/DISCUSS/PLAN_GATE/EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR/MISSION_DONE).
- 기존 모드 원시요소: `app/server/deps.py` TURN_PROFILES, `turn_modes.py` ModeContract, `divergence.py`.
- 유지 자산: 위 Constraints의 KEEP/FUSE 모듈 목록.
- 직전 작업으로 `plan_execute.py`/`mission_loop.py` God 모듈은 leaf 모듈(`plan_execute_{prompts,status,verify}`, `mission_{notepad,advance}`)로 분해 완료 — 재배선의 손댈 면적이 줄어든 상태.

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Orchestrator | core domain | current_mode, stage | routes Mission through stages; selects Mode |
| Mode | core domain | clarity/consensus/execution | selected by Orchestrator per situation |
| ClarityGate | core domain | scorer, threshold, ambiguity | precedes Consensus; uses dedicated LLM scorer |
| ConsensusEngine | core domain | room, roles | fuses Room; produces plan.md |
| ExecutionTracker | core domain | goal_ledger, worktree, oracle | retains isolation+verify; tracks goal |
| HumanGate | supporting | plan_approval, merge_approval | preserved between stages (HITL) |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 3 (Orchestrator, Mode, Pipeline) | 3 | - | - | N/A |
| 2 | 4 (+HumanGate) | 1 | 0 | 3 | 75% |
| 3 | 5 (+ClarityGate) | 1 | 0 | 4 | 80% |
| 4 | 6 (Pipeline→ConsensusEngine+ExecutionTracker) | 2 | 1 | 4 | 83% |

## Interview Transcript
<details>
<summary>Full Q&A (Round 0 + 4 rounds)</summary>

### Round 0 — 토폴로지
**Q:** 4개 최상위 컴포넌트(명료화/합의/실행/모드라우팅) 토폴로지 확인
**A:** add/remove/merge 필요 → "거의 대체하되 keep/fuse할 기존 구조 식별" → keep/fuse 표 제시 후 4개로 고정

### Round 1
**Q:** 이 체계가 agent-lab의 무엇을 지배하나?
**A:** (a) 제품 오케스트레이션 자체 — mission/room이 단계 자동 운영, 오케스트레이터가 모드 자율 선택
**Ambiguity:** 64% → (이전 라운드 대비 측정 시작)

### Round 2
**Q:** 자율성과 기존 Human 게이트의 경계?
**A:** (a)와 거의 같음 — GJC처럼 모드는 알아서 켜고 바꾸되 중간중간 질문·승인 받음 (HITL 보존)
**Ambiguity:** 56% → 47%

### Round 3
**Q:** 명료화 게이트는 누가/무엇이 점수를 매기나?
**A:** (b) 새 전용 단일 LLM 점수자 네이티브 구현 (Room과 별개)
**Ambiguity:** 47% → 43%

### Round 4
**Q:** 첫 증분 — 빅뱅 vs 점진 + 관찰가능 성공?
**A:** (c) 빅뱅 — 4개로 mission_loop 오케스트레이션 통째 재배선
**Ambiguity:** 43% → 37% (조기 종료 합의 → ralplan)
</details>
