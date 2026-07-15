# R1 — Journey reliability matrix (2026-07-16)

> [05-reliability-evaluation-operations.md](../05-reliability-evaluation-operations.md) §4 R1의
> 산출물. `sessions/_regression/`에 이미 39개 golden fixture와 README 표가 있다 — R1은 이걸 처음부터
> 새로 만드는 게 아니라 8개 journey(start/plan/execute/diff/verify/repair/resume/cancel)로 재정리하고
> 빈 곳을 드러내는 감사다. **판정을 바꾸지 않는다** — R2(fault injection)가 어디를 채워야 하는지 정하는
> 근거 문서다.

## 1. Journey × fixture 매트릭스

| journey | 커버하는 `sessions/_regression/*` fixture | evidence tier |
| --- | --- | --- |
| start | `discuss`, `review-on`, `category_escalation_quick_to_deep`, `dispatch_parallel_explore` | deterministic fixture |
| plan | `plan`, `plan_workflow_approved`, `plan_workflow_pw5_latency`, `objection_blocks_execute`, `challenge_revises_metric`, `mission_loop_plan_reject`, `mission_loop_execute_queue` | deterministic fixture |
| execute | `worktree_merge_ok`, `worktree_reject`, `worktree_unavailable`, `worktree_apply`, `snapshot_override_pending`, `pre_execute_blocked`, `adversarial_gate_lgtm` | deterministic fixture |
| diff | `merge_conflict`, `ui_pending_diff` | deterministic fixture |
| verify | `execute_verify_loop`, `evidence_gates_merged_ok`, `evidence_ledger_stream`, `mission_loop_verify_repair` | deterministic fixture |
| repair | `execute_verify_loop`(LC-L3 repair loop), `mission_loop_verify_repair` | deterministic fixture |
| resume | `durable_completed_steps`, `mission_loop_paused`, `mission_loop_circuit_breaker`, `mission_loop_discuss_recovery` | deterministic fixture |
| cancel | **없음** — `sessions/_regression/`에 cancel 시나리오 fixture가 없다 | unit test만(`test_run_control.py` 등, §3) |

fixture 없이 unit test로만 다뤄지는 부수 journey: `mailbox_handoff`(A2A 메시징), `bridge_degraded_health`(provider degraded), `wisdom_index_built`, `envelope_consensus_endorse`, `recombination_synthesis`, `specialist_asymmetric_cwd`, `specialist_r2_artifact_only`, `producer-reviewer-roles`, `mission_loop_dogfood_ok`, `emergence_hybrid_plan`, `external_handoff_attached` — 이들은 8개 핵심 journey 밖의 보조 시나리오(role/topology/messaging/wisdom)라 이번 매트릭스에서 제외했다.

## 2. Deterministic/mock/live 구분

`sessions/_regression/`의 39개는 전부 **deterministic fixture**(minimal `run.json` 재생, mock agent)다.
`make dogfood-suite-mock`/`make dogfood-progress-record`(`docs/NOW.md`)가 **mock dogfood** 계층을,
NOW.md의 라이브 dogfood 트랙(F7/N4-D3/CATALOG/HS-M5/N1-30)이 **live** 계층을 담당한다 — 이 세 계층
전부 이미 존재하고, R1이 요구하는 "각 journey에 deterministic/mock/live evidence가 구분된다"는 계층
자체는 새로 만들 게 없다. 새로 만들어야 하는 건 journey→계층 매핑을 명시한 표(이 문서 §1)뿐이었다.

## 3. Cancel — 유일한 실질 커버리지 갭

`plan/execute_resolve.py::cancel_open_execution`이 실제 cancel 로직이고, unit test는 있다
(`test_run_control.py` 외 9개 파일이 "cancel" 관련 테스트를 가짐 — grep 결과). 하지만 **regression
golden fixture가 없다** — 즉 "cancel된 세션의 최종 run.json 형태"가 dogfood/smoke 비교 대상으로
고정돼 있지 않다. §4에서 R1 acceptance criteria로 이 gap을 명시적으로 기록한다.

이건 A1(provider capability inventory, `docs/redesign-2026-07/evidence/a1-provider-capability-inventory-2026-07-16.md`)에서
발견한 "provider-level invoke cancel을 찾지 못함"과 같은 축의 문제다 — execution 단위 cancel(이 문서)과
provider 호출 단위 cancel(A1)이 서로 다른 계층이지만, 둘 다 "cancel"이라는 이름의 진짜 커버리지가
설계 문서 대비 약하다는 같은 결론으로 수렴한다.

## 4. 부수 발견 — README와 실제 fixture 디렉터리 drift

`sessions/_regression/README.md`의 표에 없는데 디렉터리에는 있는 fixture 4개: `recombination_synthesis`,
`ui_pending_diff`, `plan_workflow_pw5_latency`, `mission_loop_discuss_recovery`. 기능은 있는데 문서화가
안 된 상태 — README 갱신은 이 문서의 범위 밖(별도 정리 필요, R1 판정에는 영향 없음).

## 5. R1 acceptance criteria 대조

| 기준 | 상태 |
| --- | --- |
| start/plan/execute/diff/verify/repair/resume/cancel 전부 포함 | 7/8 커버됨. **cancel만 fixture 커버리지 없음**(§3) |
| deterministic/mock/live evidence 구분 | 이미 3계층 존재, 매핑만 새로 문서화(§2) |
| 미검증 경로가 명시적으로 드러난다 | cancel(§3) + README drift 4건(§4) |

**검증**(R1이 요구하는 "CI가 matrix의 fixture/test link 존재를 검사"): 이 문서 자체는 스크립트를
새로 안 만들었다 — §1 표에 나열된 fixture 이름은 `sessions/_regression/`에 실제로 존재하는지
`tests/test_regression_journey_matrix.py`가 확인한다.

## 6. 다음

R2(fault injection suite)는 이 매트릭스가 비어 있다고 확인한 곳(cancel) 먼저 채우는 게 맞다 —
`sessions/_regression/`에 cancel golden fixture를 하나 추가하는 게 R2 첫 조각으로 가장 낮은 리스크다.
