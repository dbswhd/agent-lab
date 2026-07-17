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

1. 더 다양한 synthetic/실제 세션으로 반복 실행해 `context_recipe_shadow` 표본을 늘린다.
2. `legacy_total_chars`/`recipe_total_tokens`를 같은 단위로 정규화해서 "recipe가 실제로 더
   타이트하게 고르는가"를 판단한다.
3. mailbox/wisdom_index/playbook을 포함하도록 splice 시점을 재검토한다(mailbox는 특히
   `build_mailbox_block` 호출 **이전** 시점에 별도로 shadow 자료를 뽑아야 한다).
4. 위 데이터가 충분히 쌓이면 실제 cutover(레거시 문자열 대신 recipe manifest 사용) 여부를
   결정한다 — 이 문서는 그 결정을 내리지 않는다.
