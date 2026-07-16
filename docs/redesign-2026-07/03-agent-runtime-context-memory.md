# Sector 3 — 에이전트 런타임·도구·컨텍스트·메모리

> **상태:** In progress / D0 — context contract first pass complete  
> **선행:** Mission command/activity와 event envelope  
> **후행:** Human UX의 agent activity, 운영 평가

## 1. 목표

Cursor, Codex, Claude, Kimi Work를 제품의 고정된 분기문이 아니라 동일한 `AgentRuntime` 계약을 구현하는 capability provider로 다룬다. 컨텍스트는 매 단계의 목적에 맞게 선택·예산화하며, 메모리는 working/episodic/semantic으로 구분한다.

## 착수 상태

`src/agent_lab/context/recipe.py`가 activity 목적·source authority·신선도·token budget을 결정적으로 선택한다. 현재는 recipe contract와 테스트를 먼저 고정했으며 guidance/notepad/wisdom assembler의 단일 writer 전환은 후속 단계다.

**2026-07-16 update — A1 완료.** [provider capability inventory](./evidence/a1-provider-capability-inventory-2026-07-16.md)가 `agent/health.py::agent_health_row()`의 6개 provider(cursor/codex/claude/kimi/kimi_work/local) 분기를 매트릭스로 고정했다. 핵심 발견: base 필드 7개만 공통이고 나머지(auth_mode, bridge 실측, loop_phase 등)는 provider별 ad hoc — `ready=False`가 여러 실패 원인을 구분 안 함. tool capability는 4/6 provider(`kimi`/`local` 제외)에만 등록됨. **cancel/resume은 후속 조사로 채워짐**: cancel은 `run.control`의 `is_cancelled()`/`register_child_process()`로 4/6 provider(tool capability와 정확히 같은 집합)가 이미 지원하고, resume(thread 재개)은 3/6(`cursor`/`codex`/`claude`)이 지원 — `kimi_work`는 cancel은 있지만 resume은 없는 비대칭. `runtime/adapters/execute.py`·`discuss.py`가 이미 activity별 부분 invoke 추상화를 갖고 있어 A2(AgentRuntime port)는 이 둘을 일반화하는 데서 시작하면 된다 — cancel/resume 인터페이스 설계는 더 이상 막혀 있지 않다.

## 2. 현재 평가

### 강점

- provider별 CLI/SDK adapter, health/preflight, model catalog가 존재한다.
- 세션 capability, MCP allowlist, prompt guidance, context layer가 이미 있다.
- Kimi daimon, Cursor bridge 등 서로 다른 실행 모델을 실제로 다룬 경험이 있다.
- subprocess env allowlist와 tool envelope는 안전한 기반이다.

### 결함

| 결함                                                                     | 영향                                                       |
| ------------------------------------------------------------------------ | ---------------------------------------------------------- |
| provider lifecycle·stream parsing·prompt 정책이 provider별로 다르게 결합 | 새 provider 추가가 코어 변경을 유발                        |
| agent 역할이 이름과 prompt에 강하게 묶임                                 | 같은 모델의 capability·비용·가용성 기반 동적 배치가 어려움 |
| context source가 guidance/bundle/layers/repo map/wisdom/notepad로 누적   | 무엇이 왜 포함됐는지 설명하기 어려움                       |
| PROJECT, wisdom, outcome, memory store의 수명·쓰기 권한이 다름           | 장기 메모리의 품질·오염 통제가 약함                        |
| 도구 발견과 세션 mount는 있으나 실제 사용 기여 attribution이 약함        | 도구 수가 늘어도 가치 판단이 어려움                        |

## 3. 설계 결정

### D1. Agent는 이름이 아니라 capability manifest로 선택한다

```text
AgentManifest
  provider_id
  models
  capabilities: [repo_read, edit, shell, web, critique, long_context, mcp]
  transports: [cli, sdk, daemon, http]
  isolation
  concurrency_limit
  cost_class
  health
```

`Cursor/Codex/Claude/Kimi` 역할 기본값은 UX preset으로 남길 수 있지만 scheduler는 task requirement와 manifest를 비교한다.

### D2. 공통 invocation 계약을 둔다

```text
AgentRequest
  activity_id, objective, response_contract
  context_refs, tool_grants, budget, deadline

AgentEvent
  started, progress, tool_requested, tool_result_ref,
  output_chunk, completed, failed, cancelled

AgentResult
  artifact_refs, summary, claims, usage, termination
```

provider adapter는 raw stream을 공통 event로 번역한다. 코어는 provider 고유 메시지를 해석하지 않는다.

### D3. 멀티 에이전트 추가는 이득 계약을 요구한다

추가 agent dispatch 조건:

- 독립적으로 병렬화 가능한 작업인가
- 필요한 전문 capability가 lead에 없는가
- 실패 격리 또는 대안 검증의 가치가 있는가
- 예상 품질 이득이 비용·지연·조율 오버헤드를 넘는가

기본 topology는 `lead + optional specialist + optional critic`이다. 전원 브로드캐스트는 명시적 high-risk policy에서만 허용한다.

### D4. Context는 단계별 recipe로 조립한다

```text
ContextRecipe
  activity_kind
  required_sources
  optional_sources
  exclusions
  token_budget
  freshness
  provenance_required
```

선택 순서: system constraints → current goal/command → relevant plan/evidence → recent episode summary → targeted repo/docs → optional semantic memory. 단순히 사용 가능한 모든 정보를 넣지 않는다.

### D5. 메모리 계층을 분리한다

| 계층     | 내용                                    | 수명                  | 쓰기                          |
| -------- | --------------------------------------- | --------------------- | ----------------------------- |
| Working  | 현재 activity 입력·도구 결과·최근 대화  | activity/turn         | runtime                       |
| Episodic | mission 요약, 결정, 실패, 교정, outcome | mission/cross-session | event projector               |
| Semantic | 검증된 프로젝트 규칙·패턴·도구 카드     | 장기                  | Human 승인 또는 검증 pipeline |

Semantic memory에 모델의 임의 관찰을 자동 승격하지 않는다. provenance, confidence, supersedes, expiry를 요구한다.

### D6. MCP/A2A는 edge protocol로 취급한다

MCP는 tool/context adapter, A2A는 원격 agent adapter가 될 수 있다. 둘 다 Mission domain schema를 대체하지 않는다. 외부 protocol payload는 경계에서 내부 request/event로 변환한다.

## 4. 구현 계획

### A1. Provider capability inventory

**산출물:** 현재 provider 기능·인증·stream·cancel·resume·tool 지원 매트릭스.

**Acceptance criteria:**

- 모든 provider가 공통 capability vocabulary로 표현된다.
- provider-specific 예외가 adapter 내부/외부 중 어디에 속하는지 결정된다.
- unavailable/degraded/healthy 의미가 통일된다.

**검증:** health fixture와 catalog snapshot.

### A2. AgentRuntime port와 contract tests

**산출물:** invoke/cancel/resume/events/result interface.

**Acceptance criteria:**

- mock adapter와 실제 adapter 하나가 같은 contract suite를 통과한다.
- timeout, cancellation, malformed stream, auth failure가 typed termination으로 변환된다.
- tool grant 밖 호출은 실행 전 거부된다.

**검증:** adapter contract tests + CLI happy/bad/cancel manual QA.

### A3. Provider adapter migration

**산출물:** Codex, Claude, Cursor, Kimi 순으로 공통 runtime에 연결.

**Acceptance criteria:**

- Room/mission 코어에서 provider-specific import가 사라진다.
- 각 adapter는 raw 로그를 공통 event로 매핑한다.
- 기존 auth와 health UX를 유지한다.

**검증:** provider별 mock replay, opt-in live smoke.

### A4. Context assembler와 explanation

**산출물:** recipe 기반 source selection, token budget, context manifest.

**Acceptance criteria:**

- 모든 agent call에 포함 source/ref/token/reason manifest가 남는다.
- stale plan, 중복 규칙, 금지된 secret source를 제외한다.
- 단계별 token cap 초과 시 deterministic trim/summarize 순서가 있다.

**검증:** golden context tests, prompt injection/redaction tests, token benchmark.

### A5. Memory lifecycle

**산출물:** episodic projection과 semantic promotion inbox.

**Acceptance criteria:**

- user correction과 Oracle outcome이 episode로 연결된다.
- semantic entry는 provenance/confidence/expiry를 가진다.
- 잘못된 memory를 supersede/삭제해도 감사 이력은 남는다.
- retrieval miss가 agent call을 막지 않는다.

**검증:** cross-session recall fixture, poisoned-memory red team, retrieval precision sample.

### A6. Tool registry와 least privilege

**산출물:** tool manifest, grant, audit, contribution attribution.

**Acceptance criteria:**

- tool은 input/output schema, side-effect class, auth scope, timeout을 선언한다.
- activity별 최소 grant만 전달된다.
- 실제 사용과 outcome 기여 후보가 episode에 기록된다.
- 미사용·실패 tool은 자동 mount되지 않는다.

**검증:** unauthorized tool test, MCP compatibility test, tool-card adoption report.

### A7. Topology policy 단순화

**산출물:** task requirement → topology decision 함수와 budget guard.

**Acceptance criteria:**

- agent 추가 이유와 예상 이득이 event로 설명된다.
- fast path는 lead 하나로 완료 가능하다.
- critic은 평가 기준이 생성보다 명확할 때만 추가된다.
- quorum timeout은 Human escalation 또는 lead decision으로 끝난다.

**검증:** single vs team benchmark에서 품질·비용·지연 비교.

## 5. 제거·통합 후보

- provider 이름에 종속된 Room dispatch 분기
- 역할 prompt와 transport 정책이 섞인 코드
- 동일 내용을 여러 guidance block에서 중복 주입하는 경로
- zero-consumer `MemoryStore`와 별도 wisdom store의 중복 개념
- 세션 설정·env·plugin마다 다른 tool enable 방식
- 고정 trio를 모든 supervisor turn에 무조건 호출하는 정책

## 6. 품질 지표

| 지표                                | 목적                                 |
| ----------------------------------- | ------------------------------------ |
| context relevance precision         | 포함 source가 실제 결과에 기여했는가 |
| context tokens / successful mission | 작은 모델·비용 효율                  |
| duplicate work ratio                | 멀티 agent 조율 낭비                 |
| specialist lift                     | single lead 대비 품질 개선           |
| tool success/contribution rate      | 설치보다 실제 가치 측정              |
| memory correction recurrence        | 학습 루프가 같은 실수를 줄이는가     |
| provider cancellation latency       | 통제·복구 가능성                     |

## 7. 완료 정의

- 새 provider는 코어 변경 없이 adapter와 manifest로 추가된다.
- 각 agent call의 목적·context·tool 권한·비용·결과가 추적된다.
- multi-agent 사용 이유가 측정 가능하며 single-agent fast path가 유지된다.
- 장기 메모리는 검증·폐기 가능한 지식이지 무제한 transcript 저장이 아니다.
- MCP/A2A 도입이 내부 domain을 vendor protocol에 결합하지 않는다.
