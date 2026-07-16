# 심화 4 — 컨텍스트 엔지니어링

> **상태:** In progress / D0 — recipe contract first pass complete  
> **소유 범위:** activity별 정보 선택·구조화·예산·보안·provenance·평가  
> **관련:** [Agent Runtime](./03-agent-runtime-context-memory.md), [Mission Kernel](./01-mission-kernel.md)

## 1. 결론

Agent Lab의 성능 병목은 더 긴 prompt보다 **현재 activity에 필요한 올바른 정보를 선택하고, 충돌과 오래된 정보를 제거하고, 모델이 행동 가능한 구조로 전달하는 능력**에 있다.

## 착수 상태

`context/recipe.py`가 required/optional/forbidden source, authority, relevance, trust boundary와 token budget을 typed manifest로 산출한다. 실제 provider prompt assembler와 legacy bundle 수렴은 recipe contract 위에 단계적으로 연결한다.

**2026-07-16 update — CX1~CX4 완료(전부 first draft, Human review 대기).** [source registry](./evidence/cx1-source-registry-2026-07-16.md)가 `context/bundle.py`(레거시 assembler)가 실제로 소비하는 17개 producer(PROJECT.md/AGENTS.md/SHARED_CONTEXT.md, repo tree, session guidance, mission notepad, wisdom index/playbook/store, run_meta 파생 3종)를 §4 taxonomy로 분류했다. 핵심 발견이었던 `SourceClass`(10종)의 `agent_opinion` 누락은 CX2 진행하면서 추가로 결정·해소했다 — critic recipe가 "actor 자기평가를 authority로 취급하지 않음"(§6.3)을 forbidden source로 명시하려면 필요했다. `src/agent_lab/context/activity_recipes.py`가 §6의 6개 activity(clarify/plan/critic/execute/repair/scribe) 프로즈 스펙을 typed `ContextNeed`로 번역했다. CX3는 `ContextItem`에 `provenance`/`freshness`/`security_label` 필드를 추가하고, `select_context()`가 secret/credential 라벨 콘텐츠를 자동 redact하도록(원문은 `ContextManifest.redacted`로만 추적) 확장했다. CX4는 `conflict_key` 필드 + §5 7-tier 우선순위(`CONFLICT_TIER`)로 "같은 사실의 다중 표현"을 하나로 좁히고(예: old plan revision vs 최신 승인 plan — old plan이 `ContextManifest.superseded`로 빠짐), §7.2 trim 순서의 1단계(정확히 같은 content 중복 제거)와 2단계(낮은 authority/relevance 우선 제거, 기존 로직 재확인)를 구현했다. `select_context()`는 동일 input에 항상 동일 manifest를 반환함을 20회 반복 테스트로 확인(`tests/test_context_selector_cx4.py`). **trim 3~6단계(tool output 압축, 대화 요약, symbol-targeted snippet, required item 구조화 요약)는 구현하지 않았다** — 실제 콘텐츠 압축/요약 파이프라인이 필요해 `select_context()`(이미 만들어진 `ContextItem`만 다루는 순수 selector) 범위 밖이다.

**2026-07-16 Human review 1차 반영(4건):**
1. `CONFLICT_TIER`에서 `REPO_CONTEXT`를 tier 3(RUNTIME_STATE/EVIDENCE와 동률)에서 tier 4(PROJECT_DOC과 동률)로 내림 — tier 3에 있으면 authority/freshness tie-break에서 stale repo snippet이 현재 runtime fact를 이길 수 있었음(`tests/test_context_selector_cx4.py::test_stale_repo_snippet_cannot_outrank_current_runtime_state_on_a_tie`).
2. `CLARIFY_RECIPE`/`REPAIR_RECIPE`에 빠져 있던 `SYSTEM_INVARIANT`를 필수로 추가 — 모든 activity가 같은 Human gate/security 경계 안에서 동작하므로 6개 recipe 전부 이제 `SYSTEM_INVARIANT`를 요구함(`tests/test_activity_recipes.py::test_every_activity_requires_system_invariant`). §6.2 프로즈에도 `agent_opinion`을 선택 source로 명시해 코드-문서 drift를 닫았다.
3. `REDACTED_SECURITY_LABELS`에서 `pii` 제거 — CX3의 acceptance criteria는 "secret" 원문만 금지했는데 PII까지 파괴적으로 지우면 "사용자에게 메일" 같은 task utility가 깨진다. PII는 CX6 adapter에서 안정적 가명처리/토큰화(PERSON_1/EMAIL_1 등, 참조 무결성·재수화 보존)로 다뤄야 하는 별개 문제 — 지금은 pii 라벨 콘텐츠가 redact 없이 그대로 통과한다(의도된 gap, `tests/test_context_manifest_cx3.py::test_pii_passes_through_unredacted_pending_cx6_pseudonymization`).
4. token budget 검토: `PLAN_RECIPE`(§7.1에서 "relevant repo/docs"가 40%로 최대 배분인데 12000은 좁음) 12000→16000, `REPAIR_RECIPE`(반복되는 repair cycle마다 prior attempt가 누적됨) 8000→10000으로 상향. 구조적으로 `select_context()`는 required item이 budget을 넘으면 조용히 잘라내지 않고 `ContextSelectionError`로 실패하므로, budget이 너무 작을 때의 실패 양상은 "품질 저하"가 아니라 "에러"다 — 그래도 여전히 추정치이며 실측이 필요하다.

**CX1~CX4는 여전히 first draft다** — 위 4건 반영 후에도 CX2 token budget 전반, CX4의 다른 tier 배정 판단은 계속 재검토 대상. CX1의 17개 producer를 실제 `ContextItem`으로 잇는 어댑터는 여전히 없다.

**2026-07-16 코드 리뷰 2차 — `select_context()` 자체의 버그 4건 수정:**
1. **[진짜 버그]** required source에 항목이 여러 개일 때, 이미 요구조건을 충족한 뒤에도 남는 저순위 항목이 budget을 넘으면 전체가 `ContextSelectionError`로 죽었다 — 실제 producer가 하나의 required source에 여러 항목(예: EXECUTE의 code slice 여러 개)을 주면 상시 재현되는 버그. `satisfied_required` 집합으로 "그 source가 이미 대표 항목을 확보했는지" 추적하도록 수정 — 대표(최고 authority) 항목도 budget에 못 들어갈 때만 실패한다.
2. **[엣지 버그]** required source의 유일한 후보가 다른 source와 `conflict_key`를 공유해 tier 경쟁에서 지면, `candidates`(conflict 해소 후)에서 사라져 "missing required sources"로 오탐했다. missing 판정을 conflict 해소 **이전**(`eligible`) 기준으로 바꿨다 — "이 source에 대한 근거가 있었는가"와 "그 근거가 최종적으로 어떤 항목으로 대표되는가"를 분리.
3. **[정확성]** freshness tie-break이 서로 다른 source(commit SHA vs ISO timestamp vs plan revision)를 사전식으로 비교해 결정론적이지만 의미 없는 결과를 냈다. `_pick_winner`를 `cmp_to_key` 비교자로 재작성 — freshness는 **같은 source끼리만** 비교하고, cross-source 동률은 authority/relevance로만 가른다.
4. **[gap]** exact-duplicate 제거가 `(source, content)` 키라 PROJECT_DOC과 REPO_CONTEXT가 같은 텍스트를 담아도 둘 다 살아남아 budget을 두 번 먹었다. §7.2 "exact duplicate 제거"는 source 무관 해석으로 명시적으로 결정 — 키를 content 단일 축으로 바꿨다.

4건 전부 `tests/test_context_selector_review2.py`에 전용 회귀 테스트가 있다.

**2026-07-16 코드 리뷰 3차 — 구성(construction)-시점 검증 4건 + 참고 개선 1건:**
1. **[보안]** `security_label`이 `SECURITY_LABELS` 어휘에 속하는지 전혀 검증하지 않아, 오타("secrt")나 비표준 라벨("internal")을 달면 `_redact_if_needed`가 그냥 통과시켰다 — "secret" 라벨인데 redaction만 실패한 것과 같은 결과. `ContextItem.__post_init__`에서 fail-closed로 `ValueError` 하도록 수정 — construction 시점에 즉시 잡는다(selection 시점까지 미루지 않음).
2. **[데이터 버그]** `conflict_key=""`가 `None`과 다르게 취급돼, 빈 문자열을 가진 서로 무관한 item들이 전부 "같은 slot"으로 묶여 하나만 남고 나머지가 supersede됐다. `_resolve_conflicts`의 체크를 `is None`에서 falsy(`not item.conflict_key`)로 바꿨다.
3. **[데이터 버그]** `content=""`도 같은 패턴 — 빈 파일 요약, 빈 tool 결과 등 서로 다른 item들이 "exact duplicate"로 오인돼 하나로 찌그러졌다. 빈 content도 REDACTED 항목처럼 dedup 대상에서 제외(passthrough).
4. **[가드레일]** `ContextNeed`가 `required_sources`/`forbidden_sources`(또는 `optional_sources`/`forbidden_sources`) 겹침을 검증 안 해서, 불가능한 recipe가 selection 시점에야 "missing required sources"라는 오해하기 쉬운 에러로 터졌다. `ContextNeed.__post_init__`에서 두 겹침 모두 `ValueError`. `required ∩ optional`은 겹쳐도 무해한 중복이라 그대로 허용(검증 안 함).
5. **[참고 개선]** `ContextItem.trusted` 기본값을 source 기반으로 조정 — `EXTERNAL_CONTENT`는 명시적으로 `trusted=True`를 안 주면 이제 `False`가 기본(09 문서 §8의 untrusted-content boundary). `AGENT_OPINION`은 의도적으로 그대로 둠 — 동료 agent 제안은 injection-safety 문제가 아니라 authority 가중치 문제(이미 tier 6 + 낮은 authority로 반영됨)라서 신뢰 플래그까지 자동으로 내리는 건 과함.

5건 전부 `tests/test_context_selector_review3.py`에 전용 테스트가 있다(19개).

**2026-07-16 코드 리뷰 4차 — conflict resolution의 "결정 vs 승격" 경계 + 관측성 4건:**
1. **[진짜 버그, §5]** §5는 "해결할 수 없는 충돌은 둘 다 prompt에 던지지 않고 structured ambiguity 또는 Human decision으로 승격한다"고 명시하는데, `_pick_winner`는 항상 승자를 하나 뽑았다 — tier/authority/(같은 source일 때만)freshness/relevance가 전부 동률이면 마지막에 `item_id` 사전순 비교로 "승자"를 결정했다. item_id는 우선순위 신호가 아니라 그냥 문자열이라, 진짜 상충하는 두 사실(같은 `conflict_key`, 같은 authority, 다른 content) 중 하나가 아무 근거 없이 조용히 사라지는 문제였다. `_compare_candidates`를 item_id-tiebreak 없는 `_compare_candidates_core`와, 정렬 안정성만을 위한 얇은 wrapper로 분리하고, `_resolve_group()`이 "핵심 신호가 전부 동률인 그룹"을 감지하면 승자를 뽑지 않고 그룹 전체를 `ContextManifest.unresolved_conflicts`로 승격하도록 바꿨다 — 이 그룹의 item은 `included`/`superseded` 어디에도 들어가지 않는다. required source의 유일한 대표가 이 상태로 빠져도 "missing required sources"로 오탐하지 않는다(2차 리뷰 #2 정책의 연장 — eligible 존재 여부와 conflict 해소 후 생존 여부는 별개).
2. **[실제 버그, 중상]** `_resolve_conflicts`가 exact-content dedup(phase 1)을 `conflict_key` 해소(phase 2)보다 먼저 돌려서, 서로 다른 `conflict_key`를 명시적으로 선언한 두 item이 우연히 같은 텍스트를 담았다는 이유만으로 phase 1에서 먼저 병합됐다 — 예: `conflict_key="plan-slot"`과 `conflict_key="config-slot"`이 둘 다 "pending"이면, 후자의 유일한 대표가 자기 conflict_key가 평가받기도 전에 사라졌다. 서로 다른 `conflict_key`를 선언하는 건 "우리는 다른 사실이다"라는 명시적 주장이므로, 우연한 content 동일성이 이를 무시해선 안 된다. dedup grouping key를 `content` 단일 축에서 `(conflict_key 정규화값, content)`로 바꿨다 — 같은(또는 둘 다 없는) `conflict_key`를 가진 item들은 여전히 content로 dedup되고, 다른 `conflict_key`를 선언한 item들은 phase 1에서 절대 병합되지 않는다.
3. **[관측성 갭, 중]** `ContextManifest.excluded`/`.superseded`가 사유·승자 정보 없는 flat item_id tuple이라, forbidden/not-allowed/untrusted/budget-overflow 4가지 서로 다른 배제 원인이 구분 불가능했고 어떤 item이 무엇에게 졌는지도 기록이 없었다. `excluded`를 `tuple[(item_id, reason), ...]`(`EXCLUDE_REASONS` = forbidden/not_allowed/untrusted/budget_overflow)로, `superseded`를 `tuple[(loser_id, winner_id), ...]`로 바꾸고, #1의 결과를 담을 `unresolved_conflicts: tuple[tuple[str, ...], ...]` 필드를 추가했다. §3.3이 지향하는 `included_items[{id, reason, tokens, transform}]`/`excluded_items[{id, reason}]`/`conflict_resolutions[]` 스키마로의 완전한 수렴은 아니지만(그건 §3.3 자체를 구현하는 더 큰 작업), 리뷰에서 지적한 "사유 구분 불가"와 "승자 미기록" 두 갭은 닫았다.
4. **[계약, 하-중]** `select_context()`가 입력 `items`의 `item_id` 유일성을 검증하지 않았다 — 중복이 있으면 `redacted_ids & included_ids` 교집합 로직과 excluded/superseded id 매칭이 어느 쪽 item을 가리키는지 불명확해질 수 있었다. `select_context()` 진입부에서 중복 `item_id`를 감지하면 즉시 `ContextSelectionError`로 fail-closed.

4건 전부 `tests/test_context_selector_review4.py`에 전용 회귀 테스트가 있다(11개) — 기존 `tests/test_context_selector_review2.py::test_identical_content_from_different_sources_is_deduplicated`도 #1의 새 동작(진짜 동률은 이제 item_id로 결정되지 않고 승격됨)에 맞춰 갱신했다.

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
선택: 유사 episode, 외부 docs, 다른 agent의 제안/분석(Room 멀티에이전트 라운드에서 나온 동료 proposal — authority는 낮게, 참고용).  
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
