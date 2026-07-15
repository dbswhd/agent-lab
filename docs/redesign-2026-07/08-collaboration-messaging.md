# 심화 3 — 협업·통신·메시징

> **상태:** In progress / D0 — local message contract first pass complete  
> **소유 범위:** agent·runtime·Human 사이의 메시지 의미, envelope, routing, delivery, replay  
> **선행:** [State & Events](./02-state-events-durability.md), [Async Runtime](./06-asynchronous-mission-runtime.md)  
> **관련:** [Multi-agent Coordination](./10-multi-agent-coordination.md)

## 1. 결론

Agent Lab의 우선 과제는 Kafka나 NATS 도입이 아니라 **통신 의미를 통일하는 것**이다. 현재 callback event, SSE, chat message, dispatch directive, MCP Inbox, gateway, run snapshot이 각자의 형식으로 협업 상태를 전달한다. 먼저 로컬 단일 프로세스에서도 동일하게 적용되는 message contract와 delivery semantics를 정의한다.

## 착수 상태

`messages.py`의 actor·authority·correlation·schema envelope와 `dispatcher.py`의 local command dedupe/event subscription을 추가했다. 외부 broker 없이도 at-least-once command와 best-effort progress 의미를 테스트하며, SSE/MCP gateway는 adapter 단계로 남긴다.

**2026-07-16 update — CM1 착수(콜백 채널 완료).** `messages.py`/`dispatcher.py`는 여전히 프로덕션 어디에도
연결돼 있지 않다(`JsonValue` 타입 재사용뿐). [CM1 message inventory](./evidence/cm1-message-inventory-2026-07-16.md)가
Room `on_event(type, payload)` 콜백 채널의 40개 이벤트 타입 전부를 6종 분류로 정리했고,
`scripts/message_inventory_scan.py` + `tests/test_message_inventory.py`로 drift를 자동 검증한다.
핵심 발견: work_request/artifact_ref가 0건 — 지금 콜백은 순수 fire-and-forget 알림뿐이라 CM2 registry
설계 전에 그 두 종류가 실제로 필요한지부터 결정해야 한다. SSE/chat/dispatch ledger/MCP/gateway는 채널
단위 개요만 남겼고, 항목 단위 전수 조사는 아직이다.

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

## 13. CM2~CM8 재범위 결정 (2026-07-16)

> [CM1 message inventory](./evidence/cm1-message-inventory-2026-07-16.md)가 나온 뒤 CM2~CM8을 그대로
> 진행할지 판단한 결과. §11의 CM2~CM8 산출물/acceptance criteria는 이 절이 대체한다 — 삭제하지 않고
> 남겨두는 건 "왜 그렇게 계획했었는지" 기록으로만 유효하다.

### D6. Command·Domain Event·Human Decision은 이미 `messages.py` 밖에 durable 구현이 있다

CM2(schema registry)를 `messages.py`/`dispatcher.py` 위에 일반적으로 지으려 했지만, 6종 중 3종은
이미 도메인 전용으로 더 성숙한 구현이 production에 연결돼 있다:

| kind | 실제 구현 | 상태 |
| --- | --- | --- |
| Command | `mission/kernel.py`의 `MissionCommand`(OpenPlan·ApprovePlan·StartExecution·...) | schema-versioned event로 변환, `journal.py`가 append-only 저장 |
| Domain Event | `mission/kernel.py`의 이벤트(PlanApproved·MergeCommitted·OraclePassed·...) | `event_codec.py`가 encode/decode, replay 가능 |
| Human Decision | `mission/decision_queue.py` + `decision_repository.py` | durable state machine, optimistic lock(§7.3), production Human Inbox route에 연결(2026-07-15) |

제네릭 envelope 위에 이 세 kind를 다시 만드는 건 이미 테스트되고 실제 라우트에 붙어 있는 도메인 전용
구현을 퇴화시키는 셈이다. **CM2/CM3는 취소한다** — 만들 필요가 없다.

### D7. Progress는 지금 그대로가 맞다

CM1이 찾은 40개 콜백 이벤트 중 9개가 progress다. §5.1이 이미 "progress: best-effort, gap 허용"이라고
정의했고, 지금 구현(in-process callback → SSE, journal 없음)이 정확히 그 요구를 만족한다. schema
versioning이나 durable delivery를 얹으면 복잡도만 늘고 progress의 설계 의도(유실 허용)에 반한다.
**CM6의 durable delivery는 progress 채널에는 적용하지 않는다.**

### D8. Work Request/Result가 유일한 실질적 gap이지만, 범위가 다른 문제다

`agent/envelope.py::parse_agent_response`가 agent 응답의 자연어와 제어 directive를 같이 파싱하는
방식이 §2 결함("agent output 텍스트 안의 directive가 routing protocol 역할")에 정확히 해당한다.
CM1에서도 work_request가 0/40으로 확인됐다 — 구조화된 work request 프로토콜이 지금 어디에도 없다.

하지만 이걸 고치려면 `room/agent_invoke.py`의 실제 agent 호출 hot path와 `agent/envelope.py`를 바꿔야
한다. 이건 "메시지 스키마 하나 등록"이 아니라 agent 협업 프로토콜 자체의 재설계이고, 살아있는 agent
호출 경로를 건드리는 만큼 별도 검토·설계가 필요하다. **CM4를 이 섹터 안에서 계속하지 않는다** — 별도
섹터/RFC로 분리 제안한다(이번 결정 범위 밖).

### D9. Artifact Reference는 이미 기능적으로 존재한다

`plan/execute_snapshot.py`의 manifest(파일별 hash·목록)가 content-addressed artifact 참조 역할을
사실상 수행하고 있다. 이름이 `ArtifactRef`가 아닐 뿐 기능은 있다. **새로 만들 게 없다.**

### D10. `messages.py`/`dispatcher.py`의 앞으로

Retire하지 않는다 — `tests/test_mission_messages.py`/`test_local_dispatcher.py`가 이미 있고,
`ActorKind`/`MessageKind` 어휘는 문서 vocabulary로서 여전히 유효하다. 하지만 **CM2 이후 아무것도 이
파일 위에 짓지 않는다.** 파일 상단에 "prototype, superseded by domain-specific durable
implementations(mission/kernel·decision_queue)" 주석을 남기는 정도로 충분 — 코드 삭제는 이번
결정의 범위 밖(별도 실행 승인 필요).

### 재범위 요약

| 원래 마일스톤 | 결정 |
| --- | --- |
| CM2 schema registry | 취소 — Mission kernel/decision_queue가 이미 담당(D6) |
| CM3 typed local dispatcher | 취소 — 동일 이유(D6) |
| CM4 agent work protocol | 이 섹터에서 분리, 별도 RFC 필요(D8) |
| CM5 Human decision protocol | 이미 완료됨(§7.3) — CM1이 재확인, 추가 작업 없음 |
| CM6 durable delivery/replay | Mission journal이 command/event/decision에는 이미 제공. progress에는 적용 안 함(D7) |
| CM7 SSE/gateway adapters | SSE는 `mission/read_model.py`가 사실상 adapter. gateway(Telegram 등)는 섹터 08 범위 밖 — 별도 문서화 필요 |
| CM8 legacy protocol 제거 | 대상 없음 — retire 안 하기로 했으므로(D10) |

**결론: 08 sector는 CM1 완료로 사실상 종료.** 남은 유일한 실질 작업(agent work request 프로토콜)은
새 섹터로 분리해야 다음 실행 단계를 잡을 수 있다.
