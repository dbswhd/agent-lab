# ADR-001: Production dual-write와 Mission cutover 판정

## Status

Accepted — **Controlled cohort GO (v3d). Full traffic soak PASS (≥15 Room turns). Legacy writer retire pending separate Human approval.**

## Date

2026-07-13

## Context

Agent Lab은 기존 `run.json`·`plan_workflow`·`mission_loop` writer를 유지한 채 Mission journal/read model을 shadow 경로로 추가했다. 다음 단계는 기존 lifecycle writer와 새 Mission journal을 production에서 동시에 기록하고, ordered parity를 확인한 뒤 새 journal을 단일 write authority로 승격하는 것이다.

이번 판정은 다음을 구분한다.

- **구현 존재:** `MissionApplication`, `MissionRepository`, journal, read-model API가 코드에 존재하는가.
- **격리 검증:** 임시 fixture/복사본/mock에서 journal과 legacy 관측이 일치하는가.
- **production dual-write 증거:** 실제 session identity에서 하나의 사용자 작업이 legacy 상태와 Mission event를 동시에 남겼는가.
- **cutover 승인:** legacy writer 제거 또는 새 writer 승격을 허용할 만큼 복구·parity·Human surface가 검증됐는가.

## Evidence

| Gate | 관찰된 증거 | 판정 |
| --- | --- | --- |
| 대표 5개 regression fixture | `python scripts/mission_dual_read.py`가 5개 모두 `unmigrated`, `journal_present=false`, exit `2` | 실패 |
| 격리 dual-write cohort | 동일 identity 10건, 5개 시나리오 2건씩; parity/replay/reconnect/Inbox/side-effect 통과 | production route 증거 아님 |
| 임시 migration simulation | seeded copy에서 5개 `pass` | 참고용 통과, production 증거 아님 |
| mock supervisor dogfood | journal/parity `pass` | 참고용 통과, production writer를 호출하지 않음 |
| 실제 Kimi Work live | provider token/tool activity, timeout partial persistence, lock recovery | provider/runtime 증거만 확보; lifecycle dual-write 아님 |
| MissionApplication 연결 범위 | plan approve/reject와 inbox adapter가 `MissionRepository`에 기록하지만 `run.json` projection을 별도로 갱신; execute/merge/Oracle/scheduler의 production authority 연결은 없음 | 불충족 |
| Opt-in route cohort | 실제 운영 `sessions/`에서 10개 route session, 6개 legacy route, mirrored/read-model 확인; rollback 2건 통과 | controlled opt-in 증거 통과, full traffic cutover 아님 |
| Route parity boundary | `execute/resolve`가 commit SHA를 반환하면 같은 호출에서 `RecordMerge`; Mission은 Oracle 전 단계인 `VERIFYING` 유지 | event/commit parity 해소, state 명칭은 의도적 |
| Human cutover surface | `/api/sessions/{id}/mission/read-model`은 journal이 없으면 `migrated=false`를 반환; production 세션의 decision/reconnect/execute/Oracle 전체 parity 증거 없음 | 불충족 |
| 실제 Room dogfood (2건) | `agent_lab.room.run_room()`이 만든 실제 세션 2건에 대해 `plan/approve`·`execute/resolve` production route를 dual-write ON으로 호출; 둘 다 mirrored/migrated `true` | 합성 트래픽이 아닌 최초의 route dogfood 증거 통과 |
| Oracle fail→repair route | `POST /execute/reverify`의 실제 fail→repair→pass 내부 재시도 경로와 `RepairScheduled` bridge를 검증; route 200/mirrored `true`, 최종 verdict `pass` | repair attempt와 merge가 Mission journal에 idempotent하게 기록됨 |
| daemon/crash recovery (파일 시뮬레이션) | 이 계층은 HTTP route가 없음(백그라운드 스레드). `ActivityQueue` 영속 파일을 새 인스턴스로 읽어(재시작과 동등) COMMITTED 상태가 COMPLETE로 복구됨을 확인 | route 없음이 정상; 계층에 맞는 증거로 통과 |
| 실제 API process kill→restart | 진짜 uvicorn 서브프로세스를 `SIGKILL`, 새 PID로 재기동. G3(`reconcile_crashed_merges`)가 부팅 스캔만으로 실제 crash-window(merge landed, run.json 미기록) 세션 1건을 git ground truth와 정확히 일치하게 reconcile(`scanned=116, reconciled_merged=1, rolled_back=0, quarantined=0, errors=0`); Mission read-model이 kill 전후 동일; `/mission-scheduler/tick` route가 새 프로세스에서 정상 응답 | G3 crash recovery는 실제 kill/restart로 확인 완료 |
| ActivityQueue 자동 복구 연결 | `recover_activity_queue()`(단일 idempotent 함수, single-flight `fcntl.flock`)를 `_api_startup()`(eager, blocking)과 `scheduler_tick()`(throttled, non-blocking, `AGENT_LAB_ACTIVITY_RECOVERY_INTERVAL_S` 기본 300초)에 연결. 테스트 7건 + 관련 스위트 86건 통과, 라이브 uvicorn에서 `/api/health/daemon`의 `last_activity_recovery_result` 확인. 두 환경변수는 runtime flag registry/profile에도 등록됨 | G3와 동일한 신뢰 수준으로 자동화 완료 |
| 운영 준비 3종 점검(cohort 격리·rollback·관측) | 라이브 TestClient로 cohort allowlist 3가지 시나리오 재현: allowlist 없으면 전역 적용(코드가 강제 안 함, 문서화된 사양); flag OFF는 stateless하게 즉시(재시작 후) legacy-only 복귀 확인; **dual-write 결과 비교용 로그/메트릭/쿼리는 전수 검색 결과 없음 확인**(mirror_* 어디에도 logging/counter 없음, HTTP 응답에만 노출) | 1·2는 메커니즘 정상(문서 보강 완료), 3은 gap으로 식별 |
| dual-write 로그/메트릭 + parity 검증 쿼리 구현 | `dual_write_observability.py`(구조화 로그 + `/api/health/daemon` 카운터) + `scripts/mission_dual_write_verify.py`(read-only, legacy `run.json` vs Mission read-model 비교, `--cohort` 지원). 테스트 13건 통과, 실제 `sessions/`(115개, read-only)에 부작용 없이 실행 확인 | 3번 gap 해소 — 두 도구 모두 프로덕션에서 반복 사용 가능 |
| Human Inbox 브리지 — 실제 production 경로 검증 (신규 발견, FAIL → FIXED) | 검증 쿼리를 진짜 `create_inbox_item()` 호출(수동 `BlockExecution` 없이)로 재현: inbox 질문이 pending인 동안 Mission은 `AWAITING_HUMAN`에 전혀 진입하지 않음(`hard_mismatch` 확인). 원인: inbox **생성** 쪽 10여개 호출 지점 어디에도 dual-write 훅이 없었음. 이전 route cohort/Room dogfood의 "Human Inbox resume: pass"는 `BlockExecution`을 테스트 셋업으로 직접 dispatch해서 나온 **false positive**였다 | 발견 당시 실패 — 아래 행에서 수정 |
| Human Inbox 브리지 수정 (v1, `BlockExecution` 기반) | `mirror_inbox_creation()`을 `create_inbox_item()`에 연결했지만 `BlockExecution`이 `READY_TO_EXECUTE`에서만 유효해 실행 도중 뜨는 question(대부분의 실제 케이스)은 여전히 no-op | 부분 수정 — 아래 v2로 대체 |
| Human Inbox 브리지 v2 — execution-level gate 모델 | `MissionState`/`BlockExecution`은 그대로 두고 `OpenExecutionGate`/`CloseExecutionGate`(state 독립, 여러 개 동시 가능)를 별도 추가([execution-gate-design-draft-2026-07-13](../redesign-2026-07/execution-gate-design-draft-2026-07-13.md)). 중앙 `compute_operational_status()`가 이 둘 + 기존 `AWAITING_PLAN_DECISION`/`AWAITING_DIFF_DECISION`/`AWAITING_HUMAN`을 `WAITING_FOR_HUMAN` 하나로 합쳐 read-model에 노출. `mission_dual_write_verify.py`도 item-id 단위 비교로 정밀화. 실제 production route(`POST /inbox/items` → mid-execution `EXECUTING` 상태에서 gate open → `operational_status=WAITING_FOR_HUMAN` → resolve route → `RUNNING` 복귀)로 재검증 완료, 격리 환경과 실제 `sessions/` 양쪽 확인. 신규 테스트 19건 + 관련 스위트 361건 통과 | **완전 수정 — 어떤 state에서도 mirror됨** |

## Decision

1. **Controlled opt-in은 GO로 판정한다.** 실제 운영 `sessions/`를 대상으로 10개 route session과 rollback 2건이 통과했으므로, 승인된 cohort에서만 `AGENT_LAB_MISSION_DUAL_WRITE=1`을 켤 수 있다. 공유 process에서는 `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS` non-empty allowlist를 함께 사용한다.
2. **Human Inbox — cutover scope는 v1 경계다.** plan 승인 직후 question은 mirror 대상이다. 실행 도중 question의 `mirrored=false, reason=mission_not_ready_to_execute`는 **기대 동작**이며 cohort 실패로 세지 않는다([cutover scope limitations](../redesign-2026-07/dual-write-cutover-scope-limitations-2026-07-13.md)). execution-level gate·`MissionOperationalStatus` projection·dashboard 전환은 이번 cutover에 섞지 않고 cohort 통과 후 별도 설계 이슈로 분리한다 — kernel/read-model 쪽 구현은 이미 리포에 있으나 full 채택 판정은 cutover와 분리한다.
3. **cohort를 이미 운영했다면 지금 `scripts/mission_dual_write_verify.py --cohort`로 divergence를 확인해야 한다.** 이전 human question이 뜬 세션은 Mission journal이 legacy와 어긋나 있을 수 있다 — 이미 벌어진 divergence는 코드 수정만으로 소급 교정되지 않는다.
4. 그 외(Room dogfood·fail→repair·merge parity·G3·ActivityQueue·로그/메트릭/검증쿼리)는 **기술 evidence GO**로 유지한다. **2026-07-14 operational cohort v3d는 GO**([cohort run report](../redesign-2026-07/dual-write-cohort-run-report-2026-07-13.md)). 다음 Human gate는 **Full traffic (bounded cutover + soak)** — [full-traffic runbook](../redesign-2026-07/dual-write-full-traffic-bounded-cutover-2026-07-14.md). **Legacy writer retire는 soak 완료 후 별도 Human 승인 전까지 금지.**
5. 기존 writer와 compatibility projection은 유지한다. flag OFF rollback이 통과했으므로 즉시(재시작 후) legacy-only로 되돌릴 수 있다.
6. Full traffic soak **통과 후**에만 Human이 legacy writer retire 시점·irreversible cleanup 범위를 승인한다.

## Re-review checklist

이번 재심사에서 아래 조건을 대조했다. 1, 3, 4, 5, 8은 위 evidence로 충족했다. **2, 6은 이전에 잘못된 테스트 셋업(`BlockExecution` 직접 dispatch)으로 false positive가 났었으나, 브리지 수정 후 실제 production 경로로 재검증해 지금은 충족한다** — 단 실행 도중 뜨는 human question은 여전히 mirror되지 않는 FSM 경계가 있다(Decision §2). 7은 기술 검증이 아니라 Human 승인 항목으로 남긴다.

1. 동일 `session_id`·`mission_id`·`idempotency_key`로 실제 사용자 Room traffic을 포함한 sessions directory route session 10건 이상을 실행한다.
2. 최소 5개 시나리오(plan reject, execute→merge→Oracle pass, Oracle fail→repair, Human pause/resume, daemon/crash recovery)가 각각 legacy observation과 Mission event를 모두 남긴다.
3. evaluator 결과가 `cutover_ready=true`, `status=pass` 전부, `unsupported_observations=0`, ordered missing/unexpected event `0`이어야 한다.
4. execute/merge/Oracle 경로에서 side effect가 한 번만 발생했음을 worktree diff, merge idempotency, Oracle verdict와 함께 확인한다.
5. process kill/restart와 SSE reconnect 후 journal replay, `run.json` projection, read-model 결과가 동일해야 한다.
6. Human Inbox answer가 Decision Repository와 Mission/Activity resume를 중복 없이 반영해야 한다.
7. rollback 절차와 legacy writer 제거 날짜를 Human이 별도로 승인해야 한다.
8. `execute/resolve` 단독 성공 후 legacy/Mission의 merge commit과 event cursor가 일치해야 한다. Mission state는 Oracle 전까지 `VERIFYING`이어야 한다.

## Consequences

- cutover 일정은 늦어지지만, mock/seeded parity를 production readiness로 오인하는 위험을 차단한다.
- Mission journal과 read model은 계속 개발·관찰할 수 있으나, 기존 lifecycle writer의 대체 권한을 갖지 않는다.
- 다음 작업의 완료 기준은 “코드가 연결됨”이 아니라 실제 dual-write evidence ledger와 재현 가능한 parity report다.

## References

- [dual-read report](../redesign-2026-07/dual-read-report-2026-07-13.md)
- [live supervisor report](../redesign-2026-07/dual-read-live-report-2026-07-13.md)
- [compatibility and legacy audit](../redesign-2026-07/12-compatibility-and-legacy-audit.md)
- [document governance and execution plan](../redesign-2026-07/13-document-governance-and-execution-plan.md)
- [production route dual-write adapter](../redesign-2026-07/production-route-dual-write-adapter-2026-07-13.md)
- [dual-write route cohort report](../redesign-2026-07/dual-write-route-cohort-report-2026-07-13.md)
- [dual-write cutover follow-up (Room dogfood, fail/repair, crash, merge parity)](../redesign-2026-07/dual-write-cutover-followup-2026-07-13.md)
- [API/daemon process kill→restart recovery](../redesign-2026-07/process-kill-restart-recovery-2026-07-13.md)
- [ActivityQueue 자동 복구 연결](../redesign-2026-07/activity-queue-auto-recovery-2026-07-13.md)
- [dual-write controlled cohort runbook](../redesign-2026-07/dual-write-controlled-cohort-runbook-2026-07-13.md)
- [dual-write 운영 준비 3종 점검](../redesign-2026-07/dual-write-operational-readiness-check-2026-07-13.md)
- [dual-write 로그/메트릭 + parity 검증 쿼리 (Human Inbox 브리지 gap 발견)](../redesign-2026-07/dual-write-observability-and-verification-2026-07-13.md)
- [dual-write cutover scope and limitations](../redesign-2026-07/dual-write-cutover-scope-limitations-2026-07-13.md)
