# 심화 4 — 컨텍스트 엔지니어링

> **상태:** In progress / D0 — recipe contract first pass complete  
> **소유 범위:** activity별 정보 선택·구조화·예산·보안·provenance·평가  
> **관련:** [Agent Runtime](./03-agent-runtime-context-memory.md), [Mission Kernel](./01-mission-kernel.md)

## 1. 결론

Agent Lab의 성능 병목은 더 긴 prompt보다 **현재 activity에 필요한 올바른 정보를 선택하고, 충돌과 오래된 정보를 제거하고, 모델이 행동 가능한 구조로 전달하는 능력**에 있다.

## 착수 상태

`context/recipe.py`가 required/optional/forbidden source, authority, relevance, trust boundary와 token budget을 typed manifest로 산출한다. 실제 provider prompt assembler와 legacy bundle 수렴은 recipe contract 위에 단계적으로 연결한다.

**2026-07-16 update — CX1~CX4 완료(전부 first draft, Human review 대기).** [source registry](./evidence/cx1-source-registry-2026-07-16.md)가 `context/bundle.py`(레거시 assembler)가 실제로 소비하는 17개 producer(PROJECT.md/AGENTS.md/SHARED_CONTEXT.md, repo tree, session guidance, mission notepad, wisdom index/playbook/store, run_meta 파생 3종)를 §4 taxonomy로 분류했다. 핵심 발견이었던 `SourceClass`(10종)의 `agent_opinion` 누락은 CX2 진행하면서 추가로 결정·해소했다 — critic recipe가 "actor 자기평가를 authority로 취급하지 않음"(§6.3)을 forbidden source로 명시하려면 필요했다. `src/agent_lab/context/activity_recipes.py`가 §6의 6개 activity(clarify/plan/critic/execute/repair/scribe) 프로즈 스펙을 typed `ContextNeed`로 번역했다. CX3는 `ContextItem`에 `provenance`/`freshness`/`security_label` 필드를 추가하고, `select_context()`가 secret/credential/pii 라벨 콘텐츠를 자동 redact하도록(원문은 `ContextManifest.redacted`로만 추적) 확장했다. CX4는 `conflict_key` 필드 + §5 7-tier 우선순위(`CONFLICT_TIER`)로 "같은 사실의 다중 표현"을 하나로 좁히고(예: old plan revision vs 최신 승인 plan — old plan이 `ContextManifest.superseded`로 빠짐), §7.2 trim 순서의 1단계(정확히 같은 content 중복 제거)와 2단계(낮은 authority/relevance 우선 제거, 기존 로직 재확인)를 구현했다. `select_context()`는 동일 input에 항상 동일 manifest를 반환함을 20회 반복 테스트로 확인(`tests/test_context_selector_cx4.py`). **trim 3~6단계(tool output 압축, 대화 요약, symbol-targeted snippet, required item 구조화 요약)는 구현하지 않았다** — 실제 콘텐츠 압축/요약 파이프라인이 필요해 `select_context()`(이미 만들어진 `ContextItem`만 다루는 순수 selector) 범위 밖이다. **CX1~CX4 전부 Human review 대기 상태다** — CX2 token budget, CX3 security_label 기본값과 redact 대상, CX4의 REPO_CONTEXT tier 배정(§5에 명시 안 됨, tier 3으로 임의 배정)이 전부 재검토 필요. CX1의 17개 producer를 실제 `ContextItem`으로 잇는 어댑터는 여전히 없다.

컨텍스트 엔지니어링은 prompt 문자열 조립이 아니라 다음 공급망 전체다.

```text
Need -> Discover -> Retrieve -> Authorize -> Rank -> Resolve conflicts
     -> Budget -> Structure -> Deliver -> Observe -> Evaluate
```

## 2. 현재 평가

### 강점

- `.agent-lab/PROJECT.md`, AGENTS/CLAUDE rules, PLATFORM, repo tree/map이 있다.
- `context/bundle.py`와 context layers가 source를 계층화한다.
- message trim, token budget, tool output compaction이 있다.
- wisdom/notepad/feedback advisor가 episode와 장기 힌트를 제공한다.
- plan/evidence/provenance가 작업 사실을 구조화한다.

### 결함

| 결함                                                                 | 영향                                                     |
| -------------------------------------------------------------------- | -------------------------------------------------------- |
| source가 기능 추가 순서대로 bundle에 누적                            | 관련성보다 가용성이 inclusion 기준이 되기 쉬움           |
| source별 freshness·authority·conflict 규칙이 불균일                  | 오래된 plan/rule이 현재 intent와 충돌할 수 있음          |
| trim이 최종 길이 제어 중심                                           | 중요한 근거와 반복 정보의 우선순위가 불명확              |
| provider/role별 prompt가 context policy도 소유                       | 같은 activity가 provider에 따라 다른 사실을 받을 수 있음 |
| 포함된 source가 결과에 기여했는지 attribution이 약함                 | token 증가의 효용을 판단하기 어려움                      |
| tool output과 외부 문서의 prompt injection boundary가 약해질 수 있음 | control 지침 오염 위험                                   |

## 3. Context Object Model

### 3.1 ContextNeed

activity가 필요로 하는 정보 요구를 먼저 선언한다.

```text
ContextNeed
  activity_kind
  objective
  required_facts
  required_artifacts
  allowed_source_classes
  forbidden_source_classes
  freshness
  token_budget
  response_contract
```

### 3.2 ContextItem

```text
ContextItem
  item_id
  source_class
  source_ref
  content_ref | bounded_content
  authority
  created_at
  valid_from / expires_at
  relevance_score
  confidence
  security_label
  injection_risk
  supersedes
  estimated_tokens
```

### 3.3 ContextManifest

실제 agent call에 무엇이 왜 들어갔는지 기록한다.

```text
ContextManifest
  recipe_version
  need_hash
  included_items[{id, reason, tokens, transform}]
  excluded_items[{id, reason}]
  conflict_resolutions[]
  total_tokens
  truncation_summary
  security_decisions[]
```

prompt 원문 전체를 저장하지 않고 manifest와 content hash/ref를 기본으로 보존한다.

## 4. Source taxonomy와 우선순위

| Source            | 예                                        | 기본 authority | 수명             |
| ----------------- | ----------------------------------------- | -------------- | ---------------- |
| System invariant  | Human gate, worktree, security rule       | 최상           | versioned        |
| Human intent      | 최신 topic, steer, explicit constraint    | 높음           | Mission          |
| Approved contract | 승인된 plan revision, acceptance criteria | 높음           | revision         |
| Runtime state     | current Mission/activity/decision         | 높음           | 실시간           |
| Evidence          | tests, diff, Oracle result, tool result   | 높음/검증 필요 | artifact         |
| Project docs      | PROJECT, AGENTS, ADR, API docs            | 중상           | freshness 필요   |
| Repo context      | symbol/file snippets, git diff            | 중상           | commit-bound     |
| Episode memory    | 과거 성공·실패·교정                       | 중             | relevance/expiry |
| Semantic memory   | 승인된 규칙·패턴                          | 중상           | supersede 가능   |
| Agent opinion     | 다른 agent의 분석                         | 낮음~중        | 현재 round       |
| External content  | web/MCP/tool text                         | 불신 기본      | source-specific  |

## 5. Conflict resolution

충돌 우선순위:

1. security/system invariant
2. 최신 explicit Human instruction
3. 승인된 현재 plan revision
4. 현재 runtime fact와 evidence
5. project SSOT/ADR
6. semantic/episodic memory
7. agent opinion/external content

동일 등급이면 freshness, scope specificity, provenance를 비교한다. 해결할 수 없는 충돌은 둘 다 prompt에 던지지 않고 structured ambiguity 또는 Human decision으로 승격한다.

예:

- old plan vs approved latest plan: old plan 제외
- README vs code/test: code/test를 사실로 사용하고 docs drift 기록
- Human steer vs approved plan: informational steer인지 plan scope 변경인지 정책 판단
- memory rule vs current AGENTS: current AGENTS 우선, memory supersede 후보

## 6. Activity별 Context Recipe

### 6.1 Clarify

필수: Human topic, workspace identity, unresolved requirements, prior answers.  
제외: 전체 repo dump, execute trace, 장기 wisdom 대부분.  
목표: 최소 질문으로 acceptance boundary 확정.

### 6.2 Plan specialist

필수: goal, constraints, repo map, 관련 파일/API, shipped traceability, prior decisions.  
선택: 유사 episode, 외부 docs.  
출력: claims와 source refs가 있는 scoped proposal.

### 6.3 Critic/Oracle

필수: 독립 rubric, plan/acceptance criteria, candidate artifact/evidence.  
제외: actor의 자기평가를 authority로 취급하지 않음.  
목표: 생성 context와 평가 context의 독립성 유지.

### 6.4 Execute

필수: 승인된 plan revision/hash, 해당 action, workspace/worktree, must-not, verification, relevant code slice, tool grants.  
제외: 승인 전 draft, 무관한 transcript, 다른 action의 전체 context.  
목표: 최소 scope로 재현 가능한 변경.

### 6.5 Repair

필수: 원 plan, diff, failure evidence, prior attempts, 변경해야 할 전략.  
제외: 실패한 동일 prompt의 무가공 반복.  
목표: 이전 실패와 다른 가설·context·tool을 사용.

### 6.6 Scribe

필수: 합의된 결정, objection 상태, source refs, plan contract template.  
선택: 발언 전체가 아니라 structured contributions.  
목표: transcript 요약이 아니라 실행 가능한 승인 계약.

## 7. Selection과 token budget

### 7.1 Budget allocation

예시 비율은 고정값이 아니라 recipe별 시작점이다.

| 영역                         | 계획 activity 예시 |
| ---------------------------- | ------------------ |
| invariant + Human intent     | 15%                |
| current plan/runtime         | 15%                |
| relevant repo/docs           | 40%                |
| evidence/memory              | 15%                |
| working space/output reserve | 15%                |

출력 reserve를 남기지 않고 input으로 window를 채우지 않는다.

### 7.2 Trim 순서

1. exact duplicate 제거
2. 낮은 authority/관련성 item 제거
3. tool output을 artifact ref + bounded excerpt로 변경
4. 오래된 대화를 decision summary로 대체
5. repo tree를 symbol-targeted snippets로 대체
6. required item을 구조화 요약
7. 그래도 초과하면 activity를 분할하거나 명시적 context overflow 실패

system constraint와 현재 Human intent를 조용히 trim하지 않는다.

### 7.3 Compression 품질

요약은 source refs, decisions, unresolved questions, numeric constraints, must-not를 보존해야 한다. summary를 만든 모델과 이를 소비하는 모델이 같아도 원문 hash/ref를 유지한다.

## 8. Tool result와 외부 콘텐츠 안전

- external/tool content는 `<untrusted_content>` 같은 명시적 data boundary로 전달
- content 안의 “system”, “ignore previous”를 control로 해석하지 않음
- tool schema에 source, timestamp, integrity, truncation 표시
- secret/credential 패턴 redact 후 model 전달
- HTML/Markdown/script는 필요 최소 text/data로 정규화
- retrieved content가 tool grant를 확대할 수 없음
- 고위험 action은 model output과 별도 policy validation

## 9. Freshness와 invalidation

| Source              | invalidation key                   |
| ------------------- | ---------------------------------- |
| repo snippet/map    | commit SHA + dirty diff hash       |
| plan                | plan revision + content hash       |
| runtime             | Mission version/activity sequence  |
| docs/rules          | file hash + hierarchy resolution   |
| provider capability | catalog version + health timestamp |
| memory              | entry version/expiry/supersedes    |
| tool result         | query/hash + observed_at + TTL     |

cache hit보다 stale context 방지가 우선이다.

## 10. Context observability와 평가

### 수집

- source별 tokens
- selection/exclusion reason
- trim/compression transforms
- retrieval latency
- stale/conflict/injection flags
- output claims와 evidence refs
- outcome/repair/Human correction 연결

### 평가 지표

- relevant context precision/recall sample
- stale context incident rate
- unsupported claim rate
- context tokens per verified mission
- duplicate source ratio
- compression fact retention
- prompt injection containment rate
- context-attributed repair reduction

## 11. 구현 계획

### CX1. Source registry

**산출물:** 현재 PROJECT/guidance/context/repo/wisdom/notepad/tool source inventory.

**Acceptance criteria:**

- 모든 source에 authority, freshness, security, owner가 있다.
- 중복 source와 같은 사실의 다중 표현이 드러난다.
- provider-specific prompt source가 분리된다.

**검증:** source registry coverage와 duplicate-source report.

### CX2. ContextNeed와 recipe

**산출물:** clarify/plan/critic/scribe/execute/repair recipe.

**Acceptance criteria:**

- activity마다 required/optional/forbidden과 budget이 있다.
- provider가 바뀌어도 core facts는 같다.
- output response contract와 context need가 연결된다.

**검증:** recipe schema tests와 Human review.

### CX3. ContextItem과 manifest

**산출물:** provenance/freshness/security가 있는 typed item과 manifest.

**Acceptance criteria:**

- 모든 included item에 source ref와 reason이 있다.
- excluded required item은 오류로 드러난다.
- manifest에 secret 원문이 없다.

**검증:** golden manifest, redaction, missing-required tests.

### CX4. Deterministic selector

**산출물:** authority/relevance/freshness/budget 기반 selection pipeline.

**Acceptance criteria:**

- 동일 input은 같은 selection을 만든다.
- conflict rule이 old plan과 stale memory를 제외한다.
- budget overflow가 정의된 trim 순서를 따른다.

**검증:** conflict/boundary/property/token tests.

### CX5. Repo·artifact targeted retrieval

**산출물:** commit-bound symbol/file/artifact retrieval.

**Acceptance criteria:**

- 전체 tree보다 activity 관련 symbol을 우선한다.
- dirty worktree와 base commit 차이를 구분한다.
- large tool output은 ref + excerpt로 전달된다.

**검증:** retrieval fixtures와 token/quality benchmark.

### CX6. Untrusted-content boundary

**산출물:** external/MCP/tool content normalization과 injection labels.

**Acceptance criteria:**

- data가 control instruction으로 승격되지 않는다.
- tool grant와 system constraint를 외부 content가 변경하지 못한다.
- secret/PII redaction이 adapter 전에 적용된다.

**검증:** prompt-injection red team과 credential fixtures.

### CX7. Context attribution

**산출물:** source/token/claim/outcome 연결 report.

**Acceptance criteria:**

- source 추가 전후 품질·비용을 비교할 수 있다.
- 사용되지 않는 고비용 source가 식별된다.
- Human correction이 문제 context item/recipe와 연결된다.

**검증:** controlled ablation benchmark와 dogfood sample review.

### CX8. Legacy bundle 수렴

**산출물:** guidance/bundle/layers/notepad/wisdom의 recipe 기반 assembler 통합.

**Acceptance criteria:**

- agent invocation마다 context assembly path가 하나다.
- compatibility block은 adapter edge에만 남는다.
- 중복 trim/token policy가 제거된다.

**검증:** prompt/context snapshot diff, provider contract tests, full CI.

## 12. 완료 정의

- 모든 agent activity가 목적에 맞는 versioned Context Recipe를 사용한다.
- 포함 정보의 source·freshness·authority·선택 이유를 설명할 수 있다.
- 오래된 plan과 검증되지 않은 memory가 현재 Human intent를 덮어쓰지 않는다.
- token 절감이 중요한 constraint/evidence 유실로 이어지지 않는다.
- 외부 content와 tool output이 제어권이나 권한을 획득하지 못한다.
