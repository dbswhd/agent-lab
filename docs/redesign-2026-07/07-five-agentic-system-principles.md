# 심화 2 — 에이전틱 시스템 구축 5원칙

> **상태:** In progress / D0 — principles mapped to fitness gates  
> **소유 범위:** 확장성·모듈성·지속 학습·회복탄력성·미래 대비의 설계 및 운영 gate  
> **관련:** [Reliability](./05-reliability-evaluation-operations.md), [Agent Runtime](./03-agent-runtime-context-memory.md)

## 1. 결론

다섯 원칙은 기능 체크리스트가 아니라 서로 견제하는 설계 제약으로 사용한다. Agent Lab에서 우선순위는 다음과 같다.

## 착수 상태

현재 구현은 모듈성·회복탄력성의 최소 계약부터 적용한다. pure Mission/Activity/Decision 모델과 typed journal이 core policy와 adapter/transport를 분리하며, topology·context·message 모델은 미래 확장을 허용하되 외부 broker나 provider lock-in을 추가하지 않는다.

1. **모듈성:** 잘못된 경계 위에서 확장하면 복잡성만 빠르게 늘어난다.
2. **회복탄력성:** Human gate와 실제 코드 변경을 다루므로 실패가 설명·복구 가능해야 한다.
3. **지속 학습:** 동일 실수를 줄이되 검증되지 않은 기억으로 시스템을 오염시키지 않는다.
4. **확장성:** 먼저 단일 노드에서 Mission 단위 병렬성과 backpressure를 해결한다.
5. **미래 대비:** 내부 domain을 안정시키고 provider/protocol은 adapter로 둔다.

“미래 대비”를 이유로 현재 필요 없는 분산 시스템이나 추상화를 미리 만들지 않는다.

## 2. 원칙 1 — 확장성

### Agent Lab에서의 의미

확장성은 agent 수를 늘리는 능력이 아니라 Mission 부하가 증가해도 품질·안전·비용이 예측 가능한 상태다. 확장 단위는 다음 순서로 본다.

1. 한 Mission 안의 독립 read-only activity 병렬화
2. 여러 Mission의 동시 실행
3. provider별 concurrency와 rate limit 분리
4. 여러 process/node로 worker 분리
5. 외부 queue/actor/workflow engine

### 현재 평가

- parallel Room, dispatch fan-out, background task, scheduler가 있으나 공통 quota/backpressure가 없다.
- 전역 run lock은 안전하지만 독립 Mission 병렬성을 제한한다.
- agent를 추가하면 통신·토큰 비용이 늘지만 marginal lift gate가 약하다.

### 목표 계약

| 항목         | 계약                                                |
| ------------ | --------------------------------------------------- |
| 병렬성       | dependency graph상 독립인 activity만                |
| 격리         | Mission/workspace/provider별 resource scope         |
| backpressure | queue, concurrency, token, cost 상한                |
| degradation  | specialist 축소→lead-only, 품질 gate는 유지         |
| 측정         | throughput뿐 아니라 queue age, cost, retry, quality |

### 금지

- 모든 agent 호출의 무조건 병렬화
- queue 없이 thread/process 생성
- 처리량을 위해 Human/BLOCK/worktree/Oracle gate 약화
- 단일 노드 병목 측정 없이 Kafka/NATS/Ray 도입

### 지표

- missions completed / hour
- queue age p50/p95
- provider saturation
- duplicate work ratio
- cost per verified mission
- quality degradation under load

## 3. 원칙 2 — 모듈성

### Agent Lab에서의 의미

모듈은 파일 수가 아니라 **한 가지 정책 또는 상태의 소유권**을 가진 교체 가능한 경계다. 목표 의존 방향은 `domain ← application ← ports ← adapters/transport`다.

### 현재 평가

- package split과 cycle guard는 개선됐지만 루트 Python 모듈이 134개다.
- Room, plan, mission, runtime이 lifecycle을 나눠 소유한다.
- provider, prompt, tool, stream parsing이 일부 경로에서 함께 결합된다.
- UI feature와 API client가 많은 server field를 직접 조합한다.

### 목표 계약

| 모듈           | 소유하는 것                     | 소유하지 않는 것               |
| -------------- | ------------------------------- | ------------------------------ |
| Mission domain | command, event, invariant       | filesystem, HTTP, provider SDK |
| Application    | use case와 transaction boundary | UI copy, raw subprocess        |
| Agent port     | invocation semantics            | provider-specific stream       |
| Adapter        | 외부 protocol 변환              | domain policy                  |
| Projection     | query/read model                | write authority                |
| Extension      | 선택 capability                 | core state field 추가          |

### 경계 검증

- import direction test
- contract test
- extension-disabled full CI
- provider 교체 smoke
- projection rebuild
- public schema compatibility check

### 금지

- `utils`에 domain policy 숨기기
- cross-package lazy import로 구조 문제만 감추기
- 하나의 `run.json` dict를 공유 인터페이스로 사용
- flag OFF일 때만 모듈성이 유지되는 구조

## 4. 원칙 3 — 지속 학습

### Agent Lab에서의 의미

모델 weight 학습이 아니라 검증된 episode가 다음 Mission의 routing, context, tool, policy 선택을 더 낫게 만드는 폐쇄 루프다.

```text
Observe -> Attribute -> Review -> Promote -> Apply -> Measure -> Supersede
```

### 현재 평가

- outcome ledger, feedback advisor, wisdom index, correction harvester가 있다.
- 하지만 source별 수명·승격 권한·품질 기준이 다르고 contribution attribution이 제한적이다.
- default-off 기능과 적은 표본이 학습 효과 주장에 혼선을 줄 수 있다.

### 메모리 승격 단계

| 단계           | 예                                | 사용 범위                 |
| -------------- | --------------------------------- | ------------------------- |
| Observation    | agent/tool 결과, Human correction | 현재 Mission              |
| Episode        | 검증 결과와 원인 요약             | 유사 Mission recall 후보  |
| Candidate rule | 반복 패턴                         | Human/Oracle review 대기  |
| Semantic rule  | 승인된 프로젝트 규칙              | 기본 context/routing      |
| Superseded     | 오래되거나 반증된 규칙            | 신규 적용 금지, 감사 보존 |

### 학습 안전장치

- provenance와 source ref
- sample size와 confidence
- Human correction 우선순위
- Oracle result와 실제 outcome 분리
- expiry와 supersedes
- rollout cohort와 rollback
- 동일 오류 재발률 측정

### 금지

- 한 번의 성공을 전역 rule로 승격
- raw transcript 전체를 장기 기억으로 사용
- Human 승인 없이 tool permission이나 autonomy ceiling 확대
- benchmark 점수만으로 dogfood 가치 주장

### 지표

- correction recurrence rate
- history-vs-default clean pass delta
- false recall/harmful recall rate
- rule adoption and rollback rate
- feedback loop latency
- memory retrieval precision

## 5. 원칙 4 — 회복탄력성

### Agent Lab에서의 의미

회복탄력성은 실패를 숨기지 않고, 실패 영역을 식별하고, 이미 완료된 안전한 작업을 반복하지 않으며, 자동 복구 또는 명확한 Human 행동으로 수렴하는 능력이다.

### 현재 평가

- worktree, crash recovery, retry, partial turn, pause/resume, Human Inbox가 있다.
- 실패 분류와 retry 정책이 기능별로 분산되어 있다.
- 일부 recovery가 파생 상태를 자동 reconcile하므로 원인과 authority가 흐려질 수 있다.

### 목표 실패 taxonomy

```text
DOMAIN / POLICY / PROVIDER / INFRASTRUCTURE / MODEL_QUALITY /
HUMAN_WAIT / DATA_INTEGRITY / UNKNOWN
```

모든 failure는 `retryable`, `state_preserved`, `side_effect_status`, `next_action`, `evidence_refs`를 가진다.

### 복구 계층

1. adapter 내부 transient retry
2. activity 재시도 또는 대체 provider
3. Mission repair strategy
4. Human Decision Queue
5. terminal failure + exportable diagnostic bundle

### 금지

- blanket exception 후 success처럼 계속 진행
- 동일 prompt/model/tool을 변화 없이 반복
- 복구 중 기존 event/history 수정
- 비가역 side effect 상태 확인 없이 재실행

### 지표

- automatic recovery rate
- duplicate irreversible side effects
- mean actions to recovery
- unknown failure rate
- cancellation success/latency
- recovery explanation coverage

## 6. 원칙 5 — 미래 대비

### Agent Lab에서의 의미

미래 대비는 특정 provider, 모델, transport, 저장소를 교체해도 Mission domain과 Human 권한 모델이 유지되는 것이다.

### 목표 seam

- provider capability manifest와 AgentRuntime port
- tool schema + MCP adapter
- remote agent + A2A adapter
- local journal + optional store adapter
- local queue + optional workflow engine adapter
- OpenTelemetry-compatible trace export
- versioned public command/query schemas

### 채택 기준

새 표준·프레임워크는 다음을 모두 만족해야 한다.

1. 현재의 측정된 문제를 해결한다.
2. 내부 command/event/invariant를 대체하지 않는다.
3. lock-in과 migration 비용이 문서화된다.
4. 작은 adapter spike로 검증된다.
5. 제거와 rollback이 가능하다.

### 금지

- provider prompt format을 domain schema로 사용
- 외부 workflow engine 상태를 유일한 제품 truth로 사용
- A2A/MCP payload를 내부 모든 모듈에 전파
- “언젠가 필요할 것”만으로 dependency 추가

### 지표

- provider replacement effort
- extension removal blast radius
- public schema compatibility
- dependency concentration
- clean-clone reproducibility

## 7. 원칙 간 충돌 해결

| 충돌                 | 선택 규칙                                                    |
| -------------------- | ------------------------------------------------------------ |
| 확장성 vs 단순성     | 현재 SLO가 깨지기 전에는 단순한 local runtime                |
| 지속 학습 vs 안정성  | candidate→review→cohort→promotion 순서                       |
| 회복탄력성 vs 비용   | side-effect risk가 클수록 더 강한 durability                 |
| 모듈성 vs 개발 속도  | reversible duplication은 허용, shared mutable state는 금지   |
| 미래 대비 vs YAGNI   | 안정된 port만 정의하고 adapter는 필요할 때 구현              |
| 자율성 vs Human 통제 | autonomy는 ceiling 안에서만, BLOCK/HIGH risk는 항상 escalate |

## 8. Architecture fitness functions

원칙을 문구가 아니라 자동 검증으로 만든다.

| 원칙       | fitness function                               |
| ---------- | ---------------------------------------------- |
| 확장성     | concurrency/backpressure 부하 시험             |
| 모듈성     | import boundary, contract, extension-off test  |
| 지속 학습  | recurrence/lift/false recall report            |
| 회복탄력성 | fault injection, replay, duplicate-effect test |
| 미래 대비  | mock provider/store 교체 및 clean clone smoke  |

## 9. 구현 계획

### PR1. Principle scorecard baseline

**산출물:** 5원칙별 현재 지표·코드 evidence·unknown 목록.

**Acceptance criteria:**

- 각 원칙에 정량 지표와 정성 review가 있다.
- shipped code와 dogfood value가 구분된다.
- unknown을 임의 점수로 채우지 않는다.

**검증:** scorecard source link 검사와 Human review.

### PR2. Fitness-function CI

**산출물:** import, replay, fault, extension-off, profile 검증 묶음.

**Acceptance criteria:**

- 원칙별 최소 한 개의 자동 gate가 있다.
- ratchet은 개선을 막지 않고 악화만 실패시킨다.
- baseline 변경은 이유와 목표를 요구한다.

**검증:** 의도적 위반 fixture가 각각 실패함을 확인.

### PR3. Learning promotion policy

**산출물:** episode→semantic rule의 검토·승격·폐기 계약.

**Acceptance criteria:**

- provenance/confidence/expiry가 없는 rule은 적용되지 않는다.
- harmful recall을 즉시 비활성화할 수 있다.
- Human correction과 Oracle evidence의 우선순위가 명시된다.

**검증:** poisoned memory, supersede, rollback tests.

### PR4. Capacity and degradation policy

**산출물:** quota, backpressure, lead-only degradation, SLO.

**Acceptance criteria:**

- 부하 시 queue가 증가하되 gate는 유지된다.
- specialist를 줄여도 completion criteria는 바뀌지 않는다.
- 비용 상한 초과가 명시적 Mission 상태로 나타난다.

**검증:** controlled load test와 budget exhaustion journey.

### PR5. Technology adoption ADR gate

**산출물:** provider/protocol/store/framework 도입 template.

**Acceptance criteria:**

- problem evidence, alternatives, exit cost, rollback이 필수다.
- spike 결과 없이는 accepted가 될 수 없다.
- extension lane과 core change를 구분한다.

**검증:** NATS/Temporal/A2A 가상 제안에 template 적용 review.

### PR6. Quarterly architecture review

**산출물:** scorecard trend, expired experiments, deletion candidates, next constraints.

**Acceptance criteria:**

- 각 원칙의 개선과 악화가 diff로 보인다.
- default-off/zero-call-site 기능이 결정된다.
- 다음 분기 구현은 가장 약한 원칙의 병목과 연결된다.

**검증:** 실제 dogfood data로 첫 review 수행.

## 10. 완료 정의

- 다섯 원칙이 각각 코드 evidence, 운영 metric, 승격·폐기 규칙을 가진다.
- 확장성은 agent 수가 아니라 verified mission 품질과 비용을 포함한다.
- 지속 학습은 검증된 기억만 적용하고 언제든 되돌릴 수 있다.
- 회복탄력성은 자동 retry 횟수가 아니라 안전한 수렴으로 측정된다.
- 미래 대비가 불필요한 인프라 선도입의 명분으로 사용되지 않는다.
