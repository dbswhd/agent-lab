# Sector 5 — 신뢰성·평가·운영·확장

> **상태:** In progress / D0 — first-pass evidence complete, ops cutover pending  
> **선행:** 모든 섹터의 command/event/adapter 계약  
> **목표:** green CI가 아니라 실환경에서 설명·복구·개선 가능한 시스템

## 1. 목표

결정론적 소프트웨어 품질, 비결정적 agent 품질, 운영 신뢰성, 사용자 가치를 분리해 측정한다. 기능은 코드 존재가 아니라 dogfood에서 효용과 복구 가능성이 확인될 때 승격한다.

## 착수 상태

Mission journal tail recovery, stale writer conflict, Oracle fail→repair→merge→pass, Human decision restart를 자동 검증하는 테스트를 추가했다. 기존 대형 mission 모듈의 broad/silent exception과 중복 writer는 발견된 레거시 리스크로 기록하고 이번 slice에서는 수정하지 않는다.

**2026-07-16 update — R1 완료, R2 first slice 완료.** [journey reliability matrix](./evidence/r1-journey-reliability-matrix-2026-07-16.md)가 `sessions/_regression/`의 기존 39개 golden fixture를 8개 journey(start/plan/execute/diff/verify/repair/resume/cancel)로 재정리했다. deterministic/mock/live 3계층은 이미 존재했고(README, `make dogfood-suite-mock`, NOW.md 라이브 트랙) 새로 만들 게 없었다 — journey→fixture 매핑 문서화가 R1의 실질 작업이었다. 발견한 유일한 gap이었던 cancel(`plan/execute_resolve.py::cancel_open_execution` — 테스트가 전무했음, `test_run_control.py`는 다른 개념인 turn-level cancel을 다룸)은 `tests/test_execute_cancel.py`로 즉시 닫았다 — 8/8 journey 커버. A1(provider capability inventory)의 "provider-level invoke cancel을 못 찾음"은 다른 계층이라 아직 미해결로 남아 있다. R2의 나머지 범위(agent timeout, process kill, partial journal, git merge ambiguity, SSE disconnect, stale Human command)는 미착수.

## 2. 현재 평가

### 강점

- `make test-fast`, integration/bridge/smoke/score, regression sessions가 풍부하다.
- evidence ledger, cost ledger, feedback report, turn metrics, emergence bench가 있다.
- run profile과 flag registry, D0~D4 언어가 운영 승격에 유용하다.
- worktree, subprocess env, merge checks, crash recovery 등 안전 경계가 강하다.

### 결함

| 결함                                                                           | 영향                                                 |
| ------------------------------------------------------------------------------ | ---------------------------------------------------- |
| 테스트 수와 shipped matrix가 크지만 제품 journey별 신뢰도가 한눈에 보이지 않음 | 많은 green check가 실제 dogfood 성공을 보장하지 않음 |
| mock가 기본이고 live/dogfood evidence가 별도                                   | 모델·provider·실환경 변동성 회귀를 늦게 발견         |
| flag와 Make target가 많음                                                      | 운영 조합 폭발과 dead feature 누적                   |
| quality/cost/latency/Human effort 지표가 여러 ledger에 분산                    | 최적화 목표가 충돌해도 통합 판단 어려움              |
| default-off/zero-call-site 실험의 종료 규칙이 약함                             | 코어 복잡도는 증가하고 사용자 가치는 불명            |

## 3. 신뢰성 모델

### D1. 실패 영역을 분리한다

| 영역           | 예                                 | 책임                   |
| -------------- | ---------------------------------- | ---------------------- |
| Domain         | invalid transition, stale approval | Mission kernel         |
| Infrastructure | filesystem, git, process, network  | adapter + retry policy |
| Provider       | auth, rate limit, malformed stream | AgentRuntime adapter   |
| Model          | wrong plan, unsupported claim      | evaluation/Oracle      |
| Human wait     | answer/approval pending            | Decision Queue         |
| Policy         | permission, risk, budget blocked   | MissionPolicy          |

모든 실패는 영역, retryability, preserved state, next action을 구조화해 남긴다.

### D2. 재시도는 중앙 기본값이 아니라 activity policy다

- deterministic validation failure: 재시도하지 않음
- transient provider/network: bounded exponential backoff + jitter
- model quality failure: 동일 prompt 반복 대신 critic/repair/context change
- permission/Human wait: 자동 재시도하지 않음
- merge ambiguity: 실제 git state 확인 후 reconcile

### D3. 평가 피라미드를 둔다

```text
Pure transition/property tests
Adapter contract tests
Projection/replay tests
Temp-repo integration tests
Mock mission journeys
Live provider canary
Dogfood cohort + Human review
```

상위 단계가 하위 단계를 대체하지 않는다. 모델 품질을 unit test로 주장하지 않고, 상태 안전성을 live 평가에 맡기지도 않는다.

### D4. 성공을 다목적으로 측정한다

대표 mission scorecard:

- task outcome: acceptance criteria/Oracle/evidence
- safety: gate bypass, unsafe tool, secret leak
- reliability: crash recovery, duplicate side effect, manual rescue
- quality: plan defects, repair count, correction recurrence
- efficiency: latency, tokens, cost, duplicate agent work
- Human effort: decisions, wait time, override rate
- experience: abandoned mission, return-to-context success

단일 합성 점수는 보조 지표로만 사용하고 원 지표를 숨기지 않는다.

### D5. 확장은 실제 병목 뒤에 한다

현재 목표는 single-node durable runtime이다. 다음 단계의 선택 기준:

| 신호                               | 후보                            |
| ---------------------------------- | ------------------------------- |
| 독립 mission 병렬 처리량 부족      | local worker pool/process pool  |
| 여러 노드 간 task delivery 필요    | NATS/Redis Streams/RabbitMQ ADR |
| 장기 timer·재시작·보상 흐름이 핵심 | Temporal ADR                    |
| 수십 개 stateful agent의 동적 배치 | Ray/actor ADR                   |
| 원격 이기종 agent 상호운용 요구    | A2A adapter                     |

기술 유행이나 노트의 예시만으로 인프라를 도입하지 않는다.

## 4. 구현 계획

### R1. Journey reliability matrix

**산출물:** 핵심 journey × failure mode × test/evidence 소스 표.

**Acceptance criteria:**

- start/plan/execute/diff/verify/repair/resume/cancel 경로가 모두 포함된다.
- 각 journey에 deterministic, mock, live/dogfood evidence가 구분된다.
- 미검증 경로가 명시적으로 드러난다.

**검증:** CI가 matrix의 fixture/test link 존재를 검사한다.

### R2. Fault injection suite

**산출물:** agent timeout, process kill, partial journal, git merge ambiguity, SSE disconnect, stale Human command 시나리오.

**Acceptance criteria:**

- 각 failure가 명시적 terminal/wait/retry 상태로 수렴한다.
- 중복 merge와 중복 external side effect가 없다.
- recovery 후 evidence와 transcript가 원인을 설명한다.

**검증:** temp repo integration + daemon restart tests.

### R3. Unified telemetry schema

**산출물:** mission/activity/agent/tool/decision/side-effect spans와 metrics.

**Acceptance criteria:**

- correlation id로 Human command부터 Oracle까지 추적한다.
- latency/cost/token/retry/escalation이 activity와 연결된다.
- prompt 원문과 secret은 기본 telemetry에 없다.
- local JSON export와 향후 OpenTelemetry adapter를 분리한다.

**검증:** trace completeness test, redaction test, sample dashboard.

### R4. Eval corpus와 rubric versioning

**산출물:** 대표 repo/task corpus, rubric, oracle version, baseline result.

**Acceptance criteria:**

- correctness, safety, efficiency, Human effort가 별도 rubric이다.
- model/provider/prompt/context recipe 버전이 결과에 기록된다.
- benchmark overfit를 막기 위해 holdout과 dogfood incident replay가 있다.

**검증:** 동일 seed/mock reproducibility, live result confidence interval.

### R5. Profile·flag·experiment governance

**산출물:** 모든 flag를 `operational / rollout / experiment / migration`으로 분류.

**Acceptance criteria:**

- experiment는 owner, hypothesis, metric, expiry, removal condition을 가진다.
- migration flag는 dual path 종료 날짜가 있다.
- profile은 사용자 의도와 SLO만 표현하고 내부 구현 조합을 숨긴다.
- zero-call-site 기능은 extension 이동 또는 제거된다.

**검증:** registry linter, expired flag CI failure, profile pairwise tests.

### R6. Dogfood rollout

**산출물:** shadow → opt-in → supervisor cohort → default 전환 runbook.

**Acceptance criteria:**

- 단계별 rollback command와 data compatibility가 검증된다.
- 최소 표본과 promotion/rollback threshold가 사전에 정해진다.
- Human override와 incident note가 episode로 수집된다.

**검증:** 실제 dogfood missions, weekly scorecard, rollback drill.

### R7. Extension boundary

**산출물:** extension manifest와 dependency rule.

**Acceptance criteria:**

- `trading_mission/`, quant, gateway 같은 선택 기능이 Mission ports만 사용한다.
- extension이 core state field나 root flag를 임의 추가하지 않는다.
- 제거한 extension이 core CI와 기본 UI를 깨지 않는다.

**검증:** extension-disabled full CI, import boundary test, package smoke.

### R8. Legacy retirement

**산출물:** delete list, data migration, documentation supersede map.

**Acceptance criteria:**

- classic graph, duplicate FSM, orphan endpoint, expired flags가 제거된다.
- TRACEABILITY는 “코드 존재”가 아니라 새 journey evidence를 가리킨다.
- README/ARCHITECTURE/NORTH-STAR가 새 vocabulary로 갱신된다.

**검증:** dead import/route scan, docs link check, clean clone quickstart.

## 5. 초기 SLO 제안

수치는 Wave 0 기준선 이후 확정한다. 아래는 측정 항목의 제안이다.

| SLO                                   | 초안                             |
| ------------------------------------- | -------------------------------- |
| accepted command durability           | acknowledgement 후 event 유실 0  |
| duplicate irreversible side effect    | 0                                |
| reconnect transcript convergence      | 30초 내 또는 즉시 snapshot 복구  |
| cancel acknowledgement                | provider별 p95 측정 후 상한 설정 |
| mission recovery after daemon restart | 자동 또는 단일 Human action      |
| unsafe gate bypass                    | 0                                |
| explainable terminal failure          | 100% next action 포함            |

## 6. 운영 리뷰 주기

- 매 mission: outcome, cost, Human decision, repair, failure domain 기록
- 매주: regression drift, recurring correction, provider health, expired experiments
- 매월: architecture debt, flag count, endpoint count, extension dependencies
- 분기: autonomy level, budget, live quality, framework/broker 도입 조건 재평가

## 7. 완료 정의

- 핵심 journey마다 failure injection과 recovery evidence가 있다.
- mock, live canary, dogfood 가치가 구분되어 보고된다.
- feature flag와 실험이 만료·승격·삭제되는 생명주기를 가진다.
- 비용·지연·Human effort가 품질과 함께 의사결정에 사용된다.
- 분산 인프라는 측정된 요구에 의해 선택되며 코어 domain은 독립적이다.
