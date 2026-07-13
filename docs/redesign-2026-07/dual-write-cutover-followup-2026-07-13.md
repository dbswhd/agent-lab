# Dual-write cutover follow-up — Room dogfood + fail/repair + crash + merge parity — 2026-07-13

ADR-001의 "다음 단계" 3개 항목([Decision §4](../decisions/ADR-001-production-dual-write-cutover.md))을 순서대로 처리한 결과다. 전부 실제 운영 `sessions/` 디렉터리를 대상으로 실행했고, 증거 수집 후 합성 세션 폴더는 정리했다.

## 1) `execute/resolve` merge event parity

이미 `src/agent_lab/mission/dual_write.py`의 `mirror_execution_transition`(phase=`approve`)에 반영되어 있었다 — commit SHA가 있으면 diff-approve 직후 같은 호출에서 `RecordMerge`를 dispatch한다(`tests/test_mission_dual_write.py::test_execute_approve_mirrors_merge_commit_without_advancing_oracle`로 커버).

- `AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python -m pytest tests/test_mission_dual_write.py tests/test_plan_execute_reverify_api.py tests/test_plan_execute_worktree.py tests/test_plan_execute_revise_api.py -q` → **27 passed**.
- 실제 `sessions/`에서 `execute/resolve`(approve, clean worktree merge) 재실행 → `merged_commit_sha_recorded_same_call=true`, read-model이 같은 호출 안에서 `VERIFYING`(merge 완료, Oracle 대기)까지 도달함을 재확인.

**판정: 해소.** 이전 리포트가 "다음 호출까지 지연"이라고 적었던 것은 fix 이전 상태였고, 지금은 단일 호출 안에서 merge event parity가 맞는다.

## 2) fail→repair route evidence

`scripts/mission_dual_write_route_cohort.py`에 `_scenario_execute_reverify_oracle_fail_repair`를 추가해 `POST /execute/reverify`의 실제 oracle-fail → agent repair → 재검증 → pass 경로를 exercise했다(`tests/test_plan_execute_reverify_api.py::test_execute_reverify_endpoint_repairs_oracle_fail`과 동일한 기법: `registry.available_agents`/`cursor_agent.respond`를 결정적으로 monkeypatch, 실 LLM 호출 없음).

실제 `sessions/`에서 실행한 결과(`dualwrite-route-11-fail-repair`):

| 항목 | 값 |
| --- | --- |
| route | `POST /execute/reverify` |
| status | 200 |
| repair_status | `merged` |
| repair_agent | `cursor` |
| final_oracle_verdict | `pass` |
| mirrored | `true` |
| read-model migrated / state | `true` / `SUCCEEDED` |

**결정 및 구현:** Mission은 최종 outcome뿐 아니라 repair 시도도 추적한다. `dual_write.py`는 legacy `repair_history`에 commit 증거가 있으면 `Oracle FAIL → RepairScheduled → DiffReady → DiffApproved → MergeCommitted → Oracle PASS`를 idempotent하게 기록한다. 따라서 legacy의 `verify_history`·`repair`와 Mission의 `repair_attempt`·`REPAIRING` 전이가 같은 lifecycle을 설명한다. commit 증거가 없는 repair는 fail-open으로 `repair_commit_missing`을 반환하며 최종 event를 추정하지 않는다.

## 3) crash/daemon recovery evidence

**HTTP route가 존재하지 않는다.** `ActivityQueue`/scheduler daemon(`start_mission_scheduler_background`)은 API 프로세스 내 백그라운드 스레드로 동작하며 전용 router가 없다(`app/server/routers/`에 activity_queue를 노출하는 라우터 없음 확인). 따라서 "route evidence"는 이 계층에 대해선 성립하지 않는다.

대신 영속성 계층에서 증거를 남겼다(`_scenario_crash_recovery`, `dualwrite-route-12-crash-recovery`): 실제 `sessions/`에 활동을 enqueue → claim → side-effect COMMITTED까지 기록한 뒤, **같은 디스크 파일을 읽는 새 `ActivityQueue` 인스턴스**(= 프로세스 재시작과 동등)로 `recover()`를 호출해 `COMPLETE`로 정리되는지 확인했다.

| 항목 | 값 |
| --- | --- |
| route | 없음(daemon in-process) |
| recovery_action | `complete` |
| recovered_and_completed | `true` |

**판정: 계층에 맞는 persistence 증거 확보.** 진짜 프로세스 kill/restart(예: uvicorn을 SIGKILL 후 재기동)까지는 하지 않았다. 따라서 crash evidence는 durable queue recovery 기준을 통과했지만, process-level cutover gate는 별도 확인이 필요하다.

## 4) 실제 Room dogfood 2건

`scripts/mission_dual_write_room_dogfood.py` 신규 작성. `scripts/x2_lift_dogfood_run.py`와 같은 mock 관례(`AGENT_LAB_MOCK_AGENTS`, isolated config dir)를 따르되, 그 스크립트가 추적하는 `docs/_dogfood/x2-lift.md` fixture는 건드리지 않고 별도 topic을 썼다.

흐름: `agent_lab.room.run_room()`으로 **실제 멀티에이전트 Room 턴**(peer discussion, mock cursor/codex/claude 응답)을 돌려 세션을 만든 뒤, 그 세션에 대해 `plan/approve`·`execute/resolve` **production route**를 dual-write ON으로 호출했다.

실제 `sessions/`에서 실행한 2건:

| session | agent turns | peer review rounds | plan 출처 | plan/approve mirrored | execute/resolve mirrored |
| --- | ---: | ---: | --- | --- | --- |
| 세션 A (plan approve 확인) | 4 msgs / 1 turn | 0 | fallback(파싱 가능한 plan 보장용) | `true` | `true` (merged, VERIFYING) |
| 세션 B (execute route 확인) | 4 msgs / 1 turn | 1 | 실제 patched `synthesize_plan` 산출(178자) | `true` | `true` (merged, VERIFYING) |

두 세션 모두 `read_model.migrated=true`. 세션 B는 room 파이프라인이 실제로 `HUMAN_PENDING` plan_workflow 상태까지 만들어냈고(peer review 라운드 1회 포함), 세션 A는 그 산출물이 비어 있어 스크립트가 파싱 가능한 fallback plan으로 보완했다 — 두 경로 모두 real-Room-traffic → production-route 증거로 유효하다.

**판정: 통과.** 합성 스크립트 트래픽이 아닌, 실제 Room 멀티에이전트 파이프라인이 만든 세션에 대한 production route dual-write 증거를 처음으로 확보했다.

## 정리

증거 수집에 쓴 세션 폴더(`dualwrite-route-11/12`, Room dogfood 2건)는 실제 운영 `sessions/`에서 제거했다. `git status --short sessions/`로 그 외 변경 없음을 재확인했다. 스크립트(`scripts/mission_dual_write_route_cohort.py`, `scripts/mission_dual_write_room_dogfood.py`)는 재사용 가능하도록 리포지터리에 남겨뒀다(git 미추적).

## 다음 판정 후보

1·2·3·4번은 route/persistence/event parity 기준으로 닫혔다. Repair 시도 추적은 Mission journal에 반영하는 설계로 확정했고, 관련 테스트를 통과했다. 이후 ActivityQueue 자동 복구를 startup eager + scheduler throttled 경로에 연결하고 runtime health를 live uvicorn으로 확인했다. 따라서 현재 남은 것은 기술적 blocker가 아니라 legacy writer retire/Mission 단일 authority 승격에 대한 명시적 Human 승인이다.
