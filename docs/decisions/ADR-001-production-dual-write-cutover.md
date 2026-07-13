# ADR-001: Production dual-write와 Mission cutover 판정

## Status

Accepted — **NO-GO / cutover 보류**

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
| Opt-in route adapter | plan/inbox/execute/merge/Oracle route 뒤에 `AGENT_LAB_MISSION_DUAL_WRITE=1`일 때만 fail-open bridge가 실행됨; 기본 off, local smoke와 test suite 통과 | 구현 완료, production cohort 미실행 |
| Human cutover surface | `/api/sessions/{id}/mission/read-model`은 journal이 없으면 `migrated=false`를 반환; production 세션의 decision/reconnect/execute/Oracle 전체 parity 증거 없음 | 불충족 |

## Decision

1. **Production route dual-write 증거는 현재 0건으로 판정한다.** 격리 cohort 10건은 실제 legacy writer와 MissionRepository를 동일 identity로 실행해 통과했지만, production route가 자동으로 두 저장소에 쓴 증거는 아니므로 production dual-write 기간을 시작한 것으로 간주하지 않는다.
2. **Human cutover는 NO-GO로 결정한다.** legacy writer 제거, Mission journal 단일 authority 승격, production scheduler enqueue 전환, read-model 기본 전환을 승인하지 않는다.
3. 기존 writer와 compatibility projection은 유지한다. 이번 판정은 rollback을 위해 legacy 경로를 보존하는 결정이다.
4. 다음 단계는 기능 확장이 아니라 production evidence 수집이다. 별도 격리 cohort에서 한 번에 하나의 수직 절편을 dual-write한 뒤 parity와 재시작 결과를 기록한다.

## Required evidence before re-review

다음 재심사에서 아래 조건을 모두 만족해야 한다.

1. 동일 `session_id`·`mission_id`·`idempotency_key`로 실제 sessions directory에서 dual-write flag를 켠 route session 10건 이상을 실행한다.
2. 최소 5개 시나리오(plan reject, execute→merge→Oracle pass, Oracle fail→repair, Human pause/resume, daemon/crash recovery)가 각각 legacy observation과 Mission event를 모두 남긴다.
3. evaluator 결과가 `cutover_ready=true`, `status=pass` 전부, `unsupported_observations=0`, ordered missing/unexpected event `0`이어야 한다.
4. execute/merge/Oracle 경로에서 side effect가 한 번만 발생했음을 worktree diff, merge idempotency, Oracle verdict와 함께 확인한다.
5. process kill/restart와 SSE reconnect 후 journal replay, `run.json` projection, read-model 결과가 동일해야 한다.
6. Human Inbox answer가 Decision Repository와 Mission/Activity resume를 중복 없이 반영해야 한다.
7. rollback 절차와 legacy writer 제거 날짜를 Human이 별도로 승인해야 한다.

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
