# 심화 5 — 멀티 에이전트 조율

> **상태:** In progress / D0 — topology contract first pass complete  
> **소유 범위:** topology 선택, 역할·작업 배정, 합의·비평, 충돌, 예산, 종료  
> **관련:** [Agent Runtime](./03-agent-runtime-context-memory.md), [Messaging](./08-collaboration-messaging.md), `docs/05-room-agent-roles.md`

## 1. 결론

Agent Lab에는 하나의 고정 조율 방식이 맞지 않는다. 다음 혼합형을 기본으로 한다.

## 착수 상태

`topology.py`가 risk, domain 수, exploration budget, rubric 명확성을 기준으로 single·manager/specialist·peer quorum·actor/critic·bounded swarm을 결정한다. 실제 agent fan-out은 lift/cost benchmark 이후에만 연결한다.

- Human: 목표·권한 ceiling·고위험 결정
- Conductor: task graph, agent 선택, budget, termination
- Lead: 주 경로 산출물과 synthesis 책임
- Specialist: 독립된 bounded subtask
- Critic/Oracle: 명시적 rubric에 따른 평가
- Scribe: 승인 가능한 `plan.md` artifact 합성

기본 topology는 **single lead**다. specialist, critic, quorum은 예상 이득이 추가 비용과 지연을 넘을 때만 붙인다. supervisor preset이 존재한다는 이유만으로 모든 turn에 모든 agent를 호출하지 않는다.

## 2. 현재 평가

### 강점

- Cursor/Codex/Claude/Kimi의 역할과 강점이 문서·prompt에 정의돼 있다.
- fast/supervisor preset, lead, roster, consensus, objection이 존재한다.
- parallel dispatch와 scoped delegate가 가능하다.
- plan scribe, peer review, Oracle이 actor-critic과 유사한 품질 루프를 제공한다.
- Human gate가 agent 집단의 최종 authority를 제한한다.

### 결함

| 결함                                                               | 영향                                              |
| ------------------------------------------------------------------ | ------------------------------------------------- |
| agent identity와 역할이 강하게 결합                                | capability·가용성·비용 기반 대체가 어려움         |
| consensus round가 큰 단일 orchestration 함수에 집중                | 종료·충돌·부분 실패 reasoning이 복잡              |
| 전체 transcript 공유와 반복 의견                                   | 통신·token 비용과 anchoring 증가                  |
| 다수 agent 호출의 marginal lift를 turn마다 설명하지 않음           | team이 single lead보다 나은지 불분명              |
| lead, manager, scribe, Oracle의 authority 경계가 경로별로 다름     | 누구의 결과가 다음 상태를 바꾸는지 이해 비용 증가 |
| partial failure와 straggler 처리 정책이 topology별로 명확하지 않음 | 느린 agent가 전체 turn을 지연                     |

## 3. 조율 topology catalog

### 3.1 Single Agent

한 lead가 탐색·산출·간단 검증을 수행한다.

**적합:** 작은 변경, 명확한 질문, 낮은 위험, latency 우선.  
**장점:** 최소 통신·비용, 책임 명확.  
**위험:** 맹점, capability 부족.  
**Agent Lab 기본:** fast path와 모든 topology의 fallback.

### 3.2 Manager + Specialists

Conductor가 task graph를 만들고 독립 specialist에게 배정한 뒤 lead/scribe가 합성한다.

**적합:** 서로 다른 domain, repo 탐색과 UX/테스트처럼 병렬 가능한 subtask.  
**장점:** 전문화·병렬성.  
**위험:** manager 병목, 잘못된 decomposition, 결과 통합 비용.

### 3.3 Peer Review / Quorum

독립 proposal을 만들고 공통 rubric으로 비교·합의한다.

**적합:** 아키텍처·위험·plan approval 전의 고비용 결정.  
**장점:** 관점 다양성, 단일 실패 완화.  
**위험:** 통신 폭증, 합의 지연, majority가 truth라는 착각.

합의는 correctness가 아니라 decision policy다. evidence가 약하면 소수 objection을 표결로 지우지 않는다.

### 3.4 Actor–Critic

actor가 후보를 만들고 critic이 독립 rubric으로 판정한다.

**적합:** 생성보다 평가가 쉽고 acceptance criteria가 명확한 plan, patch, report.  
**장점:** 추가 연산 대비 품질 개선을 측정하기 쉬움.  
**위험:** critic anchoring, 무한 repair loop.

critic은 actor의 숨은 reasoning이 아니라 artifact와 evidence를 평가한다.

### 3.5 Hierarchical Coordination

상위 Conductor가 여러 workstream lead를 관리하고 각 lead가 specialist를 관리한다.

**적합:** 장기 Mission, 여러 package/worktree, 5개 이상 독립 workstream.  
**장점:** manager 병목 분산.  
**위험:** 전달 손실, 권한 모호, 복잡한 cancellation.

현재 agent-lab 기본 규모에는 과하다. task graph와 telemetry에서 manager bottleneck이 증명될 때만 활성화한다.

### 3.6 Swarm / Market-like

다수의 느슨한 agent가 local rule과 shared signals로 탐색한다.

**적합:** 대규모 source discovery, 후보 탐색, 독립 simulation.  
**부적합:** 승인·merge·보안처럼 중앙 authority가 필요한 core lifecycle.  
**결정:** 코어 Mission 실행 topology로 채택하지 않는다. extension/evaluation 실험만 허용한다.

## 4. Topology 선택 정책

### 4.1 입력 특징

```text
CoordinationNeed
  task_complexity
  domain_count
  decomposability
  dependency_density
  uncertainty
  risk
  evaluation_clarity
  time_budget
  token_cost_budget
  available_capabilities
  provider_health
```

### 4.2 선택표

| 조건                                | topology                |
| ----------------------------------- | ----------------------- |
| 단일 domain, 명확, 저위험           | single lead             |
| 2개 이상 독립 subtask               | manager + specialists   |
| 고위험 설계, 관점 다양성 필요       | peer review/quorum      |
| 명확한 rubric, artifact 개선        | actor-critic            |
| workstream이 많고 manager 병목 측정 | hierarchy               |
| 대규모 탐색 실험                    | bounded swarm extension |

### 4.3 Agent 추가 gate

새 agent마다 다음을 기록한다.

- 필요한 capability
- 맡을 고유 subtask
- lead가 대신할 때의 손실
- 병렬화 가능 여부와 dependency
- 예상 quality lift
- 추가 cost/latency
- failure 시 fallback

고유 책임을 설명할 수 없으면 추가하지 않는다.

## 5. 역할과 authority

| 역할       | 결정 가능                                          | 결정 불가                              |
| ---------- | -------------------------------------------------- | -------------------------------------- |
| Human      | goal, scope, plan/diff/high-risk, autonomy ceiling | runtime 내부 scheduling 세부           |
| Conductor  | topology, task assignment, budget, stop/escalate   | Human gate bypass, Oracle verdict 위조 |
| Lead       | proposal, synthesis, routine tactical choice       | plan/diff approval                     |
| Specialist | bounded task artifact와 evidence                   | scope 확장, 다른 specialist 지시       |
| Critic     | rubric verdict와 defect                            | actor artifact 직접 변경               |
| Scribe     | agreed input을 plan contract로 합성                | 새 합의를 임의 생성                    |
| Oracle     | criteria 기반 completion verdict                   | acceptance criteria 변경               |

한 actor가 여러 역할을 수행할 수 있지만 message와 event에는 현재 seat를 기록한다.

## 6. Task graph와 delegation

### 6.1 Task specification

```text
AgentTask
  task_id
  objective
  scope
  deliverable
  acceptance_criteria
  input_refs
  dependency_ids
  capability_requirements
  tool_grants
  budget
  deadline
  stop_conditions
  fallback
```

“레포를 살펴봐” 같은 무한 탐색을 delegate하지 않는다. deliverable과 stop condition을 둔다.

### 6.2 Dependency

- no dependency: 병렬
- data dependency: producer result 후 시작
- review dependency: artifact ready 후 critic 시작
- authority dependency: Human decision 후 시작
- resource conflict: 같은 worktree write는 직렬화

### 6.3 Result contract

specialist는 긴 대화가 아니라 다음을 반환한다.

- concise conclusion
- artifact/source refs
- claims and confidence
- unresolved questions
- risks/objections
- completion status

## 7. 정보 공유 전략

### 7.1 최소 필요 공유

- 공통: goal, invariant, approved plan, current decision
- specialist: scoped task, relevant files/artifacts, dependency result
- critic: artifact + independent rubric + evidence
- scribe: structured contributions + accepted/rejected decisions

전체 transcript broadcast는 기본 금지다.

### 7.2 독립성 보존

peer diversity가 목적이면 첫 proposal 전에 다른 agent 답을 보여주지 않는다. 이후 comparison round에서만 공유한다. critic에게 actor의 자기확신을 authority로 주지 않는다.

### 7.3 Stigmergic artifact

agent가 서로에게 직접 장문 메시지를 보내기보다 plan candidate, repo finding, test result 같은 artifact를 공유 작업공간에 남기고 ref로 전달한다. artifact에는 owner, revision, hash, status가 있다.

## 8. 합의와 충돌 해결

### 8.1 합의 대상

- 사실: evidence로 판정
- 설계 선택: criteria와 trade-off로 비교
- scope/권한: Human 결정
- completion: Oracle/evidence
- preference: lead recommendation 또는 Human 선택

모든 것을 vote로 해결하지 않는다.

### 8.2 Objection model

```text
Objection
  claim
  category: safety | correctness | scope | evidence | cost | preference
  severity
  evidence_refs
  blocking
  proposed_resolution
  owner
```

safety/correctness blocking objection은 단순 majority로 닫지 않는다. evidence, plan revision, Human override 중 하나를 요구한다.

### 8.3 Quorum

quorum은 participant 수가 아니라 필요한 seat/capability로 정의한다.

예:

- plan gate: lead proposal + independent critic + no unresolved blocking objection
- high-risk merge: execute evidence + merge checks + Oracle readiness + Human approval

### 8.4 Tie/timeout

- evidence가 더 강한 안 선택
- reversible한 안 우선
- 비용이 낮은 실험으로 정보 획득
- unresolved high-risk는 Human escalate
- low-risk/time-boxed는 lead 결정 후 기록

## 9. Actor–Critic loop

```text
Actor produces Artifact v1
Critic evaluates against Rubric vN
  PASS -> next gate
  REVISE -> bounded defect list
Actor produces v2 with change summary
  max iterations reached -> Human/terminal decision
```

필수 제한:

- max iterations
- critic defect deduplication
- 매 iteration의 변경 전략
- quality threshold
- cost/time budget
- 같은 critic/model의 반복 편향 감시

## 10. 부분 실패와 straggler

### Partial success

독립 specialist 하나가 실패해도 다음을 판단한다.

- deliverable에 필수 seat인가
- lead가 대체 가능한가
- 다른 provider로 retry할 가치가 있는가
- degraded synthesis가 안전한가

### Straggler

- soft deadline에 partial result 요청
- speculative duplicate는 high-value/side-effect-free task에만
- quorum이 충족되고 늦은 seat가 필수가 아니면 취소
- high-risk critic을 latency 때문에 생략하지 않음

### Manager failure

Conductor state는 task graph/event에 있으므로 새 coordinator가 재구축 가능해야 한다. manager의 대화 메모리에만 작업 상태를 두지 않는다.

## 11. Budget와 종료

### Budget

- max agents
- max concurrent calls
- max rounds
- max critic iterations
- token/cost/time budget
- per-provider quota

### 종료 조건

- deliverable과 criteria 충족
- required seats 완료
- blocking objection 없음 또는 명시적 resolution
- marginal information gain이 임계값 아래
- budget 소진
- Human stop/pause
- terminal infrastructure/policy failure

“모두 동의할 때까지”는 종료 조건으로 사용하지 않는다.

## 12. 측정

| 지표                        | 의미                                         |
| --------------------------- | -------------------------------------------- |
| single-to-team lift         | team 사용의 실제 품질 이득                   |
| coordination overhead ratio | 전체 token/time 중 조율 비중                 |
| duplicate work ratio        | 같은 탐색·주장의 반복                        |
| synthesis loss rate         | specialist evidence가 최종 artifact에서 유실 |
| objection precision         | blocking objection이 실제 defect였는가       |
| critic repair yield         | iteration당 결함 감소                        |
| straggler wait cost         | 늦은 seat 때문에 증가한 시간                 |
| escalation rate             | topology가 Human 판단으로 수렴한 비율        |
| role substitution success   | provider/agent 교체 가능성                   |

## 13. 구현 계획

### CO1. Coordination inventory

**산출물:** turn contract, role plan, dispatch, consensus, scribe, Oracle의 authority/task map.

**Acceptance criteria:**

- 모든 seat에 input, output, authority, stop condition이 있다.
- 중복된 manager/lead 역할이 드러난다.
- 자연어 directive와 structured control을 구분한다.

**검증:** 현행 supervisor fixture 5개의 seat trace review.

### CO2. Topology decision contract

**산출물:** CoordinationNeed와 topology selection 함수.

**Acceptance criteria:**

- 같은 입력 특징은 같은 topology를 선택한다.
- agent 추가마다 고유 책임과 budget이 기록된다.
- single lead fallback이 항상 정의된다.

**검증:** table-driven policy tests와 boundary cases.

### CO3. Typed AgentTask와 Result

**산출물:** objective/scope/deliverable/dependency/criteria/result schema.

**Acceptance criteria:**

- 무한 탐색 task가 schema validation을 통과하지 못한다.
- result가 artifact/evidence ref와 unresolved 항목을 포함한다.
- tool grant가 task scope에 결합된다.

**검증:** dispatch contract tests와 malformed task fixtures.

### CO4. Selective context routing

**산출물:** seat/task별 context recipe와 artifact sharing.

**Acceptance criteria:**

- specialist가 전체 transcript 없이 task를 수행한다.
- independent proposal round에서 다른 답이 숨겨진다.
- scribe가 structured contribution을 사용한다.

**검증:** token ablation, diversity, synthesis retention benchmark.

### CO5. Objection·quorum policy

**산출물:** typed objection, capability quorum, resolution state.

**Acceptance criteria:**

- blocking correctness/safety objection을 vote로 닫지 않는다.
- preference disagreement와 defect가 구분된다.
- timeout이 deterministic fallback/escalation으로 수렴한다.

**검증:** objection/quorum/timeout scenario tests.

### CO6. Actor–critic bounded loop

**산출물:** versioned artifact, rubric, defect list, iteration budget.

**Acceptance criteria:**

- 각 iteration이 변경된 전략과 defect resolution을 기록한다.
- 동일 defect 반복과 max iteration이 종료된다.
- critic failure가 actor result를 자동 PASS시키지 않는다.

**검증:** pass/revise/repeat/critic-timeout fixtures.

### CO7. Partial failure와 substitution

**산출물:** required/optional seat, fallback, straggler policy.

**Acceptance criteria:**

- optional specialist failure가 안전한 경우 전체를 중단하지 않는다.
- required critic failure는 대체 또는 Human escalation으로 간다.
- provider 교체가 task/result contract를 바꾸지 않는다.

**검증:** provider-down, partial result, late result tests.

### CO8. Lift-based rollout

**산출물:** single/manager/peer/actor-critic 비교 benchmark와 topology promotion policy.

**Acceptance criteria:**

- 품질, cost, latency, Human effort를 함께 비교한다.
- lift가 없는 topology는 default에서 제거된다.
- supervisor도 topic/task에 따라 single lead를 선택할 수 있다.

**검증:** mock corpus + live dogfood cohort report.

## 14. 완료 정의

- topology가 preset 이름이 아니라 task 특징과 risk/evaluation clarity로 선택된다.
- 모든 agent가 고유한 책임·deliverable·budget·stop condition을 가진다.
- 정보 공유는 task/artifact 중심이며 전체 transcript broadcast가 기본이 아니다.
- 합의, objection, Oracle, Human authority의 의미가 분리된다.
- 멀티 에이전트의 품질 이득이 비용·지연 대비 측정되고, 이득이 없으면 single lead로 축소된다.
