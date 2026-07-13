# 심화 3 — 협업·통신·메시징

> **상태:** In progress / D0 — local message contract first pass complete  
> **소유 범위:** agent·runtime·Human 사이의 메시지 의미, envelope, routing, delivery, replay  
> **선행:** [State & Events](./02-state-events-durability.md), [Async Runtime](./06-asynchronous-mission-runtime.md)  
> **관련:** [Multi-agent Coordination](./10-multi-agent-coordination.md)

## 1. 결론

Agent Lab의 우선 과제는 Kafka나 NATS 도입이 아니라 **통신 의미를 통일하는 것**이다. 현재 callback event, SSE, chat message, dispatch directive, MCP Inbox, gateway, run snapshot이 각자의 형식으로 협업 상태를 전달한다. 먼저 로컬 단일 프로세스에서도 동일하게 적용되는 message contract와 delivery semantics를 정의한다.

## 착수 상태

`messages.py`의 actor·authority·correlation·schema envelope와 `dispatcher.py`의 local command dedupe/event subscription을 추가했다. 외부 broker 없이도 at-least-once command와 best-effort progress 의미를 테스트하며, SSE/MCP gateway는 adapter 단계로 남긴다.

핵심 분리:

- 협업: 누가 어떤 책임으로 무엇을 요청·판정하는가
- 메시징: 그 의미를 어떤 envelope로 전달하는가
- transport: in-process, SSE, stdio MCP, CLI, HTTP, 향후 broker
- 저장: 어떤 사실을 journal에 남기고 재생하는가

transport가 바뀌어도 앞의 세 계약은 바뀌지 않아야 한다.

## 2. 현재 평가

### 강점

- Room은 lead, specialist, scribe, consensus, objection 개념이 있다.
- `room/dispatch.py`가 delegate와 parallel dispatch를 제공한다.
- callback event가 agent/activity progress를 UI로 전달한다.
- MCP-first Inbox가 Human 질문 채널과 source badge를 표준화하기 시작했다.
- gateway adapter가 Telegram/Slack/Discord/Webhook 전송을 분리한다.

### 결함

| 결함                                                                     | 영향                                                |
| ------------------------------------------------------------------------ | --------------------------------------------------- |
| event 이름과 payload가 여러 모듈에서 ad hoc 생성                         | schema evolution과 consumer 추적이 어려움           |
| agent output 텍스트 안의 directive가 routing protocol 역할               | 자연어와 제어 메시지가 혼합됨                       |
| callback, persisted chat, live log, SSE가 같은 사실을 다르게 표현        | reconnect·중복·순서 처리 복잡                       |
| delivery guarantee가 기능별로 암묵적                                     | retry 시 중복 agent call/decision/notification 위험 |
| broadcast/team 토론의 정보량이 커도 selective subscription이 약함        | token·latency·attention 낭비                        |
| Human·agent·system actor의 authority가 payload 타입보다 호출 위치에 의존 | 감사와 보안 정책 적용이 어려움                      |

## 3. 메시지 분류

### 3.1 Command

수신자에게 상태 변경을 요청한다. 단일 handler와 idempotency key를 가진다.

예: `ApprovePlan`, `StartActivity`, `CancelActivity`, `ResolveDecision`.

### 3.2 Domain Event

이미 일어난 사실이다. append-only이며 여러 projection/consumer가 읽을 수 있다.

예: `PlanApproved`, `ActivityFailed`, `OracleVerdictRecorded`.

### 3.3 Work Request / Result

Coordinator가 agent/tool/executor에게 유한 작업을 위임하고 결과를 받는다. domain command와 달리 외부 worker protocol이다.

### 3.4 Progress Signal

ephemeral하며 최신값 손실을 허용할 수 있다. durable result를 대체하지 않는다.

예: thinking, tool currently running, percentage when measurable, heartbeat.

### 3.5 Human Decision Request

질문, 선택지, 추천, 근거, consequence, expiry를 가진 durable request다. 일반 chat text와 구분한다.

### 3.6 Artifact Reference

plan, diff, report, tool output의 content-addressed reference다. 메시지 본문에 대형 데이터를 복제하지 않는다.

## 4. 공통 envelope

```text
MessageEnvelope
  message_id
  schema_name
  schema_version
  kind
  mission_id
  activity_id?
  sender: ActorRef
  recipient: RecipientRef
  occurred_at
  causation_id?
  correlation_id
  idempotency_key?
  sequence?
  deadline?
  priority
  content_type
  payload | artifact_refs
  trace_context
  security_labels
```

### ActorRef

```text
kind: human | conductor | agent | tool | system | extension
id
provider?
capabilities?
authority_scope
```

sender가 주장하는 authority를 그대로 신뢰하지 않는다. gateway/adapter가 인증된 principal과 연결한다.

## 5. Delivery semantics

### 5.1 기본 원칙

- command: at-least-once delivery + idempotent handler
- domain event append: 한 stream 안에서 monotonic sequence
- progress: best-effort, gap 허용
- Human decision: durable, exactly-once effect는 idempotent command로 구현
- notification: at-least-once 가능, dedupe key 필수

“exactly once delivery”를 transport가 제공한다고 가정하지 않는다. **effect once**를 idempotency와 state transition으로 달성한다.

### 5.2 Ordering

전역 순서를 만들지 않는다.

- Mission stream: total order
- Activity stream: Mission sequence 또는 activity-local sequence
- 서로 다른 Mission: 순서 없음
- progress와 terminal result: terminal이 authority, 늦은 progress는 폐기

### 5.3 Deduplication

consumer는 `message_id`와 business idempotency key를 구분한다. 같은 command가 새 message id로 재전달되어도 effect는 한 번이어야 한다.

### 5.4 Expiry

deadline이 지난 work request는 새로 시작하지 않는다. Human decision expiry는 policy에 따라 재질문·pause·cancel로 전환하며 자동 승인하지 않는다.

## 6. Routing과 collaboration channels

### 6.1 Logical channels

```text
mission.control
mission.activity
mission.artifact
mission.decision
mission.evidence
agent.<capability>
provider.<id>.health
gateway.notification
```

이는 broker topic을 즉시 만들자는 뜻이 아니라 routing vocabulary다.

### 6.2 Point-to-point

한 owner가 있는 command/work request에 사용한다. execute, scribe, Human decision resolution은 point-to-point다.

### 6.3 Publish/subscribe

domain event를 projection, telemetry, notification이 독립 소비할 때 사용한다. consumer failure가 producer transaction을 되돌리지 않는다.

### 6.4 Broadcast 제한

모든 transcript를 모든 agent에게 보내지 않는다. specialist는 task scope, relevant artifact, dependency result만 받는다. 팀 전체 broadcast는 policy/gate/goal 변경처럼 전역 정렬이 필요한 사실에 한정한다.

## 7. Request/reply와 장기 작업

동기 RPC처럼 agent가 끝날 때까지 caller stack을 유지하지 않는다.

```text
WorkRequested
  -> WorkAccepted
  -> ProgressSignal*
  -> WorkCompleted | WorkFailed | WorkCancelled
```

requester는 correlation id로 result를 projection한다. timeout은 reply가 없다는 transport 사실과 작업이 실패했다는 domain 사실을 구분한다.

## 8. Backpressure·재시도·Dead Letter

### Backpressure

- recipient capability/provider별 queue
- concurrency credit
- max in-flight bytes/artifacts
- priority와 aging
- producer에게 `accepted / delayed / rejected` 결과 반환

### Retry

- 동일 payload 재전송인지 새 전략의 새 work request인지 구분
- transport retry는 같은 idempotency key
- model repair는 새 activity id와 이전 failure causation ref

### Dead Letter

다음 메시지는 dead-letter projection으로 보낸다.

- unknown schema/version
- 반복 consumer failure
- recipient 없음
- integrity/hash 실패
- expired non-recoverable request

dead letter는 자동 폐기하지 않고 diagnostic 또는 Human decision으로 연결한다.

## 9. 보안·프라이버시

- envelope security label: public/project/secret/credential/PII
- recipient capability와 session grant로 전달 가능 여부 판단
- raw credential은 message payload 금지, credential ref만 허용
- subprocess/provider 경계에서 env allowlist 유지
- 외부 gateway로 보낼 수 있는 projection을 별도 정의
- prompt injection이 control directive를 위조하지 못하도록 자연어와 control schema 분리
- audit에는 actor, authority, policy decision을 기록

## 10. Local bus와 외부 broker의 경계

### 1단계: in-process typed dispatcher

schema registry, handler ownership, idempotency, local queue를 검증한다.

### 2단계: durable local journal/queue

재시작, replay, lease, Human wait를 해결한다.

### 3단계: adapter 가능한 transport port

```text
publish(envelope)
subscribe(filter, cursor)
ack(delivery)
reject(delivery, reason)
```

### 4단계: 필요 시 broker ADR

복수 노드, 독립 배포 consumer, 처리량, HA가 실제 요구될 때 NATS/Redis Streams/RabbitMQ/Kafka를 비교한다.

## 11. 구현 계획

### CM1. 메시지 inventory

**산출물:** callback/SSE/chat/dispatch/MCP/gateway 메시지의 producer-consumer 표.

**Acceptance criteria:**

- 각 메시지가 command/event/work/progress/decision/artifact 중 하나로 분류된다.
- owner와 durability 요구가 명시된다.
- 자연어 제어 directive가 별도 목록으로 드러난다.

**검증:** 미분류 `on_event` type과 routing directive가 0인 inventory check.

### CM2. Schema registry와 envelope

**산출물:** versioned schema, actor, correlation, security label.

**Acceptance criteria:**

- unknown version은 조용히 처리되지 않는다.
- 모든 durable message에 mission/correlation id가 있다.
- payload size와 artifact ref 규칙이 적용된다.

**검증:** serialization/upcast/unknown-schema/redaction tests.

### CM3. Typed local dispatcher

**산출물:** handler registry, point-to-point, pub/sub, consumer isolation.

**Acceptance criteria:**

- command owner는 하나다.
- event consumer 하나의 실패가 다른 consumer를 막지 않는다.
- duplicate command effect가 한 번만 적용된다.

**검증:** handler ownership, fan-out isolation, dedupe tests.

### CM4. Agent work protocol

**산출물:** WorkRequested/Accepted/Progress/Result 계약.

**Acceptance criteria:**

- provider raw event가 공통 message로 변환된다.
- late progress가 terminal result를 덮어쓰지 않는다.
- cancel과 timeout의 causation chain이 유지된다.

**검증:** provider replay, timeout, cancel, malformed stream tests.

### CM5. Human decision protocol

**산출물:** plan/diff/clarifier/permission/objection의 공통 decision schema.

**Acceptance criteria:**

- 질문·선택지·근거·영향·expiry가 구조화된다.
- 답변 effect는 idempotent하다.
- stale/unauthorized answer가 거부된다.

**검증:** Decision Queue API/E2E와 MCP compatibility.

### CM6. Durable delivery와 replay

**산출물:** cursor, ack/lease, dead-letter projection.

**Acceptance criteria:**

- daemon restart 후 unacked work가 안전하게 복구된다.
- projection consumer가 offset부터 재생한다.
- 반복 실패 메시지가 Mission을 무한 루프시키지 않는다.

**검증:** kill/restart, corrupted payload, poison-message tests.

### CM7. SSE/gateway adapters

**산출물:** 동일 message/projection을 SSE와 외부 notification으로 변환.

**Acceptance criteria:**

- client reconnect가 durable message를 중복 표시하지 않는다.
- progress drop이 최종 결과를 손상시키지 않는다.
- 외부 gateway는 허용된 필드만 수신한다.

**검증:** network drop browser E2E와 outbound redaction tests.

### CM8. Legacy protocol 제거

**산출물:** ad hoc event payload와 자연어 control directive 축소.

**Acceptance criteria:**

- core routing은 typed message만 사용한다.
- compatibility parser는 edge에만 있고 폐기 날짜가 있다.
- producer-consumer graph가 문서와 일치한다.

**검증:** static event-name scan, compatibility fixture, full CI.

## 12. 완료 정의

- 메시지 의미와 transport가 분리된다.
- command, event, work, progress, Human decision이 혼용되지 않는다.
- retry와 reconnect가 duplicate effect를 만들지 않는다.
- 모든 durable 협업 메시지는 actor·correlation·authority·schema version을 가진다.
- 외부 broker 없이도 같은 계약이 로컬 runtime에서 검증된다.
