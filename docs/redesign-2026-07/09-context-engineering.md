# 심화 4 — 컨텍스트 엔지니어링

> **상태:** In progress / D0 — recipe contract first pass complete  
> **소유 범위:** activity별 정보 선택·구조화·예산·보안·provenance·평가  
> **관련:** [Agent Runtime](./03-agent-runtime-context-memory.md), [Mission Kernel](./01-mission-kernel.md)

## 1. 결론

Agent Lab의 성능 병목은 더 긴 prompt보다 **현재 activity에 필요한 올바른 정보를 선택하고, 충돌과 오래된 정보를 제거하고, 모델이 행동 가능한 구조로 전달하는 능력**에 있다.

## 착수 상태

`context/recipe.py`가 required/optional/forbidden source, authority, relevance, trust boundary와 token budget을 typed manifest로 산출한다. 실제 provider prompt assembler와 legacy bundle 수렴은 recipe contract 위에 단계적으로 연결한다.

**2026-07-16 update — CX1~CX4 완료(전부 first draft, Human review 대기).** [source registry](./evidence/cx1-source-registry-2026-07-16.md)가 `context/bundle.py`(레거시 assembler)가 실제로 소비하는 producer(PROJECT.md/AGENTS.md/SHARED_CONTEXT.md, repo tree, session guidance, mission notepad, wisdom index/playbook/store, run_meta 파생 3종 — registry §1 표는 15개 row; 문서 본문의 "17개"는 표 자체의 오기였다, 아래 어댑터 절 참고)를 §4 taxonomy로 분류했다. 핵심 발견이었던 `SourceClass`(10종)의 `agent_opinion` 누락은 CX2 진행하면서 추가로 결정·해소했다 — critic recipe가 "actor 자기평가를 authority로 취급하지 않음"(§6.3)을 forbidden source로 명시하려면 필요했다. `src/agent_lab/context/activity_recipes.py`가 §6의 6개 activity(clarify/plan/critic/execute/repair/scribe) 프로즈 스펙을 typed `ContextNeed`로 번역했다. CX3는 `ContextItem`에 `provenance`/`freshness`/`security_label` 필드를 추가하고, `select_context()`가 secret/credential 라벨 콘텐츠를 자동 redact하도록(원문은 `ContextManifest.redacted`로만 추적) 확장했다. CX4는 `conflict_key` 필드 + §5 7-tier 우선순위(`CONFLICT_TIER`)로 "같은 사실의 다중 표현"을 하나로 좁히고(예: old plan revision vs 최신 승인 plan — old plan이 `ContextManifest.superseded`로 빠짐), §7.2 trim 순서의 1단계(정확히 같은 content 중복 제거)와 2단계(낮은 authority/relevance 우선 제거, 기존 로직 재확인)를 구현했다. `select_context()`는 동일 input에 항상 동일 manifest를 반환함을 20회 반복 테스트로 확인(`tests/test_context_selector_cx4.py`). trim 3~6단계(tool output 압축, 대화 요약, symbol-targeted snippet, required item 구조화 요약)는 처음엔 구현하지 않았다 — 실제 콘텐츠 압축 파이프라인이 필요해 `select_context()`(이미 만들어진 `ContextItem`만 다루는 순수 selector) 범위 밖이었다. 아래 "§7.2 trim 3~6단계" 절에서 별도 모듈(`context/compress.py`)로 구현했다.

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

**2026-07-16 코드 리뷰 5차 — 4차에서 새로 만든 escalation 로직 자체의 정합성 버그 2건 + 경미 2건:**
1. **[일관성 구멍, 높음]** required source의 유일한 대표 item(들)이 전부 `unresolved_conflicts`로 빠지면 `candidates`엔 아무것도 없는데, coverage 체크가 conflict 해소 **이전**(`eligible`) 기준이라 missing 오탐이 안 나고 manifest가 조용히 그 required source 없이 반환됐다 — CX3 "excluded required item은 오류로 드러난다", §12 "required가 목적에 맞게 들어간다"를 우회하는 결과. `unresolved_conflicts`는 advisory 필드라 안 보는 caller는 그대로 실행한다. `candidates`(해소 후) 기준으로 required source가 대표를 못 얻었는지 다시 확인하고, 그 source의 eligible item 중 하나라도 `unresolved_conflicts`에 있으면 `ContextSelectionError("required source unresolved: ...")`로 fail — 반면 다른 source의 상위 대표에게 **깔끔하게** superseded된 경우(2차 리뷰 #2 정책)는 그대로 통과시켜 기존 동작을 보존했다.
2. **[정확성, 높음]** `_compare_candidates_core`가 freshness 비교를 `a.source == b.source`로 게이팅해서, 그룹이 여러 source를 섞으면 비교자가 비추이적(non-transitive)이 됐다 — 같은 source인 A/C는 freshness로 A가 C를 확실히 이기는데, 다른 source의 B가 tier/authority/relevance만으로 A/C 둘 다와 동률이면, 하나의 `sorted()`에 셋을 함께 넣었을 때 A가 C를 이긴 진짜 해소가 사라지고 셋 다 통째로 escalate될 위험이 있었다(비교 가능성이 pair에 의존해 total preorder가 아님). `_resolve_group`을 2단계로 재작성: **1단계**— source별로 partition해서 그 안에서만 기존 비교자(같은 source라 항상 유효)로 대표 1개를 뽑는다(그 source 자체가 내부적으로도 동률이면 대표 없이 그 source의 bucket 전체를 "내부 미해결"로 들고 간다). **2단계** — 각 source의 대표(또는 내부 미해결 bucket)를 `_cross_source_rank`(tier/authority/relevance만, freshness 제외 — plain tuple key라 항상 추이적)로 비교. 최상위 rank를 단독으로 차지하는 대표가 하나면 그게 승자이고 나머지는 전부(내부 미해결 bucket 포함) 깔끔하게 superseded — 내부 동률인 source라도 tier가 명백히 밀리면 그 동률과 무관하게 진다. 최상위 rank를 2개 이상이 공유하면(또는 최상위가 그 자체로 내부 미해결이면) 그 최상위 뭉치만 `unresolved_conflicts`로 승격하고, 밀리는 나머지는 여전히 superseded.
4. **[관측성, 경미 → 테스트로 승격]** 모든 입력 item_id가 included/excluded/superseded(loser)/unresolved_conflicts 중 정확히 한 곳에만 나타난다는 파티션 불변식에 전용 회귀 테스트를 추가했다(`tests/test_context_selector_review5.py::test_every_input_item_id_lands_in_exactly_one_manifest_partition`).
5. **[죽은 코드, 경미]** `_redact_if_needed`가 redacted item에 `estimated_tokens=1`을 주지만, budget 루프의 `content_floor = max(1, (len(content)+3)//4)`가 `REDACTED_CONTENT_PLACEHOLDER`(10자)엔 항상 3을 내서 1은 한 번도 쓰이지 않았다 — redaction이 "값싸다"는 의도가 실제로 반영된 적이 없었다. content가 정확히 `REDACTED_CONTENT_PLACEHOLDER`인 item만 length-floor를 건너뛰고 `estimated_tokens`를 그대로 쓰도록 예외 처리(일반 content는 여전히 floor로 보호됨).

1·2번 전부 `tests/test_context_selector_review5.py`에 전용 테스트가 있다 — required-unresolved hard-fail 자체와 그 회귀 가드(부분 충족/정상 supersede는 여전히 통과)는 `tests/test_context_selector_review4.py`에 반영(기존 `test_required_source_fully_consumed_by_an_unresolved_tie_does_not_false_positive_missing`을 `test_required_source_fully_consumed_by_an_unresolved_tie_raises_not_silently_missing`으로 갱신 + 2건 회귀 가드 추가).

**2026-07-16 — CX1 producer→ContextItem 어댑터 (`src/agent_lab/context/adapters.py`, 신규).** 지금까지 `select_context()`는 synthetic `ContextItem`으로만 검증됐다 — CX1이 식별한 실제 producer를 실제 `ContextItem`으로 잇는 코드가 없어서, selector/manifest 전부가 사실상 죽은 코드였다(어떤 실제 agent turn도 이 경로를 타지 않았다). 이 어댑터가 그 gap을 메운다. CX1 source registry(§1)의 실제 표는 **15개 row**다 — 문서 본문이 "17개 producer"라고 적은 건 표 자체의 오기이며, 이 어댑터가 2개를 추가로 발명해서 채운 게 아니다. `agent_opinion`은 여전히 producer가 없다(§3, 미해결 — 가장 근접한 후보인 peer chat message는 구조화된 "의견" 객체가 아니라 원문 메시지라 어댑팅 대상으로 확정하지 않았다).

설계 결정 3가지:
- **어댑터는 producer의 입력이 아니라 이미 계산된 출력을 받는다** — 파일시스템/`run_meta`를 직접 읽지 않는다. 순수 함수로 유지되어 synthetic 데이터로 테스트 가능하고, `steer.py::drain_steer_follow_up` 같은 side-effecting/캐싱 producer의 로직을 중복 구현할 필요가 없다. 실제 producer 호출은 caller 몫.
- **producer 1개당 어댑터 1개** — SourceClass 1개당 1개가 아니다. AGENTS.md flat/hierarchy 중복 여부, wisdom의 4계층(notepad/index/store/playbook) 구분 등 CX1 §2가 열어둔 질문은 이 모듈이 대신 결정하지 않는다(CX2/CX8 selection-composition 몫).
- **PROJECT.md의 bootstrap(`project_memory.py`)과 injection(`session/guidance.py`) 두 registry row는 `adapt_project_md` 하나로 합쳤다** — §2 판정대로 같은 파일의 producer/consumer 관계일 뿐 별개 소스가 아니다. `_format_grounding_block`은 독립 producer가 아니라(clarify facts + goal ledger의 조건부 재조합) 어댑터를 만들지 않았다 — 별도로 만들면 anti-drift가 꺼진 일반 turn에서 같은 사실이 두 item_id로 중복 집계된다.

14개 어댑터 함수(15개 registry row 커버 — grounding_block 제외, PROJECT.md 두 row 통합)에 `tests/test_context_adapters.py`(16개, 각 어댑터의 정상/빈-입력 케이스 + `select_context()` 실제 통합 테스트)가 있다. authority는 registry의 정성 등급(최상/높음/중상/중)을 0-100 정수로 매핑한 first-draft 값 — CX1-CX4와 같은 상태(Human review 대기), 실제 선택 결과로 검증된 적 없다.

**2026-07-16 — §7.2 trim 3~6단계 (`src/agent_lab/context/compress.py`, 신규).** `select_context()`는 이미 1단계(정확히 같은 content 제거)·2단계(낮은 authority/relevance 제외)·7단계(그래도 초과하면 `ContextSelectionError`로 명시적 실패 — required item이 조용히 빠지는 일은 없다)를 구현했다. 3~6단계(tool output 압축, 대화 요약, symbol-targeted snippet, required item 구조화 요약)는 실제 콘텐츠 압축이 필요해 별도 모듈로 뺐다 — `select_context()`를 순수 selector로 유지하려는 이유와 같다.

설계는 `context/adapters.py`와 같은 원칙을 따른다 — 압축 함수는 **이미 만들어진 대체 데이터**(렌더링된 요약, symbol-graph가 이미 찾아낸 snippet, artifact ref 문자열)를 받을 뿐, 추출/요약 자체를 하지 않는다. 실제 transcript/required-item 요약은 LLM 호출이나 도메인 휴리스틱이 필요한데, 둘 다 mock-only 테스트 정책(`CLAUDE.md`: "테스트: mock-only, 실 LLM CI 금지")과 맞지 않는 이 모듈의 범위가 아니다.

- `StructuredSummary` — §7.3의 "요약은 source refs, decisions, unresolved questions, numeric constraints, must-not를 보존해야 한다"를 데이터로 못박은 dataclass(`.render()`로 렌더링).
- `compress_tool_output_to_artifact_ref` (3단계) — 순수 기계적 head+tail excerpt + artifact ref. 원문의 부분 문자열이라 왜곡 위험이 없다.
- `compress_to_structured_summary` (4단계·6단계 공용) — `StructuredSummary`를 렌더링해 item content를 대체. 4단계(오래된 대화)와 6단계(required item)는 코드가 동일하고 "어떤 item에 어떤 우선순위로 적용하는지"만 다르므로 함수를 나누지 않았다.
- `compress_repo_tree_to_symbol_snippets` (5단계) — repo tree 1개 item을 symbol별 여러 item으로 분해(각자 독립적으로 authority/relevance 랭킹 대상이 되도록 `conflict_key`는 상속하지 않음).
- `trim_to_budget(need, items, compressions=...)` — `select_context()`를 감싸는 오케스트레이터. `compressions`는 `item_id -> (step, compress_fn)` 매핑이며 호출자가 직접 등록한다(이 모듈은 "어떤 item이 tool output인지" 판단하지 않음). **6단계는 첫 selection 시도 전에 무조건 적용** — required item이 크다는 걸 호출자가 이미 알고 등록했으므로, `ContextSelectionError`를 먼저 잡았다가 재도출할 필요가 없다. **3~5단계는 점진적** — 한 번 select한 뒤 `excluded`에 `budget_overflow`로 빠진 item 중 해당 단계에 등록된 것만 압축하고 재selection, 이를 3→4→5 순서로 반복한다. 압축 후에도 여전히 안 맞으면 마지막 `select_context()` 호출의 `ContextSelectionError`가 그대로 전파된다 — 이게 7단계이고, 이미 구현된 걸 그대로 재사용할 뿐 새 코드가 필요 없다.

§7.2 마지막 문장("system constraint와 현재 Human intent를 조용히 trim하지 않는다")은 구조적으로 지켜진다 — 모든 압축 함수는 item을 삭제가 아니라 더 작은 item으로 **대체**하고 provenance에 압축 사실을 남긴다. 완전한 무흔적 제거는 `select_context()`의 `excluded`/`unresolved_conflicts`뿐이고 둘 다 이미 사유를 기록한다.

`tests/test_context_compress.py`(11개)로 검증 — 4개 압축 함수 각각의 정상/no-op 케이스, `trim_to_budget`의 6단계-무조건-적용, 3단계-점진적-재시도, 압축으로도 부족하면 여전히 raise, forbidden/not-allowed 등 budget과 무관한 배제는 압축 대상이 아님(compressor가 호출조차 안 됨)을 확인.

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
- budget overflow가 정의된 trim 순서를 따른다. — 1·2·7단계는 `select_context()` 자체, 3~6단계는 `context/compress.py::trim_to_budget()`으로 완료(2026-07-16, 위 절 참고). 압축 함수 자체(어떤 item을 어떻게 요약할지 판단)는 여전히 caller/CX8 몫.

**검증:** conflict/boundary/property/token tests.

### CX5. Repo·artifact targeted retrieval

**산출물:** commit-bound symbol/file/artifact retrieval.

**Acceptance criteria:**

- 전체 tree보다 activity 관련 symbol을 우선한다. — `compress_repo_tree_to_symbol_snippets()`가 이미 resolve된 symbol snippet을 받아 개별 item으로 쪼개는 기계적 변환은 있다(2026-07-16); symbol 자체를 찾아내는 symbol-graph/repo-map 도구 연결은 미착수.
- dirty worktree와 base commit 차이를 구분한다. — 미착수.
- large tool output은 ref + excerpt로 전달된다. — `compress_tool_output_to_artifact_ref()`로 기계적 변환 완료(2026-07-16); 실제 artifact 저장소 연결은 미착수.

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

- agent invocation마다 context assembly path가 하나다. — **아직 아니다.** 2026-07-16, flag-gated shadow slice(`context/bundle_recipe.py`, 아래 절)를 첫 단추로 놨지만 `build_context_bundle`(live per-turn path)은 전혀 안 건드렸다 — 지금은 경로가 여전히 둘(레거시 문자열 조립 + 신설된, 아직 아무도 안 부르는 typed 경로)이다.
- compatibility block은 adapter edge에만 남는다. — 미착수(bundle.py의 ~25개 producer 중 14개만 어댑팅됨, 나머지는 bundle.py 내부 string-appender라 이번 슬라이스 범위 밖).
- 중복 trim/token policy가 제거된다. — 미착수. 레거시는 여전히 진단용 `budget_pct`만 있고 강제하는 예산이 없다(select_context()는 강제한다) — 이 차이를 cutover 전에 어떻게 다룰지 결정 필요.

**검증:** prompt/context snapshot diff, provider contract tests, full CI.

**2026-07-16 — CX8 첫 슬라이스: flag-gated shadow path (`src/agent_lab/context/bundle_recipe.py`, 신규, live path 미변경).** `build_context_bundle`(798줄 레거시 assembler) 전체를 한 번에 수렴하는 건 위험이 너무 크다고 판단해서(라이브 per-turn 경로, 정확한 리터럴 마커 문자열·char 예산·`artifact_only` 억제 계약을 assert하는 기존 스냅샷 테스트 다수) 범위를 좁혔다:

1. **producer 커버리지 조사 결과:** bundle.py는 실제로 ~25개의 서로 다른 producer를 호출하는데, `context/adapters.py`는 그 중 14개만 커버한다. 나머지(mailbox/team_task/objection/challenge_owner/gate_snapshot/dispatch_intent/plugin_allowlist/thread_resume/session_skills/capability_preamble, 그리고 recent/peer/bridge/turn_state 메시지 이력 필드)는 bundle.py 내부의 private string-appender 함수라 독립 호출이 불가능하다 — bundle.py 자체를 리팩터링해야 하는데, 이번 슬라이스는 live path를 건드리지 않는 게 원칙이라 범위 밖으로 뺐다.
2. **`adapt_approved_plan` 추가(`context/adapters.py`)** — `plan_md`는 CX1 registry의 15개 row에 없었지만(레지스트리는 bundle.py "내부" producer만 카탈로그했음), 모든 `build_context_bundle` 호출부가 이미 파라미터로 받는 값이고 `SourceClass.APPROVED_PLAN`의 유일한 소스다. CLARIFY를 제외한 모든 activity recipe가 APPROVED_PLAN을 요구하는데 CX1이 이 gap을 놓쳤었다.
3. **`activity_kind_for_mission_phase(phase)`** — `mission_loop.phase`(`CLARIFY/DISCUSS/PLAN_GATE/PLAN_REJECT/EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR/...`)를 `ActivityKind`로 매핑. DISCUSS/PLAN_GATE/PLAN_REJECT는 전부 PLAN으로 매핑되는데, 이건 `layers.py::should_use_mission_slim_bundle`이 이미 같은 phase 집합으로 "PLAN 단계는 더 가벼운 context" 게이트를 걸고 있는 것과 동일한 그룹핑이다. MERGE_REVIEW/VERIFY → CRITIC은 판단 콜(재검토 대상). MISSION_DEFINE/MISSION_PAUSED/MISSION_DONE은 매핑 없음(활동이 아님). **SCRIBE는 대응하는 phase가 아예 없다** — scribe context는 `core/limits.py`의 `ScribeContextLimits`라는 완전히 별개의, 아직 수렴 안 된 경로로 만들어진다.
4. **`build_manifest_via_recipe(activity, RecipeBundleInputs)`** — 이미 계산된 producer 출력(adapters.py와 같은 철학: 이 함수는 producer를 직접 호출하지 않는다)을 받아 어댑팅하고 `activity_recipes.py`의 recipe로 `select_context()`를 돌린다.
5. **EVIDENCE gap — 닫힘 (2026-07-16).** `adapt_artifacts`(`context/adapters.py`, `room/artifacts.py::recent_artifacts_for_agent`/`list_artifacts`의 `{id, producer, kind, summary, ts, path?}` row를 `SourceClass.EVIDENCE`로 매핑 — CX1 registry는 이 producer를 카탈로그하지 않았다, `room/` 아래 있어서 `context/` 스캔 범위 밖이었다)를 추가해서, CRITIC/REPAIR/SCRIBE(전부 EVIDENCE 필수) recipe가 이제 `inputs.artifacts`가 있으면 manifest를 만들 수 있다 — 전에는 항상 실패했다. `artifacts` 없이 호출하면 여전히 이전과 동일하게 "missing required sources"로 실패하는 것도 회귀 테스트로 고정. `recent_artifacts_for_agent`가 `path`로 가리키는 실제 artifact 본문(디스크에서 별도로 읽는 부분)은 어댑팅 대상이 아니다 — `summary` 필드만 사용, adapters.py의 "파일시스템 안 건드림" 원칙 유지.
6. **`AGENT_LAB_CONTEXT_RECIPE` flag 등록**(`runtime_flags.py`, `run/profile.py` — thorough 소속) — 기본 off, 그리고 **지금 이 flag를 읽는 코드가 없다.** `build_context_bundle`은 이 슬라이스로 전혀 안 건드렸다 — flag는 향후 dogfood/eval harness가 옵트인할 수 있도록 F2 컨벤션에 맞춰 미리 등록만 해둔 것이다. 실제 splice-in(레거시 경로와 병행 실행 → parity 확인 → cutover)은 별도 승인 대상.

`tests/test_context_bundle_recipe.py`(26개)로 검증 — phase 매핑(문서화된 gap 포함), 6개 activity 전부의 성공 케이스(CRITIC/REPAIR/SCRIBE는 `artifacts` 입력이 있을 때), `artifacts` 없이 호출하면 여전히 실패하는 회귀 가드, SEMANTIC_MEMORY(wisdom/playbook)가 PLAN에선 not_allowed로 배제되지만 REPAIR에선 실제로 included된다는 것까지 확인. `context/adapters.py`도 `adapt_artifacts` 전용 테스트 2개 추가(`tests/test_context_adapters.py`).

**2026-07-16 — 나머지 14개 producer 어댑팅 + 앞선 판단 정정.** 직전 절이 "mailbox/team_task/objection/challenge_owner/dispatch_intent/plugin_allowlist/thread_resume/session_skills/capability_preamble/turn_state/plan_open/turn_bridge/peer/envelope_follow_up/agent_tool_rules는 bundle.py 내부의 private string-appender라 독립 호출 불가능"이라고 적었는데, 이 판단은 틀렸다 — 전부 `room/tasks.py`/`room/mailbox.py`/`room/objections.py`/`plugin_discovery.py`/`room/agent_capabilities.py`/`agent/thread_resume.py`/`skill_drafts.py`/`room/dispatch_intents.py`/`room/context/plan_excerpt.py`/`room/turn_state.py`/`room/context/peer_digest.py`/`reply_policy.py`/`room/context/constraints.py` 각자의 독립 함수였다 — `build_artifacts_block`과 정확히 같은 모양(bundle.py는 그냥 호출해서 문자열로 이어붙일 뿐). 이미 만들어져 있는 결과 문자열을 받는 어댑터라 전부 같은 패턴(`_adapt_single_block` 헬퍼 하나로 공유) — 예외 하나는 `build_mailbox_block`: `mark_delivered`라는 side effect(렌더링하면 읽음 처리됨)가 있어서, 그 대신 읽기 전용인 `unread_for_agent()`의 결과를 받는 `adapt_mailbox_messages`를 만들었다(steer_queue 어댑터가 `drain_steer_follow_up` 대신 `list_steer_queue`를 받는 것과 같은 이유).

SourceClass 매핑: team_task/objection/challenge_owner/thread_resume/dispatch_intent/plan_open/turn_state → RUNTIME_STATE(현재 턴/세션 상태), plugin_allowlist/capability_preamble/envelope_follow_up/agent_tool_rules → SYSTEM_INVARIANT(tool 권한 경계·절차 규칙), session_skills → EPISODE(자기 헤더가 "learned this mission"이라고 명시), **mailbox/turn_bridge/peer → AGENT_OPINION** — 이 셋이 CX1 §3가 "producer 없음"으로 남겨뒀던 `agent_opinion` gap을 실제로 닫는다(동료 agent의 mailbox 메시지·R1 요약·이번 턴 발화는 전부 그 agent 자신의 communication이지 시스템이 만든 사실이 아니다).

`RecipeBundleInputs`에 14개 필드 추가, `build_manifest_via_recipe`가 전부 어댑팅해서 넘기도록 배선. PLAN_RECIPE의 optional_sources가 `{EPISODE, EXTERNAL_CONTENT, AGENT_OPINION}`이라 mailbox/turn_bridge/peer가 실제로 included되는 걸 PLAN activity로 시연(전에는 AGENT_OPINION을 optional로 허용하는 activity가 하나도 시연 대상이 아니었다). EXECUTE_RECIPE가 EPISODE를 forbidden하므로 session_skills_block이 EXECUTE에서 실제로 배제되는 것도 확인.

`bundle.py` 자체는 이번에도 전혀 안 건드림(`git diff` 확인). `tests/test_context_adapters.py`에 30개, `tests/test_context_bundle_recipe.py`에 2개 신규 테스트.

**2026-07-16 — `recent` transcript gap도 닫힘.** 직전 절에서 "진짜 taxonomy 공백"이라고 남겨뒀던 `build_recent_turns_block`/`_build_human_only_recent_block`(전체 대화 transcript)도, 앞의 14개와 같은 이유로 다시 봤다 — 이것도 하나의 뭉친 문자열이 아니라 `ChatMessage.to_dict()` 모양(`{role, agent, content, ts, parallel_round?}`)의 구조화된 리스트다. 메시지 하나하나를 **`role`별로 분해**하면(`context/adapters.py::adapt_recent_messages`, `tests/test_context_adapters.py`에 6개 신규 테스트):
- `role == "user"`(Human 발화) → **HUMAN_INTENT** — §12 "현재 Human intent"의 1차 소스와 정확히 일치.
- `role == "agent"` & `agent == self_agent`(이 agent가 이 세션에서 이미 한 답변) → **EPISODE** — peer의 의견과 구분되는 자기 세션 이력.
- `role == "agent"` & `agent != self_agent`(recent에 peer 발화가 안 걸러지고 섞여 들어온 경우) → **AGENT_OPINION** — mailbox/peer_block/turn_bridge와 동일 슬롯.
- `role == "system"`(ephemeral 시스템 알림) → **RUNTIME_STATE**.

item_id는 `goal_ledger`와 같은 index 기반(`f"recent:{index}"`) — chat.jsonl row엔 `ts`는 있지만 안정적인 id가 없고, 동시 응답 시 `ts`가 겹칠 수 있어서 index만이 유일성을 보장한다(리스트 편집에는 불안정, 같은 caveat). `RecipeBundleInputs`에 `recent_messages`/`self_agent` 필드 추가, PLAN activity로 Human/자기 자신/peer 셋 다 실제 included되는 걸 시연(`tests/test_context_bundle_recipe.py` 1개 신규).

이걸로 CX1 §3가 열어뒀던 taxonomy 질문(agent_opinion 소스 유무)과 09 문서가 반복해서 "매핑 불가"로 남겨뒀던 recent transcript 둘 다 닫혔다 — bundle.py의 실제 producer 25개 전부에 대해 이제 어댑터가 있다(단 `_format_grounding_block`은 여전히 독립 producer가 아니라서 어댑팅 대상 자체가 아님, clarify_facts+goal_ledger로 구성).

**2026-07-16 — `AGENT_LAB_CONTEXT_RECIPE` flag splice-in + parity 확인 (`src/agent_lab/context/bundle_shadow.py`, 신규).** 이전 절에서 "flag는 등록만 해두고 읽는 코드는 없다"고 남겨뒀던 걸 실제로 연결했다 — `build_context_bundle`/`build_slim_consensus_bundle` 둘 다 자기 함수 맨 끝(`return bundle` 직전)에 딱 한 블록씩 추가해서, flag가 켜져 있으면 `select_context()` 기반 병행 manifest를 계산하고 비교 결과를 `run_meta["context_recipe_shadow"]`에 기록한다. **레거시 경로가 실제로 반환하는 `bundle`은 절대 건드리지 않는다** — 이게 이 작업 전체의 안전 불변식이다.

핵심 설계 결정:
- **함수 끝에서 한 번만 호출, 함수 본문 중간엔 손대지 않음(거의).** `build_context_bundle`이 이미 계산해둔 지역 변수(session_guidance/session_skills/thread_resume/plugin_allowlist/capability_preamble/team_task/objection/challenge_owner/plan_open/turn_state/turn_bridge/peer/envelope_follow_up/agent_tool_rules/recent 메시지 리스트, 총 14개)를 그대로 재사용한다 — 두 번째로 다시 호출해서 근사치를 만드는 것보다 싸고 정확하다. 단 5개(repo tree, mission notepad, AGENTS.md hierarchy, clarify facts, goal ledger)는 bundle.py의 private helper(`_append_mission_track_c_blocks` 등)가 `constraints` 문자열에 바로 병합해버려서 별도 지역 변수로 안 남아 있다 — 이 5개만 읽기 전용 producer를 다시 호출한다(bundle_recipe.py 첫 슬라이스가 이미 caller에게 요구했던 것과 동일).
- **`build_slim_consensus_bundle`에도 별도로 splice해야 했다** — `should_use_mission_slim_bundle`이 DISCUSS/PLAN_GATE/PLAN_REJECT phase를 `build_context_bundle` 진입 즉시 slim path로 리다이렉트하는데, 이 phase 집합이 정확히 PLAN activity로 매핑되는 phase들이다. `build_context_bundle`의 끝에만 splice했다면, 가장 흔한 activity(PLAN)가 shadow pass를 단 한 번도 실제로 타지 않는다는 걸 통합 테스트로 직접 발견하고 나서 두 번째 splice를 추가했다(`tests/test_context_bundle_shadow_splice.py::test_flag_on_stamps_a_shadow_result_into_run_meta`가 처음엔 이 이유로 실패했었다). slim path는 `bridge_block`/`peer_block`이 원래 `""`이고 `session_skills`를 아예 호출 안 하며, trim된 개별 메시지 리스트 대신 사람 전용 요약(`recent_block`)만 만들기 때문에 `recent_msgs` 대신 원본 `messages`(비trim·비dedup)를 넘긴다 — 문서화된 저-fidelity 근사치.
- **mailbox와 wisdom_index/playbook은 이번 parity pass에서 제외.** mailbox는 splice 시점이 `build_mailbox_block`(mark_delivered side effect 있음) 호출 **이후**라서, 그 시점에 `unread_for_agent`를 다시 불러도 이미 읽음 처리된 빈 리스트만 나온다 — 이 함수 끝에서 splice하는 접근법 자체의 한계, 숨기지 않고 문서화. wisdom_index/playbook은 R1·topic 게이팅이 있는 optional-only producer라 첫 parity pass에서는 재호출 대상에서 뺐다. 둘 다 "shadow manifest가 실제보다 적게 포함한다"는 방향의 gap이지 잘못된 계산이 아니다.
- **전부 try/except로 감쌈** — activity 매핑 실패, `ContextSelectionError`, 예상 밖 producer 모양 등 무엇이 나든 `{"ok": False, ...}` 기록으로 남고 절대 raise하지 않는다. flag가 꺼져 있으면(기본값) `env_bool` 체크 하나가 전부 — `bundle.py`의 실제 diff는 **87줄 순수 추가, 기존 라인 변경/삭제 0**.

검증한 것: (1) flag off일 때 기존 `tests/test_context_bundle.py`/`test_efficiency_mode.py`/`test_context_layers.py` 21개 전부 무변경 통과, (2) flag on/off 상태에서 `bundle.render()`가 **byte-identical**함을 두 경로(full path, slim path) 각각 직접 assert, (3) flag on인데 activity 매핑이 없거나 shadow 함수 자체가 raise해도 `build_context_bundle`은 정상적으로 bundle을 반환함, (4) flag on이고 phase가 매핑되면 `run_meta["context_recipe_shadow"]`에 `{ok, activity, included_count, excluded_count, unresolved_count, recipe_total_tokens, legacy_total_chars, included_sources}` 기록됨. `tests/test_context_bundle_shadow.py`(6개, `shadow_compare_bundle` 단위) + `tests/test_context_bundle_shadow_splice.py`(7개, 실제 splice 지점 통합 테스트).

**아직 안 한 것 — 진짜 cutover.** 이 pass는 병행 계산 + 기록만 한다. 레거시 문자열 대신 recipe manifest를 실제로 사용하도록 바꾸는 건 여기서 안 했다 — dogfood/eval harness가 `context_recipe_shadow` 기록을 충분히 모아서 파악한 뒤, 별도 승인을 거쳐야 할 다음 단계.

**2026-07-16 — dogfood 스크립트로 실제 기록 수거(`scripts/context_recipe_shadow_dogfood.py`, `make context-recipe-shadow-dogfood`).** Room/mock-agent 루프 없이 `build_context_bundle`/`build_slim_consensus_bundle`을 직접 호출 — 둘 다 `messages`+`run_meta`만 있으면 되고 실제 모델 호출이 필요 없어서 mission phase 11개(6개 activity 매핑 + 2개 문서화된 무매핑 + PLAN/EXECUTE/CRITIC의 중복 phase) 전부를 빠르게 순회할 수 있다. 결과: **6개 activity 매핑 전부 성공**(처음엔 CRITIC/REPAIR가 EVIDENCE 누락으로 실패했는데, recipe 버그가 아니라 synthetic run_meta에 artifact가 없었던 fixture 문제였다 — `run_meta["artifacts"]`에 1개 넣으니 즉시 해결), 2개 무매핑 phase는 설계대로 깨끗하게 skip. DISCUSS/PLAN_GATE/PLAN_REJECT 셋 다 실제로 slim path(두 번째 splice 지점)를 탔음을 `slim_context: true`로 확인. 상세 결과와 알려진 한계(mailbox 미포함, 단위 다른 char/token 비교 등)는 [evidence/cx8-context-recipe-shadow-dogfood-2026-07-16.md](./evidence/cx8-context-recipe-shadow-dogfood-2026-07-16.md) 참고. 이 실행도 cutover 판정을 내리지 않는다 — synthetic run_meta 1세트뿐이라 표본을 늘리는 게 다음 단계.

**2026-07-16 — 표본 확대(36 시나리오, 5개 variant) + PROJECT_DOC 구멍 발견·수정.** 스크립트를 확장해 activity당 5개 variant(long_conversation/minimal/many_artifacts/different_agent/room_state_populated)로 재실행했다. **표본을 늘리는 과정에서 진짜 버그를 하나 찾았다** — `bundle_recipe.py::RecipeBundleInputs`가 CX8 첫 슬라이스부터 `agents_md_hierarchy` 하나로만 PROJECT_DOC을 연결해뒀고, `project_md`/`agents_md_flat`/`shared_context_md`(전부 이미 `context/adapters.py`에 있는 어댑터)는 한 번도 배선된 적이 없었다. `agents_md_hierarchy`는 plan_md 안의 파일 경로 힌트가 있어야 뭔가를 내는데, `minimal` variant(plan_md="")로 이 조건이 깨지자 실제 workspace를 쓰는데도 PROJECT_DOC이 통째로 안 잡히는 게 드러났다 — CLARIFY/PLAN recipe가 항상 PROJECT_DOC을 요구하는 만큼, plan.md에 파일 힌트가 없는 실제 세션에서도 재현 가능한 진짜 gap이었다. `bundle_recipe.py`에 3개 필드 추가(+3개 어댑터 배선), `bundle_shadow.py`의 재호출 producer를 5개→8개로 확장해서 수정했고, 재실행 후 해당 실패가 사라졌다(`tests/test_context_bundle_recipe.py` 2개 신규 테스트로 고정). 나머지 3개 실패(`*:minimal` variant의 execute/critic/repair)는 plan_md가 비어 있어 `approved_plan`(및 critic/repair는 `evidence`)이 의도적으로 없는 negative case — 버그 아님. 상세는 evidence 문서의 "2차 실행" 절 참고.

**2026-07-16 — mailbox를 shadow pass에 포함.** 남아있던 마지막 producer 제외 항목을 닫았다. `context/bundle.py`의 두 함수 각각에서 `build_mailbox_block(run_meta, agent)` 호출 **바로 직전**에 `unread_for_agent(run_meta, agent)` 결과를 캡처하는 한 줄을 추가(읽기 전용, `build_mailbox_block` 자체 동작·부수효과는 안 바꿈) — `build_mailbox_block`이 렌더링과 동시에 `mark_delivered`로 메시지를 읽음 처리하는 부수효과가 있어서, splice 지점(함수 끝)에서 다시 읽으면 항상 빈 리스트만 나왔던 게 지금까지의 한계였다. 캡처한 값을 `shadow_compare_bundle`의 새 `mailbox_rows` 파라미터로 전달. 실제 `build_mailbox_block`(스텁 아님)을 상대로 한 end-to-end 통합 테스트로, mailbox 메시지가 `SourceClass.AGENT_OPINION`으로 select_context()를 통과하는 것과 동시에 레거시 경로의 `mark_delivered` 부수효과도 그대로 유지되는 것 둘 다 확인(`tests/test_context_bundle_shadow_splice.py`). 상세는 evidence 문서의 "3차" 절 참고. 남은 한계는 wisdom_index/playbook 미포함과 char/token 단위 불일치 둘뿐이다.

**2026-07-16 — wisdom_index/playbook도 shadow pass에 포함.** 마지막 producer 제외 항목까지 닫았다. 실제 `build_context_bundle`에서 이 둘은 `_append_wisdom_search_block`/`_append_playbook_block`(둘 다 private, `constraints` 누적 문자열을 받아 반환하는 string-appender)을 통해서만 호출되고, 게이트는 R1 한정(`parallel_round==1`) — wisdom은 추가로 `AGENT_LAB_WISDOM_IN_CONTEXT` 환경변수 또는 deep/critical turn category, 실제 `_session_folder` 디렉터리 존재, `wisdom_index_enabled`까지 필요하다. `bundle_shadow.py`에 `_wisdom_route_allows`(bundle.py의 private 헬퍼를 import하지 않고 로직만 복제 — 이 모듈이 bundle.py 내부 구현에 결합되는 걸 원치 않아서)를 추가하고, 같은 게이트를 통과했을 때만 `search_wisdom_index`/`playbook_bullets_for_topic`을 직접 재호출해서 `RecipeBundleInputs.wisdom_index_hits`/`playbook_bullets`를 채운다. `bundle.py` 자체는 이번엔 전혀 안 건드렸다 — slim path(`build_slim_consensus_bundle`)는 이 둘을 원래 절대 안 부르는데, 그 shadow 호출부가 이미 `parallel_round=2`를 넘기고 있어서 R1 게이트가 자동으로 slim 쪽을 걸러준다(우연이 아니라 실제 R1-only 규칙을 그대로 반영한 결과). REPAIR activity(SEMANTIC_MEMORY를 optional로 허용)로 실제 포함을 시연하고, `parallel_round != 1`이면 두 producer가 호출조차 안 된다는 것도 회귀 테스트로 고정(`tests/test_context_bundle_shadow.py` 2개 신규). **이제 shadow pass에서 의도적으로 제외된 producer가 하나도 없다** — 남은 건 char/token 단위 정규화뿐.

**2026-07-16 — char/token 단위 정규화.** 4차례 dogfood evidence run 전부가 "legacy_total_chars(문자 수)와 recipe_total_tokens(추정 토큰 수)는 단위가 달라 직접 비교 불가"를 미해결 항목으로 남겼는데, 이번에 닫았다. `shadow_compare_bundle`이 이제 `legacy_estimated_tokens`(레거시 렌더 결과에 `select_context()` 자신이 모든 item에 쓰는 것과 동일한 `recipe.py::estimate_tokens`(~4 chars/token) 공식을 적용)와 `recipe_to_legacy_token_ratio`(`recipe_total_tokens / legacy_estimated_tokens`)를 함께 반환한다 — 1보다 작으면 recipe가 레거시보다 더 타이트하게 골랐다는 뜻, 크면 더 크게 골랐다는 뜻. `legacy_total_chars`는 투명성을 위해 그대로 남겨뒀다(제거 안 함). dogfood 재실행 결과가 evidence 문서 "5차" 절에 있다 — activity별로 뚜렷한 패턴이 보인다(CLARIFY/PLAN은 레거시보다 ~1.3배 크게, EXECUTE/CRITIC은 레거시의 ~1/3 크기로, REPAIR는 거의 동등하게 고른다). 표본이 여전히 36개 synthetic 시나리오뿐이라 강한 결론은 아니다.

- 모든 agent activity가 목적에 맞는 versioned Context Recipe를 사용한다.
- 포함 정보의 source·freshness·authority·선택 이유를 설명할 수 있다.
- 오래된 plan과 검증되지 않은 memory가 현재 Human intent를 덮어쓰지 않는다.
- token 절감이 중요한 constraint/evidence 유실로 이어지지 않는다.
- 외부 content와 tool output이 제어권이나 권한을 획득하지 못한다.
