# CX8 — context_recipe_shadow dogfood run (2026-07-16)

> [09-context-engineering.md](../09-context-engineering.md) §11 CX8의 flag-gated shadow splice
> (`src/agent_lab/context/bundle_shadow.py`)가 실제로 `run_meta["context_recipe_shadow"]`에
> 기록을 남기는지, 어떤 activity가 성공/실패/스킵하는지 실측한다. **cutover 판정을 내리지
> 않는다** — 다음 승인 단계를 위한 원본 데이터만 남긴다.

## 실행 방법

```
make context-recipe-shadow-dogfood
```

(`scripts/context_recipe_shadow_dogfood.py` — `AGENT_LAB_MOCK_AGENTS=1`, 내부에서
`AGENT_LAB_CONTEXT_RECIPE=1` 설정. 실제 repo root를 workspace로 사용해 repo tree/AGENTS.md
producer가 진짜 파일을 본다.)

`build_context_bundle`/`build_slim_consensus_bundle`을 Room/mock-agent 루프 없이 직접
호출한다 — 두 함수 다 `messages`+`run_meta`만 있으면 되고 실제 모델 호출이 필요 없어서다.
`mission_loop.phase`로 매핑되는 11개 phase(6개 activity + 2개 무매핑 phase, 나머지는 동일
activity의 중복 phase) 각각에 대해 한 번씩 호출하고 `context_recipe_shadow` 필드를 수거했다.

## 결과 (2026-07-16 실행)

```
scenario_count: 11
ok_count: 9
skipped_count: 2
failed_count: 0
```

| scenario | phase | activity | 결과 |
| --- | --- | --- | --- |
| clarify | CLARIFY | clarify | ok |
| discuss | DISCUSS | plan | ok (slim path) |
| plan_gate | PLAN_GATE | plan | ok (slim path) |
| plan_reject | PLAN_REJECT | plan | ok (slim path) |
| execute_queue | EXECUTE_QUEUE | execute | ok |
| dry_run | DRY_RUN | execute | ok |
| merge_review | MERGE_REVIEW | critic | ok |
| verify | VERIFY | critic | ok |
| repair | REPAIR | repair | ok |
| mission_define | MISSION_DEFINE | — | skipped (문서화된 무매핑) |
| mission_done | MISSION_DONE | — | skipped (문서화된 무매핑) |

**6개 activity 매핑(CLARIFY/PLAN/EXECUTE/CRITIC/REPAIR) 전부 첫 실행에서 성공했다.** 처음
artifacts 없이 돌렸을 때는 CRITIC/REPAIR가 "missing required sources: evidence"로 실패했는데
(SCRIBE도 마찬가지였을 것 — 매핑되는 phase가 없어서 이 실행에선 시연 안 됨), 이건 recipe
파이프라인 문제가 아니라 스크립트의 synthetic run_meta에 artifact가 없었던 fixture 문제였다
— `run_meta["artifacts"]`에 하나 넣어주니 즉시 해결됐다. **CRITIC/REPAIR/SCRIBE recipe가
`SourceClass.EVIDENCE`를 requires하는 한, 이 세 activity는 실제 운영에서도 Room이 최소 1개
artifact를 기록한 뒤에만 정상 동작한다** — CX8 실제 cutover 전에 반드시 확인해야 할 전제
조건으로 남긴다.

DISCUSS/PLAN_GATE/PLAN_REJECT 셋 다 `build_slim_consensus_bundle`로 리다이렉트됐고
(`slim_context: true`), 두 번째 splice 지점이 실제로 동작함을 확인했다 — `build_context_bundle`
한 곳에만 splice했다면 이 셋(사실상 가장 흔한 PLAN activity 전부)이 단 한 번도 shadow pass를
안 탔을 것이다.

## Included source 빈도 (9개 성공 사례 합산)

```
system_invariant: 9   (전 activity가 요구)
runtime_state: 7
human_intent: 5
approved_plan: 5
repo_context: 5
project_doc: 4
agent_opinion: 3       (mailbox 없이, peer/turn_bridge 메시지에서만)
episode: 3
evidence: 3            (CRITIC/REPAIR가 artifact를 요구하는 만큼만)
```

## 알려진 한계 (숨기지 않고 기록)

- **mailbox 미포함** — splice 시점이 `build_mailbox_block`의 `mark_delivered` side effect
  **이후**라서, 이 dogfood 실행에서도 mailbox 메시지가 있었다면 shadow manifest엔 안 잡혔을
  것이다(이번 run_meta엔 mailbox 자체를 안 넣었으니 직접 관측되진 않았지만, 설계상 확정된
  gap).
- **wisdom_index/playbook 미포함** — optional-only, R1-gated라 이번 pass 재호출 대상에서
  제외(`bundle_shadow.py` 자체 문서화).
- **legacy_total_chars vs recipe_total_tokens는 단위가 다르다** — 문자 수 대 추정 토큰 수라
  직접 비율 비교는 의미 없다. "recipe가 legacy보다 얼마나 작은/큰 컨텍스트를 고르는가"를
  실제로 판단하려면 같은 단위(문자 or 토큰)로 정규화하는 후속 분석이 필요 — 이번 스크립트는
  원본 숫자만 나란히 남긴다.
- **synthetic run_meta 1세트만 사용** — 실제 세션의 다양한 phase 전이·메시지 길이·mailbox
  트래픽을 대표하지 않는다. cutover 판정 전에 실제(또는 더 다양한 synthetic) 세션 코호트로
  반복 실행하는 게 필요하다.

## 다음 단계 (승인 대상, 여기서 결정하지 않음)

1. 더 다양한 synthetic/실제 세션으로 반복 실행해 `context_recipe_shadow` 표본을 늘린다. →
   **2026-07-16 2차 실행에서 진행함, 아래 참고.**
2. `legacy_total_chars`/`recipe_total_tokens`를 같은 단위로 정규화해서 "recipe가 실제로 더
   타이트하게 고르는가"를 판단한다.
3. mailbox/wisdom_index/playbook을 포함하도록 splice 시점을 재검토한다(mailbox는 특히
   `build_mailbox_block` 호출 **이전** 시점에 별도로 shadow 자료를 뽑아야 한다).
4. 위 데이터가 충분히 쌓이면 실제 cutover(레거시 문자열 대신 recipe manifest 사용) 여부를
   결정한다 — 이 문서는 그 결정을 내리지 않는다.

---

## 2026-07-16 2차 실행 — 표본 확대 (36 시나리오, 5개 variant × 5개 activity + equivalence/무매핑 체크)

1차 실행은 activity당 synthetic 세트 1개뿐이었다. `scripts/context_recipe_shadow_dogfood.py`를
확장해 activity-대표 phase(CLARIFY/DISCUSS/EXECUTE_QUEUE/MERGE_REVIEW/REPAIR) 각각에 5개
variant를 돌리고, 나머지 동치 phase(PLAN_GATE/PLAN_REJECT/DRY_RUN/VERIFY)는 baseline
variant로만 재확인했다:

- **baseline** — 1차 실행과 동일한 3-메시지 대화, artifact 1개.
- **long_conversation** — round 1(3턴) + round 2(4턴), turn_bridge(R1 요약)·peer_block(라운드
  2 발화) 실제 관측 목적.
- **minimal** — plan_md="", 메시지 1개, artifact 0개. required source 누락 시 fail-closed가
  실제로 작동하는지 확인하는 의도된 negative case.
- **many_artifacts** — artifact 5개.
- **different_agent** — self_agent를 codex로 바꿔 EPISODE(자기 발화)/AGENT_OPINION(동료 발화)
  매핑이 실제로 뒤집히는지 확인.
- **room_state_populated** — `run_meta["tasks"]`/`["objections"]`/`["mailbox"]`를 채워서
  team_task/objection/challenge_owner/(mailbox는 여전히 구조상 미포함) producer가 실제
  내용을 낼 때도 관측.

### 실행 결과

```
scenario_count: 36
ok_count: 31 (1차 발견 이후 수정 반영, 아래 참고)
skipped_count: 2
failed_count: 3 (전부 의도된 negative case)
```

실패한 3건 전부 `*:minimal` variant다 — `plan_md=""`라 `approved_plan`이 없고(execute/critic/
repair 전부 요구), critic/repair는 추가로 `evidence`도 없다(이 variant는 artifact_count=0으로
의도적으로 설정). **의도된 fail-closed 확인이지 버그가 아니다.**

### 진짜 발견 — PROJECT_DOC 커버리지 구멍 (수정 완료)

`clarify:minimal`/`plan:minimal`가 처음엔 `"missing required sources: project_doc"`로
실패했다. 원인 추적: `bundle_recipe.py::RecipeBundleInputs`는 CX8 첫 슬라이스 때부터
**`agents_md_hierarchy` 하나만** PROJECT_DOC 소스로 연결돼 있었고, `project_md`/
`agents_md_flat`/`shared_context_md`(전부 `context/adapters.py`에 이미 존재하는 어댑터)는
단 한 번도 `RecipeBundleInputs`에 배선된 적이 없었다. `agents_md_hierarchy`는 plan_md 안의
파일 경로 힌트가 있어야 뭔가를 반환하는데(`read_agents_md_hierarchy_for_injection`), `minimal`
variant는 plan_md가 비어 있어 힌트가 없다 — 그래서 실제 workspace(repo root, 진짜
AGENTS.md/SHARED_CONTEXT.md가 있는)를 쓰는데도 PROJECT_DOC이 통째로 안 잡혔다.

**이건 CLARIFY/PLAN recipe가 항상 PROJECT_DOC을 요구하는데, "plan.md에 파일 힌트가 없으면
PROJECT_DOC이 전혀 안 채워질 수 있다"는 뜻이라 표본을 안 늘렸으면 못 봤을 실제 버그였다.**
수정: `bundle_recipe.py`에 `project_md`/`project_md_mtime`/`agents_md_flat`/
`agents_md_flat_mtime`/`shared_context_md` 필드 추가 + 3개 어댑터 배선, `bundle_shadow.py`가
`read_agents_md_for_injection`/`read_shared_context_for_injection`(둘 다 이미 public,
workspace_binding만 있으면 호출 가능)과 PROJECT.md 파일 직접 읽기(`project_memory.py::
project_md_path`)로 재호출하도록 확장(재호출 producer 5개 → 8개). 재실행 후
`clarify:minimal`/`plan:minimal` 둘 다 성공 — `failed_count`가 5→3으로 줄었다(남은 3개는
전부 의도된 negative case).

### Included source 빈도 (31개 성공 사례 합산, 36 시나리오 기준)

```
system_invariant: 31   (전 activity가 요구)
runtime_state: 25
approved_plan: 17
human_intent: 19
repo_context: 14
project_doc: 14         (1차 4 → 2차 14 — PROJECT_DOC 수정 반영)
evidence: 11
agent_opinion: 7
episode: 7
```

### Activity별 recipe_total_tokens (여러 variant 통계)

| activity | min | max | avg |
| --- | --- | --- | --- |
| clarify | 2600 | 2989 | 2825.7 |
| plan | 2821 | 3233 | 3083.1 |
| execute | 764 | 980 | 858.7 |
| critic | 647 | 775 | 727.0 |
| repair | 1935 | 2151 | 2040.8 |

variant 간 편차(예: clarify 2600~2989)가 activity 간 편차보다 훨씬 작다 — 지금 recipe들의
budget이 입력 크기 변화(대화 길이, artifact 개수)에 크게 흔들리지 않는다는 뜻이지만, 표본이
여전히 6개뿐이라 강한 결론은 아니다.

### 갱신된 알려진 한계

- wisdom_index/playbook 미포함은 여전히 유효.
- char-vs-token 단위 불일치도 여전히 유효 — 이번 실행에서도 정규화 안 함.
- **PROJECT_DOC 구멍은 이번 실행으로 닫혔다** — 위 "진짜 발견" 절 참고.

---

## 2026-07-16 3차 — mailbox를 shadow pass에 포함

`context/bundle.py`의 두 함수(`build_context_bundle`/`build_slim_consensus_bundle`) 각각에서
`build_mailbox_block(run_meta, agent)` 호출 **바로 직전**에 `unread_for_agent(run_meta, agent)`
결과를 캡처하는 한 줄을 추가했다(읽기 전용, `build_mailbox_block` 자체의 동작·부수효과는 전혀
안 바꿈). `build_mailbox_block`은 렌더링과 동시에 `mark_delivered`로 그 메시지들을 읽음
처리하는 부수효과가 있어서, splice 지점(함수 끝)에서 다시 읽으면 항상 빈 리스트만 나왔던 게
1차/2차 실행 모두의 한계였다 — 이번엔 그 부수효과가 일어나기 **전** 시점에서 값을 캡처해
shadow 쪽으로만 흘려보낸다.

재실행 결과: `plan:room_state_populated` 시나리오(`run_meta["mailbox"]`에 동료 메시지 1건
채움)에서 `included_sources`에 `agent_opinion`이 포함되고 `included_count`가 이전보다 1
늘었다 — mailbox 메시지가 실제로 `SourceClass.AGENT_OPINION`으로 select_context()를 통과했다.
동시에 실제 경로(레거시 `bundle.render()`)엔 `[받은함 — 동료에게서]` 블록이 그대로 남아있고
`run_meta["mailbox"][0]["read"]`도 여전히 `True`로 바뀐다 — mailbox 캡처가 실제 mark_delivered
동작을 전혀 방해하지 않는다는 것도 전용 통합 테스트(`tests/test_context_bundle_shadow_splice.py::
test_flag_on_captures_real_mailbox_rows_before_build_mailbox_block_mutates_them`)로 고정했다.

남은 한계는 wisdom_index/playbook 미포함과 char/token 단위 불일치 둘뿐이다.

---

## 2026-07-16 4차 — wisdom_index/playbook을 shadow pass에 포함

`bundle_shadow.py`에 `search_wisdom_index`/`playbook_bullets_for_topic`을 실제 `build_context_bundle`이 쓰는 것과 동일한 R1 게이트(`parallel_round==1`, wisdom은 추가로 `_wisdom_route_allows`+실제 `_session_folder`+`wisdom_index_enabled`)로 재호출하도록 추가했다. `context/bundle.py`는 이번엔 전혀 안 건드렸다 — slim path의 shadow 호출부가 원래 `parallel_round=2`를 넘기고 있어서 R1 게이트가 자동으로 걸러준다(실제로 slim path는 이 두 producer를 절대 안 부른다는 것과 정확히 일치).

**재실행 결과: 이번 dogfood 스크립트에선 `semantic_memory`가 여전히 안 나타났다.** 버그가 아니라 이 스크립트의 synthetic run_meta가 `_session_folder`를 안 채우고(wisdom_index는 실제 세션 폴더의 인덱스 파일이 필요) `AGENT_LAB_WISDOM_IN_CONTEXT`/`AGENT_LAB_PLAYBOOK` 플래그도 기본값(off/auto)이라서다 — 게이트가 의도대로 정확히 막고 있다는 뜻이다. 전용 단위 테스트(`tests/test_context_bundle_shadow.py::test_shadow_compare_bundle_includes_wisdom_and_playbook_on_r1`)에서 이 두 producer를 stub해서 REPAIR activity가 `semantic_memory`를 실제로 포함하는 것과, `parallel_round != 1`이면 두 producer가 호출조차 안 되는 것(`test_shadow_compare_bundle_skips_wisdom_and_playbook_when_not_r1`) 둘 다 확인했다.

**이제 shadow pass에서 의도적으로 제외된 producer가 하나도 없다.** 남은 항목은 딱 하나:
1. `legacy_total_chars`/`recipe_total_tokens` 단위 정규화 — 여전히 미착수.

다음에 이 dogfood 스크립트를 실행할 여지가 있다면, `_session_folder`에 실제 wisdom 인덱스가 있는 세션(또는 `AGENT_LAB_WISDOM_IN_CONTEXT=1`/`AGENT_LAB_PLAYBOOK=1` 강제)을 하나 추가해서 wisdom_index/playbook이 실제로 included되는 걸 dogfood 표본에서도 시연하는 게 좋겠다.

---

## 2026-07-16 5차 — char/token 단위 정규화

4차례 실행 내내 "legacy_total_chars(문자)와 recipe_total_tokens(추정 토큰)는 단위가 달라 직접 비교할 수 없다"를 미해결로 남겼었다. `bundle_shadow.py`가 이제 `legacy_estimated_tokens`(레거시 렌더 결과에 `select_context()` 자신이 쓰는 것과 동일한 `estimate_tokens()` 공식을 적용)와 `recipe_to_legacy_token_ratio`를 함께 반환한다.

### 재실행 결과 — activity별 recipe/legacy 토큰 비율

| activity | min | max | avg | 해석 |
| --- | --- | --- | --- | --- |
| clarify | 1.247 | 1.296 | 1.267 | recipe가 레거시보다 ~1.27배 큰 컨텍스트를 고름 |
| plan | 1.287 | 1.408 | 1.361 | recipe가 레거시보다 ~1.36배 큰 컨텍스트를 고름 |
| execute | 0.357 | 0.410 | 0.381 | recipe가 레거시의 ~38%만 고름(훨씬 타이트) |
| critic | 0.302 | 0.339 | 0.322 | recipe가 레거시의 ~32%만 고름(훨씬 타이트) |
| repair | 0.900 | 0.908 | 0.903 | 거의 동등(레거시의 ~90%) |

**이건 실제 방향성 있는 신호다** — CLARIFY/PLAN은 recipe가 legacy보다 더 많은 컨텍스트를 포함하는 경향(§7.1이 PLAN에 40% "relevant repo/docs" 배분을 주는 것과 방향은 일치), EXECUTE/CRITIC은 recipe가 훨씬 적게 고르는 경향(legacy가 이 두 activity에서 실제로 필요한 것보다 과하게 담고 있었을 가능성, 또는 recipe가 §6.4/§6.3의 "무관한 전체 context 제외" 원칙을 실제로 지키고 있다는 신호일 수도 있음 — 이번 데이터만으론 어느 쪽인지 구분 안 됨). REPAIR는 거의 동등.

**cutover 판정을 내리기엔 여전히 이르다** — 36개 synthetic 시나리오뿐이고, 이 비율이 "recipe가 더 낫다"는 뜻인지 "recipe가 아직 못 담는 producer가 있어서 작게 나온다"는 뜻인지(예: EXECUTE/CRITIC엔 mailbox/wisdom_index/playbook 트래픽이 원래 적을 수도 있음) 이 실행만으론 분간 안 된다. 실제(또는 더 다양한) 세션 코호트로 표본을 늘리고, 이 비율이 activity별로 안정적인지 확인한 뒤에 판단할 문제다.

---

## 2026-07-16 6차 — 실제 세션 코호트로 표본 확대

지금까지 5차례 전부 하나의 synthetic run_meta를 손으로 만들어 variant를 돌린 것이었다. 이번엔 `scripts/context_recipe_shadow_real_session_cohort.py`(신규, `make context-recipe-shadow-real-cohort`)로 **실제 세션 데이터**를 기반으로 8개 시나리오를 추가로 돌렸다:

### 소스 1 — 저장소에 이미 있는 real regression fixture 7개

`sessions/_regression/`(README.md가 관리하는 golden baseline, structural smoke-test용)의 실제 `run.json` 7개를 그대로 로드했다:

| fixture | 실제 phase | 매핑 activity |
| --- | --- | --- |
| `mission_loop_discuss_recovery` | DISCUSS | plan |
| `wisdom_index_built` | DISCUSS | plan |
| `mission_loop_plan_reject` | PLAN_REJECT | plan |
| `mission_loop_execute_queue` | EXECUTE_QUEUE | execute |
| `plan_workflow_pw5_latency` | EXECUTE_QUEUE | execute |
| `evidence_gates_merged_ok` | VERIFY | critic |
| `evidence_ledger_stream` | VERIFY | critic |

**정직하게 밝히는 한계**: 이 fixture들은 `run.json`만 있고 `chat.jsonl`/`plan.md`/`workspace_binding`이 없다(구조적 smoke-test 베이스라인이라 그럼). `mission_loop`/`topic`/`executions` 상태는 진짜지만, `plan_md`/`messages`/`workspace_binding`/artifact 1건은 스크립트가 보충했다 — 보충한 부분과 진짜 부분을 스크립트 자체 docstring/코드 주석에 명시했다.

### 소스 2 — 새로 구동한 실제 mock mission 1건 (REPAIR)

기존 regression fixture 중 `run.json`이 REPAIR phase로 끝나는 게 하나도 없어서, `scripts/mission_dogfood_run.py`가 쓰는 것과 **동일한 실제** `mission/loop.py`/`mission/advance.py`/`verified_loop.py` 함수를 그대로 호출해서 세션 하나를 처음부터 끝까지 실제로 구동했다 — 단 Oracle verdict를 `pass` 대신 `fail`로 줘서 `MISSION_DONE` 대신 `REPAIR`에 도달하게 했다. 이 세션은 `run.json`/`chat.jsonl`/`plan.md` **전부 진짜**(디스크에 실제로 써짐, `read_plan_gate`/`patch_run_meta`/`on_verify_result` 등 실제 함수가 만든 결과) — `artifacts`(Room의 별도 producer라 mission_loop 경로가 안 채움) 1건만 보충. 스크래치 디렉터리(`tempfile.mkdtemp()`)에 만들고 `sessions/`(git 커밋 금지 경로)엔 안 건드림.

### 결과

```
scenario_count: 8
ok_count: 8
skipped_count: 0
failed_count: 0
```

| scenario | recipe/legacy 비율 |
| --- | --- |
| fixture:mission_loop_discuss_recovery | 1.187 |
| fixture:wisdom_index_built | 1.194 |
| fixture:mission_loop_plan_reject | 1.190 |
| fixture:mission_loop_execute_queue | 0.469 |
| fixture:plan_workflow_pw5_latency | 0.374 |
| fixture:evidence_gates_merged_ok | 0.432 |
| fixture:evidence_ledger_stream | 0.433 |
| real_repair_session | 0.825 |

**5차의 synthetic 결과와 방향이 정확히 일치한다** — PLAN 계열(discuss_recovery/wisdom_index_built/plan_reject) 전부 ~1.19(legacy보다 크게), EXECUTE 계열 전부 ~0.37~0.47(legacy보다 훨씬 작게), CRITIC 계열(VERIFY fixture) 전부 ~0.43(작게), REPAIR는 ~0.83(거의 동등, synthetic의 ~0.90과 비슷한 범위). **서로 다른 두 표본(순수 synthetic vs 실제 세션 상태 기반)이 같은 activity별 패턴을 보인다는 건, 이 비율 차이가 우연이나 내 synthetic 데이터의 특이성이 아니라 recipe pipeline의 실제(재현 가능한) 특성이라는 근거가 하나 늘었다는 뜻이다.**

### 여전히 커버 안 된 것

- **CLARIFY** — 이 phase로 끝나는 real regression fixture가 하나도 없다. 실제 clarifier interview 흐름을 구동하는 건 이번 범위 밖으로 남겨뒀다.
- **SCRIBE** — 애초에 매핑되는 mission phase가 없다(`bundle_recipe.py` 자체 문서화, scribe context는 `core/limits.py::ScribeContextLimits`라는 별개 미수렴 경로).

### 그래도 cutover 판정은 아직

두 개의 독립적인 표본(synthetic 5차, 실제 세션 6차)이 같은 방향을 가리키는 건 고무적이지만, 표본 수 자체는 여전히 적고(6차는 8개, 5차는 36개 — 전부 합쳐도 소규모), CLARIFY/SCRIBE는 아예 실제 데이터가 없다. "recipe가 EXECUTE/CRITIC에서 legacy보다 훨씬 작게 고르는 게 좋은 신호(무관한 것 제외)인지 나쁜 신호(아직 못 담는 producer가 있어서)인지"도 여전히 미결이다.
