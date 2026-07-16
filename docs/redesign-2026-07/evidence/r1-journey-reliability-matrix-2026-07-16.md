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
| cancel | golden fixture 없음(§3에서 왜 필요 없는지 설명) | `tests/test_execute_cancel.py`(2026-07-16 추가, §3) |

fixture 없이 unit test로만 다뤄지는 부수 journey: `mailbox_handoff`(A2A 메시징), `bridge_degraded_health`(provider degraded), `wisdom_index_built`, `envelope_consensus_endorse`, `recombination_synthesis`, `specialist_asymmetric_cwd`, `specialist_r2_artifact_only`, `producer-reviewer-roles`, `mission_loop_dogfood_ok`, `emergence_hybrid_plan`, `external_handoff_attached` — 이들은 8개 핵심 journey 밖의 보조 시나리오(role/topology/messaging/wisdom)라 이번 매트릭스에서 제외했다.

## 2. Deterministic/mock/live 구분

`sessions/_regression/`의 39개는 전부 **deterministic fixture**(minimal `run.json` 재생, mock agent)다.
`make dogfood-suite-mock`/`make dogfood-progress-record`(`docs/NOW.md`)가 **mock dogfood** 계층을,
NOW.md의 라이브 dogfood 트랙(F7/N4-D3/CATALOG/HS-M5/N1-30)이 **live** 계층을 담당한다 — 이 세 계층
전부 이미 존재하고, R1이 요구하는 "각 journey에 deterministic/mock/live evidence가 구분된다"는 계층
자체는 새로 만들 게 없다. 새로 만들어야 하는 건 journey→계층 매핑을 명시한 표(이 문서 §1)뿐이었다.

## 3. Cancel — R2 first slice (2026-07-16, closed)

**정정:** 이 문서를 처음 쓸 때 "unit test는 있음"이라고 적었는데 부정확했다 — `test_run_control.py`가
테스트하는 건 `agent_lab.run.control`의 **turn/subprocess 레벨 cancel**(`request_cancel()`, 실행 중인
child process kill)이지, `plan/execute_resolve.py::cancel_open_execution`(merge 전 open dry-run/
merge-review를 버리는 **execution 레벨 cancel**)이 아니다. 실제로 확인해 보니
`cancel_open_execution`은 **테스트가 하나도 없었다**.

`tests/test_execute_cancel.py`(2026-07-16 추가)가 이 함수의 세 분기를 전부 덮는다: 열린 execution이
없을 때 no-op, 상태가 cancellable이 아닐 때 no-op, 성공 시 reject + worktree discard. **golden
`run.json` fixture는 추가하지 않았다** — `cancel_open_execution`은 내부적으로
`resolve_execution(vote="reject")`를 그대로 호출하므로, 성공 시 persisted 상태는 기존
`worktree_reject/` fixture와 동일하다(`status: "rejected"`). `reason="user_cancel"`은
`cancel_open_execution`의 반환값에만 있고 `run.json`에는 안 남는다 — 즉 진짜 gap은 "run.json 형태가
안 고정됨"이 아니라 "호출 지점 자체(no-op 분기 2개 + 성공 경로)가 테스트된 적이 없었음"이었다.

A1(provider capability inventory)에서 발견한 "provider-level invoke cancel을 찾지 못함"은 여전히
별개 미해결 문제로 남아 있다 — execution 단위 cancel(이 문서, 이제 해결됨)과 provider 호출 단위
cancel(A1, 미해결)은 다른 계층이다.

## 4. 부수 발견 — README와 실제 fixture 디렉터리 drift

`sessions/_regression/README.md`의 표에 없는데 디렉터리에는 있는 fixture 4개: `recombination_synthesis`,
`ui_pending_diff`, `plan_workflow_pw5_latency`, `mission_loop_discuss_recovery`. 기능은 있는데 문서화가
안 된 상태 — README 갱신은 이 문서의 범위 밖(별도 정리 필요, R1 판정에는 영향 없음).

## 5. R1 acceptance criteria 대조

| 기준 | 상태 |
| --- | --- |
| start/plan/execute/diff/verify/repair/resume/cancel 전부 포함 | **8/8 커버됨** — cancel은 golden fixture 대신 직접 unit test로 닫힘(§3) |
| deterministic/mock/live evidence 구분 | 이미 3계층 존재, 매핑만 새로 문서화(§2) |
| 미검증 경로가 명시적으로 드러난다 | README drift 4건(§4) — cancel은 §3에서 해결됨 |

**검증**(R1이 요구하는 "CI가 matrix의 fixture/test link 존재를 검사"): §1 표에 나열된 fixture 이름은
`sessions/_regression/`에 실제로 존재하는지 `tests/test_regression_journey_matrix.py`가 확인하고,
`tests/test_execute_cancel.py`가 cancel journey 자체를 커버한다.

## 6. 다음

R1이 찾은 유일한 실질 gap(cancel)은 R2 첫 조각으로 닫혔다(§3). R2(fault injection suite)의 나머지
범위(agent timeout, process kill, partial journal, git merge ambiguity, SSE disconnect, stale Human
command)는 아직 손대지 않았다 — 각각이 독립적인 fault-injection 시나리오라 이 문서 하나로 스코프를
정할 수 없다.
