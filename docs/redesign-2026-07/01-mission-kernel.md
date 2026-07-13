# Sector 1 — 제품 코어와 단일 Mission 생명주기

> **상태:** In progress / D0 — first-pass contract complete, cutover pending  
> **선행:** [README](./README.md) §전환 불변 조건  
> **후행:** [02 State](./02-state-events-durability.md), [04 Human UX](./04-human-experience-api-ui.md)

## 1. 목표

사용자의 주제부터 Oracle 검증 완료까지를 하나의 `Mission` aggregate로 표현한다. LLM은 후보 계획과 판단 근거를 생성하지만, 상태 전이·권한·재시도·완료 조건은 결정적 코드가 소유한다.

## 착수 상태

`src/agent_lab/mission/kernel.py`의 pure aggregate와 `repository.py`의 Journal 재생 경로를 추가했다. 계획 거절·재논의, merge commit 기록, Oracle pass, bounded repair, BLOCK 거부를 typed command/event로 검증한다. 기존 API writer는 아직 compatibility 단계이며 M6 전환 전까지 shadow 비교 대상으로 둔다.

## 2. 현재 평가

### 강점

- `plan.md`가 Human-readable contract로 존재한다.
- plan 승인, execute, merge, Oracle이 각각 명시적 gate를 가진다.
- `runtime/transitions.py`, `PolicyEngine`, import-cycle guard 등 통합 방향의 기반이 있다.
- 회귀 fixture와 worktree 테스트가 있어 strangler 전환이 가능하다.

### 핵심 결함

| 결함                | 현재 증거                                                     | 영향                                             |
| ------------------- | ------------------------------------------------------------- | ------------------------------------------------ |
| 이중 FSM            | `plan_workflow.phase`와 `mission_loop.phase`                  | 한 사용자 행위가 두 전이를 요구함                |
| 파생 상태 재저장    | `orchestration`, `work_phase`, drift reconcile                | 읽기 모델이 write authority처럼 행동함           |
| 도메인 간 직접 호출 | room/mission/plan이 runtime invoke seam으로 상호 호출         | 실패·재시도·트랜잭션 경계가 흐림                 |
| 기능별 루프 중첩    | goal loop, verified loop, mission loop, plan workflow         | “현재 어떤 루프가 주인인가”가 설정에 따라 달라짐 |
| 정책 분산           | objections, plan gate, merge gate, auto approve, trust budget | 같은 command 허용 여부를 여러 위치에서 판단      |

현재의 drift 자동 보정은 안전장치로 유용하지만 목표 구조는 아니다. 단일 사실을 여러 필드에 저장한 뒤 불일치를 고치는 대신, 한 상태와 이벤트에서 필요한 뷰를 계산해야 한다.

## 3. 설계 결정

### D1. Mission aggregate 하나를 write authority로 둔다

```text
Mission
  id, goal, workspace
  state
  plan_revision
  active_execution
  pending_decision
  policy_snapshot
  evidence_summary
  version
```

`plan.md`는 aggregate 자체가 아니라 버전이 있는 `PlanArtifact`다. Human 승인은 파일 경로가 아니라 `plan_revision + content_hash`에 결합한다.

### D2. 상태는 사용자 의미 기준으로 제한한다

제안 상태:

```text
DRAFTING
AWAITING_PLAN_DECISION
READY_TO_EXECUTE
EXECUTING
AWAITING_DIFF_DECISION
VERIFYING
REPAIRING
AWAITING_HUMAN
PAUSED
SUCCEEDED
FAILED
CANCELLED
```

Clarifier, peer review, consensus round, scribe는 최상위 mission state가 아니라 `DRAFTING` 안의 activity다. transport 연결 상태나 UI stepper 상태도 도메인 상태에 넣지 않는다.

### D3. Command와 policy를 분리한다

대표 command:

- `StartMission`
- `SubmitTopic`
- `ProposePlanRevision`
- `ApprovePlanRevision`
- `RejectPlanRevision`
- `StartExecution`
- `RecordExecutionResult`
- `ApproveDiff`
- `RejectDiff`
- `RecordOracleVerdict`
- `AnswerHumanRequest`
- `PauseMission`, `ResumeMission`, `CancelMission`

각 command는 expected version, actor, idempotency key를 가진다. `MissionPolicy`는 command 허용 여부와 필요한 Human gate를 한 번만 계산한다.

### D4. 조율 방식은 혼합형으로 고정한다

- Human: 목표·권한·고위험 결정의 최종 권한자
- Conductor: decomposition, routing, budget, stop condition
- Specialist agents: 독립 산출물 생성
- Scribe: plan artifact 합성
- Oracle: acceptance criteria 기반 판정

모든 agent의 민주적 합의는 기본값으로 사용하지 않는다. 다각도 판단 가치가 통신 비용보다 큰 plan review·high-risk gate에서만 quorum을 요구한다.

### D5. 기존 루프는 capability로 흡수한다

| 기존                    | 목표                                  |
| ----------------------- | ------------------------------------- |
| Plan workflow           | Mission의 drafting/approval use case  |
| Mission loop            | Mission command scheduler             |
| Verified loop           | Oracle policy preset                  |
| Goal loop               | Mission goal acceptance use case      |
| work_phase              | projection                            |
| orchestration reconcile | migration 기간 drift detector 후 제거 |

## 4. 목표 모듈 경계

```text
mission/
  aggregate.py       # 상태와 invariant
  commands.py        # 사용자/시스템 의도
  events.py          # 이미 일어난 사실
  policy.py          # command authorization/gates
  transitions.py     # pure transition functions
  artifacts.py       # PlanArtifact, EvidenceArtifact refs
application/
  mission_service.py # load -> decide -> append
  scheduler.py       # 다음 runnable activity 선택
  projections.py     # work/transcript/inbox read models
ports/
  agent.py
  executor.py
  oracle.py
  inbox.py
  mission_store.py
```

도메인은 FastAPI, filesystem, subprocess, provider SDK를 import하지 않는다.

## 5. 구현 계획

### M1. 현행 전이 인벤토리와 보존 계약

**산출물:** 모든 현행 phase·trigger·gate·side effect를 command/event에 매핑한 표.

**Acceptance criteria:**

- 모든 `plan_workflow`와 `mission_loop` phase가 `map / projection-only / retire` 중 하나로 분류된다.
- BLOCK, plan approval hash, worktree, merge, Oracle, repair cap 불변이 명시된다.
- 상태 전이와 외부 side effect가 분리되어 기록된다.

**검증:** 대표 regression session 5개가 매핑 표에서 끊김 없는 경로를 가진다.

### M2. Pure Mission aggregate

**산출물:** IO 없는 command decision과 event apply 함수.

**Acceptance criteria:**

- invalid transition은 typed domain error를 반환한다.
- 같은 event stream 재생은 같은 Mission을 만든다.
- BLOCK 상태에서 execute 계열 command가 항상 거부된다.
- plan hash가 바뀌면 기존 승인이 무효화된다.

**검증:** transition table test + property test + mutation test 후보를 적용한다.

### M3. Shadow translation

**산출물:** 기존 run mutation을 새 domain event로 번역하는 side-effect-free adapter.

**Acceptance criteria:**

- 기존 API 응답이나 파일을 바꾸지 않는다.
- 5개 fixture에서 새 projection이 기존 최종 상태와 일치한다.
- 불일치는 구조화된 drift report로 남고 자동 수정하지 않는다.

**검증:** `make test-fast`, fixture replay report.

### M4. Plan approval 세로 절편 전환

**산출물:** draft → plan revision → Human decision → ready-to-execute가 새 커널을 사용.

**Acceptance criteria:**

- 승인 command는 expected version과 content hash를 검증한다.
- 중복 승인 요청은 idempotent하다.
- 승인 후 계획 변경은 재승인을 요구한다.

**검증:** API integration + 실제 UI plan approve manual QA.

### M5. Execute/verify 세로 절편 전환

**산출물:** worktree execute부터 Oracle/repair까지 새 커널이 command authority가 됨.

**Acceptance criteria:**

- side effect 시작·성공·실패 이벤트가 구분된다.
- 프로세스 재시작 후 동일 idempotency key로 중복 merge되지 않는다.
- Oracle pass만 `SUCCEEDED`를 만든다.
- repair cap 소진은 명시적 Human decision 또는 terminal failure로 간다.

**검증:** temp git repo E2E, kill/restart fault injection, Oracle fail→repair path.

### M6. Legacy authority 제거

**산출물:** `plan_workflow.phase`, `mission_loop.phase` write path와 reconcile 제거.

**Acceptance criteria:**

- 새 Mission store 외 lifecycle writer가 없다.
- 기존 endpoint는 compatibility transport이거나 제거된다.
- dual-write 플래그와 drift auto-reconcile 코드가 삭제된다.

**검증:** import boundary test, dead-code scan, full CI, dogfood 10 missions.

## 6. 제거 후보

- 최상위 lifecycle authority로서의 `plan/workflow_state.py`
- 최상위 lifecycle authority로서의 `mission/loop.py`
- `runtime/orchestration_reconcile.py`
- lifecycle과 중복되는 `goal_loop.py`·`verified_loop.py` 상태
- UI 전용 `work_phase`의 저장 필드
- legacy classic planner→critic→scribe graph와 `/api/runs` 표면

삭제 시점은 대체 경로의 shadow parity와 dogfood 기준 충족 후다.

## 7. 리스크와 완화

| 리스크                                  | 완화                                                                |
| --------------------------------------- | ------------------------------------------------------------------- |
| 대규모 전환 중 gate 약화                | 기존 gate를 먼저 characterization test로 고정                       |
| dual-write가 영구화                     | M3 시작 시 종료 날짜·삭제 criteria를 함께 등록                      |
| 상태 수가 다시 증가                     | 새 최상위 state는 Human-visible wait/terminal 의미가 있을 때만 추가 |
| scheduler가 새 거대 오케스트레이터가 됨 | scheduler는 runnable activity 선택만, 정책과 IO는 port로 분리       |

## 8. 완료 정의

- 한 mission id에 lifecycle write authority가 하나다.
- 어떤 상태든 최근 event와 policy decision으로 설명할 수 있다.
- plan approve, execute, merge, verify가 중복 FSM 갱신 없이 진행된다.
- 사용자가 pause/resume 후 이전 단계를 반복하지 않는다.
- 기존 5모트가 domain invariant test로 고정된다.
