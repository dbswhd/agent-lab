# Wave 0 — Mission 생명주기 기준선 인벤토리

> **상태:** In progress / M1 complete — Human review pending  
> **목적:** 새 Mission Kernel을 구현하기 전에 현재 동작·writer·gate·side effect를 고정한다.  
> **machine-readable source:** `tests/fixtures/mission-baseline.json`

## 1. 범위와 판정 규칙

이번 기준선은 제품의 핵심 모트와 직접 연결된 다섯 경로만 다룬다.

| 분류              | 의미                                                       |
| ----------------- | ---------------------------------------------------------- |
| `map`             | 현재 동작을 새 Mission command/event로 옮길 대상           |
| `projection-only` | 상태 authority가 아니며 새 event에서 계산할 대상           |
| `retire`          | 새 커널 전환 후 제거할 중복 writer·상태·compatibility 경로 |

이 문서는 현재 구조를 정당화하는 문서가 아니다. 현재 writer를 발견하고, 새 구조 전환 후 삭제할 근거를 만든다.

## 2. 대표 시나리오 목록

| ID                                  | 현재 fixture                 | 현재 최종 상태                    | 새 커널 핵심 결과                                           |
| ----------------------------------- | ---------------------------- | --------------------------------- | ----------------------------------------------------------- |
| `plan_reject_revisit`               | `mission_loop_plan_reject`   | `mission_loop.phase=PLAN_REJECT`  | `PlanRejected` → Human/Room 재논의 activity                 |
| `execute_success_merge_oracle_pass` | `worktree_merge_ok`          | merged + Oracle pass              | `MergeCommitted` + `OraclePassed` → verified completion     |
| `oracle_fail_repair`                | `mission_loop_verify_repair` | repair 1회 후 `MISSION_DONE`      | `OracleFailed` → bounded `RepairRequested` → `OraclePassed` |
| `human_inbox_pause_resume`          | `mission_loop_paused`        | `MISSION_PAUSED` + `pause_reason` | `HumanDecisionRequested` → `DecisionResolved` → resume      |
| `daemon_crash_recovery`             | `durable_completed_steps`    | partial + `completed_steps[]`     | persisted step event replay 후 미완료 activity 재개         |

기계 검증은 `tests/test_mission_baseline_inventory.py`가 수행한다. fixture의 이름과 경로가 변경되면 이 manifest와 근거 문서를 함께 갱신한다.

## 3. 공통 현재 상태 모델

현재 생명주기는 한 필드가 소유하지 않는다.

```text
plan_workflow.phase
mission_loop.phase
run.executions[].status
run.human_inbox[]
run.completed_steps[]
orchestration / work_phase 파생값
```

따라서 기준선에서는 “현재 phase 하나”가 아니라 다음을 함께 기록해야 한다.

- 사용자 의도와 현재 goal
- plan revision/hash와 approval
- mission phase와 pending action
- execution/worktree/merge 상태
- Oracle verdict와 repair count
- Human decision/inbox 상태
- crash/restart 시 마지막 durable step
- UI/SSE에 전달되는 durable 및 ephemeral event

## 4. 시나리오별 전이 인벤토리

### 4.1 `plan_reject_revisit`

**현재 근거:** `sessions/_regression/mission_loop_plan_reject/run.json`

| 구분        | 현재 관찰                                          | 새 command/event 매핑                                | 분류            |
| ----------- | -------------------------------------------------- | ---------------------------------------------------- | --------------- |
| 시작        | 승인 전 plan gate 평가                             | `EvaluatePlan`                                       | map             |
| 판정        | verify 필드가 모호해 reject                        | `PlanRejected`                                       | map             |
| 상태 writer | `mission/loop.py`, `runtime/transitions.py`        | Mission aggregate transition                         | map             |
| Human/Room  | 재논의가 필요하지만 현재 fixture는 pending 아님    | `StartDiscussActivity` 또는 `HumanDecisionRequested` | map             |
| side effect | execute 없음                                       | 없음                                                 | projection-only |
| 파생값      | `orchestration`, `work_phase`가 fixture에서는 null | event 기반 read model                                | projection-only |
| 제거 대상   | phase를 직접 쓰는 중복 경로                        | 새 command handler 외 writer                         | retire          |

**보존 불변:** reject 상태에서 execute가 시작되지 않는다. reject reason과 실패 목록은 다음 plan revision의 근거로 남는다.

### 4.2 `execute_success_merge_oracle_pass`

**현재 근거:** `sessions/_regression/worktree_merge_ok/run.json`

| 구분       | 현재 관찰                                       | 새 command/event 매핑                        | 분류   |
| ---------- | ----------------------------------------------- | -------------------------------------------- | ------ |
| 시작       | `plan_workflow.phase=APPROVED`                  | `ApprovePlanRevision`                        | map    |
| 격리       | worktree path/branch/base SHA 기록              | `WorktreeProvisioned`                        | map    |
| 실행       | execution row가 merged                          | `ExecutionStarted`, `ExecutionSucceeded`     | map    |
| Human gate | merge approval이 필요                           | `ApproveDiff`                                | map    |
| merge      | commit SHA와 merge status 기록                  | `MergeCommitted`                             | map    |
| 검증       | `oracle.verdict=pass`, verify-after-merge pass  | `OraclePassed`                               | map    |
| 완료       | verified completion                             | `MissionSucceeded` projection/terminal event | map    |
| 제거 대상  | execution row가 lifecycle authority가 되는 경로 | Mission event authority 외 writer            | retire |

**보존 불변:** worktree 격리, Human merge gate, Oracle pass 없이는 성공 처리하지 않는다.

### 4.3 `oracle_fail_repair`

**현재 근거:** `sessions/_regression/mission_loop_verify_repair/run.json`

| 구분          | 현재 관찰                                     | 새 command/event 매핑                   | 분류   |
| ------------- | --------------------------------------------- | --------------------------------------- | ------ |
| 1차 실행      | `exec-repair-1` merged                        | `MergeCommitted`                        | map    |
| 검증 실패     | missing `pdfPageCount`                        | `OracleFailed` + evidence refs          | map    |
| repair budget | action repair count 1/2                       | `RepairRequested(attempt=1)`            | map    |
| 재실행        | `exec-repair-2` merged                        | `RepairCompleted`                       | map    |
| 재검증        | Oracle pass                                   | `OraclePassed`                          | map    |
| 완료          | `MISSION_DONE`                                | `MissionSucceeded`                      | map    |
| 제거 대상     | repair count와 phase를 여러 모듈이 직접 patch | Mission policy/aggregate writer 외 경로 | retire |

**보존 불변:** 같은 실패를 무한히 재시도하지 않는다. repair는 전략·attempt·failure evidence를 연결해야 한다.

### 4.4 `human_inbox_pause_resume`

**현재 근거:** `sessions/_regression/mission_loop_paused/run.json`, `tests/test_human_inbox.py`, `tests/test_room_disconnect_inbox_guard.py`

| 구분             | 현재 관찰                                      | 새 command/event 매핑                        | 분류            |
| ---------------- | ---------------------------------------------- | -------------------------------------------- | --------------- |
| pause            | `MISSION_PAUSED`, `pause_reason=global_cancel` | `PauseMission` / `MissionPaused`             | map             |
| partial state    | resume phase/action index 기록                 | `ActivityCheckpointed`                       | map             |
| Human decision   | Inbox item pending/resolved                    | `HumanDecisionRequested`, `DecisionResolved` | map             |
| resume           | 승인/응답 뒤 실행 재개                         | `ResumeMission` / `ActivityResumed`          | map             |
| disconnect guard | pending inbox이면 worker kill 방지             | `HumanWaitProtected` policy decision         | map             |
| 파생값           | Work/Inbox summary                             | projection                                   | projection-only |
| 제거 대상        | inbox pending과 pause phase의 중복 boolean     | Decision Queue authority 외 writer           | retire          |

**보존 불변:** Human wait는 자동 retry나 gate bypass가 아니다. 앱/SSE 연결이 끊겨도 pending decision과 partial checkpoint는 보존된다.

### 4.5 `daemon_crash_recovery`

**현재 근거:** `sessions/_regression/durable_completed_steps/run.json`, `tests/test_durable_completed_steps.py`, `tests/test_crash_recovery.py`

| 구분         | 현재 관찰                                              | 새 command/event 매핑                            | 분류            |
| ------------ | ------------------------------------------------------ | ------------------------------------------------ | --------------- |
| durable step | `completed_steps[]`에 agent turn 저장                  | `StepCompleted`                                  | map             |
| partial turn | status partial, failed agent 기록                      | `ActivityPartial` / `ActivityFailed`             | map             |
| restart      | persisted state를 읽고 완료 step skip                  | `MissionRehydrated`, `ActivityResumeEvaluated`   | map             |
| merge crash  | orphan/ambiguous merge를 startup reconcile             | `SideEffectRecoveryEvaluated`                    | map             |
| 저장         | `run/meta.py`, `checkpoint_store.py`                   | event journal + snapshot                         | map             |
| 파생값       | session/status summaries                               | projection                                       | projection-only |
| 제거 대상    | lifecycle truth로서 mutable `completed_steps`/run dict | journal authority 전환 후 compatibility snapshot | retire          |

**보존 불변:** 이미 완료된 step은 재실행하지 않는다. merge 상태가 불명확하면 안전한 reconcile 또는 Human decision으로 수렴한다.

## 5. Cross-cutting writer inventory

| 현재 경로                                          | 책임                                       | 새 분류                            |
| -------------------------------------------------- | ------------------------------------------ | ---------------------------------- |
| `src/agent_lab/mission/loop.py`                    | mission phase와 gate/repair state          | map → 이후 retire as writer        |
| `src/agent_lab/mission/advance.py`                 | merge/verify/repair side effect transition | map → application handler          |
| `src/agent_lab/plan/workflow_state.py`             | plan substate                              | map → plan artifact projection     |
| `src/agent_lab/runtime/transitions.py`             | transition table와 guard                   | map → pure Mission transition      |
| `src/agent_lab/runtime/orchestration.py`           | plan/mission drift read model              | projection-only → retire reconcile |
| `src/agent_lab/runtime/orchestration_reconcile.py` | drift auto-correction                      | retire after shadow parity         |
| `src/agent_lab/run/meta.py`                        | run snapshot patch/read                    | map → compatibility projection     |
| `src/agent_lab/checkpoint_store.py`                | checkpoint persistence                     | map → journal snapshot             |
| `src/agent_lab/crash_recovery.py`                  | startup side-effect reconcile              | map → recovery policy              |
| `src/agent_lab/human_inbox.py`                     | Human request lifecycle                    | map → Decision Queue               |
| `src/agent_lab/run/control.py`                     | cancel/pause/child process control         | map → activity control command     |
| `src/agent_lab/room/session_persist.py`            | chat/turn/completed step persistence       | map → projection + activity events |

## 6. Wave 0 검증 명령

```bash
.venv/bin/pytest -q tests/test_mission_baseline_inventory.py
.venv/bin/pytest -q tests/test_durable_completed_steps.py tests/test_crash_recovery.py
.venv/bin/pytest -q tests/test_plan_workflow.py tests/test_mission_loop.py
python scripts/smoke_room.py
```

Wave 0의 완료는 새 runtime이 동작한다는 뜻이 아니다. 현재 기준선이 재현되고, 새 구현이 비교할 state/event/gate/side-effect 계약이 생겼다는 뜻이다.

## 7. M1 완료 기준

- [x] 다섯 대표 시나리오가 machine-readable manifest에 등록됨
- [x] 각 fixture 경로가 실제 저장소에 존재함
- [x] 각 시나리오의 현재 writer와 새 command/event 매핑이 기록됨
- [x] `map / projection-only / retire` 분류가 있음
- [x] 다섯 시나리오의 full regression 명령이 모두 실행·통과함
- [ ] Human review로 불변 조건과 fixture 선택이 승인됨

M1 inventory와 M2~M5 first-pass contract 검증이 완료됐다. 다음 단계는 기존 lifecycle writer를 바로 제거하는 것이 아니라, session-facing application adapter와 shadow parity를 먼저 추가하는 것이다. 기존 writer는 cutover 전까지 유지한다.
