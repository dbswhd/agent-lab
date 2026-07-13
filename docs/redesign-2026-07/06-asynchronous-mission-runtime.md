# 심화 1 — 비동기 Mission Runtime

> **상태:** In progress / D0 — activity·lease·recovery policy first pass complete  
> **소유 범위:** 장기 실행 activity, 동시성, 대기, 취소, 재시작, backpressure  
> **선행:** [Mission Kernel](./01-mission-kernel.md), [State & Events](./02-state-events-durability.md)  
> **후행:** [Human UX](./04-human-experience-api-ui.md), [Messaging](./08-collaboration-messaging.md)

## 1. 결론

Agent Lab에서 “비동기”는 단순히 `async def`나 병렬 agent 호출을 의미하지 않는다. 사용자가 앱을 떠나거나 daemon이 재시작되고 provider 응답이 늦어져도 Mission이 **수락된 작업, 현재 실행, 보존된 결과, 필요한 Human 결정, 안전한 다음 행동**을 잃지 않는 제품 계약이다.

## 착수 상태

`activity.py`가 external wait·Human wait·bounded retry·timeout과 `SCHEDULED → CLAIMED → RUNNING` 전이를 pure transition으로 고정했고, `lease.py`가 cross-process claim/heartbeat/release/expiry recovery를 제공한다. `activity_queue.py`는 priority queue, idempotent enqueue, lease-aware claim/complete와 만료 복구를 연결한다. `recovery.py`는 side-effect 상태에 따라 ambiguous work를 무조건 재실행하지 않는다. `human_bridge.py`가 answered decision을 Activity/Mission resume으로 연결하며, `journal.py`/`repository.py`는 daemon 재시작 후 event replay를 보장한다. 아직 provider/execute/scheduler를 새 runtime으로 교체하지 않았으므로 AS4~AS7은 다음 wave다.

Room의 짧은 질의·응답은 동기 경험으로 유지한다. 다음 작업은 durable asynchronous activity로 전환한다.

- provider agent 실행
- worktree 준비와 execute
- merge checks와 Oracle verify
- repair loop
- scheduler/monitor/gateway delivery
- Human 응답을 기다리는 permission·clarification·approval

## 2. 현재 평가

### 이미 있는 기반

- `background_tasks.py`가 thread 기반 task와 취소 상태를 관리한다.
- `mission/scheduler.py`가 예약 실행과 daemon 수명을 다룬다.
- Room SSE가 agent progress를 streaming하고 reconnect registry가 있다.
- `run/control.py`, provider별 cancel, pause/resume, crash recovery가 존재한다.
- Human Inbox가 장시간 실행 중 질문을 외부화한다.

### 구조적 한계

| 현재 패턴                                                   | 문제                                                                      |
| ----------------------------------------------------------- | ------------------------------------------------------------------------- |
| thread, scheduler, Room turn, execute가 각각 자체 수명 관리 | 공통 activity 상태와 recovery 의미가 없음                                 |
| SSE 연결과 실제 작업 수명이 가까이 결합                     | client disconnect가 작업 상태 해석에 영향을 줄 수 있음                    |
| running/cancelled/failed 필드가 기능별로 다름               | UI와 운영 코드가 상태를 재해석함                                          |
| retry가 provider·execute·gateway 곳곳에 개별 구현           | 실패 영역에 맞는 공통 정책과 예산이 없음                                  |
| 전역 run lock 중심                                          | 서로 다른 Mission의 안전한 병렬성과 동일 Mission의 직렬화가 구분되지 않음 |
| Human wait와 system retry가 같은 “멈춤”처럼 보임            | 사용자가 개입해야 하는지 판단하기 어려움                                  |

## 3. 비동기 실행 모델

### 3.1 Mission과 Activity를 분리한다

`Mission`은 사용자 목표의 장기 생명주기다. `Activity`는 agent call, worktree create, verify 같은 하나의 실행 단위다.

```text
Mission 1
  Activity A: plan specialist call
  Activity B: critic call
  Activity C: scribe plan
  Wait: Human plan decision
  Activity D: worktree execute
  Wait: Human diff decision
  Activity E: Oracle verify
```

Mission은 Activity가 실패해도 사라지지 않는다. Activity terminal result가 Mission command의 입력이 된다.

### 3.2 Activity 상태 계약

```text
SCHEDULED
CLAIMED
RUNNING
WAITING_EXTERNAL
WAITING_HUMAN
CANCELLING
SUCCEEDED
FAILED_RETRYABLE
FAILED_TERMINAL
CANCELLED
TIMED_OUT
```

`WAITING_HUMAN`은 worker slot을 점유하지 않는다. `WAITING_EXTERNAL`은 provider stream 또는 외부 process를 추적하지만 재시작 시 reconnect/reconcile 정책이 있어야 한다.

### 3.3 Activity envelope

```text
ActivitySpec
  activity_id
  mission_id
  kind
  input_refs
  capability_requirements
  side_effect_class
  priority
  deadline
  timeout
  retry_policy
  idempotency_key
  expected_mission_version
  resource_budget
```

큰 prompt, diff, tool output은 inline payload가 아니라 artifact ref로 전달한다.

### 3.4 수락과 완료를 분리한다

Command API는 장기 작업을 즉시 끝내려 하지 않는다.

1. command 검증
2. event commit
3. activity enqueue
4. `202 Accepted` + command/activity id 반환
5. projection/SSE로 진행과 terminal result 전달

수락 응답 이후 journal에 기록되지 않은 작업은 존재해서는 안 된다.

## 4. 동시성과 scheduling

### 4.1 동시성 단위

| 범위                           | 정책                                          |
| ------------------------------ | --------------------------------------------- |
| 동일 Mission의 domain command  | sequence/version으로 직렬화                   |
| 동일 worktree의 write activity | 하나만 허용                                   |
| 서로 다른 Mission              | provider·CPU·workspace quota 안에서 병렬 가능 |
| read-only specialist calls     | task가 독립적이면 병렬 가능                   |
| Human decision                 | worker를 해제하고 durable wait                |

### 4.2 Queue 우선순위

초기 priority class:

1. `CONTROL`: cancel, pause, timeout, safety stop
2. `HUMAN_RESUME`: Human 응답 뒤 재개
3. `FOREGROUND`: 사용자가 현재 보고 있는 짧은 Room activity
4. `MISSION`: execute, verify, repair
5. `BACKGROUND`: index, monitor, scheduled maintenance

같은 class 안에서는 aging으로 starvation을 막는다.

### 4.3 Backpressure

- provider별 concurrency limit
- workspace별 write limit
- Mission별 outstanding activity limit
- 전체 token/cost budget
- queue age와 예상 wait를 read model에 노출

한도를 넘으면 무제한 thread를 만들지 않고 `SCHEDULED`로 유지한다. high-risk activity는 오래 기다렸다는 이유로 gate를 생략하지 않는다.

## 5. 취소·시간 제한·재시도

### 5.1 취소 계약

취소는 요청과 확인을 분리한다.

```text
CancelRequested -> CancellationForwarded -> ActivityCancelled
                                      \-> CancellationFailed
```

- soft cancel: provider/process에 중단 요청, partial artifact 보존
- hard terminate: grace period 후 child process 종료
- irreversible section: merge commit처럼 중단할 수 없는 구간은 완료 후 reconcile
- Mission cancel: 신규 activity 생성 금지, 실행 중 activity에 정책별 cancel 전파

### 5.2 Timeout 계약

queue wait, provider silence, total runtime, Human decision expiry를 서로 다른 timeout으로 둔다. timeout은 원인과 보존된 상태를 event로 남긴다.

### 5.3 Retry matrix

| 실패                      | 기본 행동                                      |
| ------------------------- | ---------------------------------------------- |
| network/rate limit        | bounded backoff + jitter                       |
| provider auth             | terminal + Human reconnect decision            |
| malformed provider stream | adapter failure, 동일 raw response 반복 금지   |
| model quality rejection   | context/critic/strategy를 바꾼 repair activity |
| stale version             | 최신 Mission reload 후 command 재결정          |
| permission/policy block   | 자동 retry 금지                                |
| ambiguous git merge       | git state reconcile 후 새 event                |

모든 retry는 `attempt`, `max_attempts`, 이전 failure ref, 변경된 전략을 기록한다.

## 6. 재시작과 복구

daemon 시작 시 Activity를 다음처럼 감사한다.

1. `CLAIMED/RUNNING/CANCELLING` activity 검색
2. provider session, process, git state와 대조
3. reconnect 가능하면 claim 복구
4. side effect가 이미 commit됐으면 result event 보강
5. 안전하게 반복 가능한 경우 새 attempt 생성
6. 판단 불가능하면 Human Decision Queue로 승격

복구가 event history를 조용히 수정해서는 안 된다. `ActivityRecoveryEvaluated`와 적용 결과를 추가한다.

## 7. 동기·비동기 UX 계약

| 상황           | 사용자에게 보여줄 것                              |
| -------------- | ------------------------------------------------- |
| 짧은 Room 응답 | streaming, 현재 speaker, cancel                   |
| queue 대기     | 대기 이유, priority, 마지막 갱신                  |
| 장기 실행      | milestone, 최근 activity, 비용/시간, pause/cancel |
| Human wait     | 질문 하나, 추천, 영향, 안전한 선택                |
| retry          | 실패 원인, 다음 시도에서 바뀐 점                  |
| 재시작 복구    | 보존된 것, 복구한 것, 확인이 필요한 것            |

부정확한 ETA 대신 milestone과 last activity time을 우선한다.

## 8. 구현 계획

### AS1. Activity catalog

**산출물:** 현행 background/Room/execute/verify/scheduler 작업의 activity 분류표.

**Acceptance criteria:**

- 모든 장기 작업에 owner, side-effect class, cancelability, timeout, retryability가 있다.
- Human wait와 external wait가 구분된다.
- 기존 전역 lock이 보호하는 invariant가 명시된다.

**검증:** 미분류 async entry point가 0인 정적 inventory 검사.

### AS2. Activity state와 journal projection

**산출물:** 공통 activity event와 read model.

**Acceptance criteria:**

- lifecycle transition table이 invalid transition을 거부한다.
- replay와 incremental projection이 동일하다.
- terminal state는 한 번만 결정된다.

**검증:** transition/property/replay tests.

### AS3. Durable local queue

**산출물:** claim lease, heartbeat, priority, concurrency limit를 가진 local worker queue.

**first-pass 결과:** `mission/activity_queue.py`가 priority·idempotent enqueue, lease-aware claim/heartbeat/complete, 만료 lease recovery를 제공한다. 실제 daemon/scheduler가 이 queue를 소비하는 wiring은 legacy parity 이후로 보류한다.

**Acceptance criteria:**

- daemon kill 후 lease가 복구된다.
- 같은 idempotency key의 side effect가 중복 실행되지 않는다.
- 서로 다른 Mission은 quota 안에서 병렬 실행된다.

**검증:** multiprocessing contention, kill/restart, queue aging test.

### AS4. Agent activity 세로 절편

**산출물:** provider call 하나를 enqueue→stream→result/cancel까지 새 runtime으로 실행.

**Acceptance criteria:**

- client disconnect가 activity를 취소하지 않는다.
- provider progress와 durable result가 같은 activity id로 연결된다.
- cancel acknowledgement가 UI에 반영된다.

**검증:** 실제 CLI happy path, silent timeout, cancel manual QA.

### AS5. Execute/verify 세로 절편

**산출물:** worktree execute와 Oracle을 durable activities로 전환.

**Acceptance criteria:**

- process crash 후 worktree와 execution state가 복구된다.
- merge irreversible section이 중복 commit되지 않는다.
- verify failure가 전략이 명시된 repair activity를 만든다.

**검증:** temp git repo fault injection E2E.

### AS6. Human durable wait

**산출물:** activity slot을 해제하는 Decision Queue wait/resume.

**Acceptance criteria:**

- 앱과 daemon 재시작 후 같은 decision을 재개한다.
- stale answer는 version conflict로 거부된다.
- expiry가 gate bypass로 이어지지 않는다.

**검증:** restart + answer, duplicate answer, expired decision tests.

### AS7. 기존 async 관리자 제거

**산출물:** 기능별 thread/status/retry 관리의 공통 runtime 수렴.

**Acceptance criteria:**

- background task, scheduler, Room, execute가 공통 activity vocabulary를 사용한다.
- 호환 API 외 별도 lifecycle truth가 없다.
- legacy thread registry와 중복 watchdog이 제거된다.

**검증:** dead-path scan, full CI, 10분 dogfood mission.

## 9. 외부 workflow engine 도입 gate

다음 증거가 없으면 Temporal/NATS/Ray를 도입하지 않는다.

- local durable queue가 만족하지 못한 구체적 SLO
- 복수 노드 또는 HA가 필요한 배포 시나리오
- 운영자가 감당 가능한 인프라 비용과 runbook
- 내부 Activity/Command/Event 계약을 그대로 유지하는 adapter 설계
- 장애·롤백 시험 결과

## 10. 완료 정의

- 수락된 장기 작업은 client와 daemon 수명에서 독립적이다.
- cancel, timeout, retry, Human wait가 서로 다른 명시적 상태다.
- 동일 Mission의 write는 직렬화되고 독립 Mission은 안전하게 병렬화된다.
- backpressure가 무제한 thread와 provider 과부하를 막는다.
- 재시작 후 중복 side effect 없이 자동 복구하거나 하나의 Human 결정으로 수렴한다.
