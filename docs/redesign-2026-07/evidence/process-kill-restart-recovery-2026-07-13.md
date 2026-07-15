# API/daemon process kill→restart recovery — 2026-07-13

ADR-001의 마지막 남은 블로커("process-restart gate")를 실제 별도 uvicorn 서브프로세스로 채웠다. 이전 증거는 "새 `ActivityQueue` 인스턴스가 같은 디스크 파일을 읽는다"로 재시작을 *시뮬레이션*했지만, 이번엔 진짜 프로세스를 `SIGKILL`로 죽이고 완전히 새 프로세스(새 PID)를 재기동해 실제 네트워크 HTTP로 검증했다.

`scripts/mission_process_kill_restart_recovery.py`, 대상은 실제 운영 `sessions/`. exit code `0`.

## 판정

| 항목 | 결과 |
| --- | --- |
| Process A 기동 | pid 65714, `/api/health` 200 |
| plan/approve (kill 전) | 200, `mirrored=true`, `READY_TO_EXECUTE` |
| G3 crash-window fixture | 실제 `git merge --no-ff`로 exec 브랜치가 base에 랜딩; `run.json`은 `pending_approval` + 살아있는 `checkpoint.phase=merging`으로 남김(진짜 크래시가 merge 성공 직후·status flip 직전에 났을 때와 동일한 디스크 상태) |
| SIGKILL | pid 65714 확인 종료(`process_confirmed_gone=true`), 포트 close 확인 |
| Process B 기동 | pid 65972(≠65714), `/api/health` 200 |
| G3 자동 boot 스캔 (`/api/health/daemon`) | `scanned=116, reconciled_merged=1, rolled_back=0, quarantined=0, errors=0` — 기존 세션 115개는 전혀 건드리지 않고 우리가 심은 1건만 reconcile |
| G3 reconcile 결과 | `run.json` status `merged`, `merge.commit_sha`가 실제 git HEAD(`e2415ff...`)와 일치, `checkpoint` 제거, `recovery.action=reconciled_merged` |
| Mission read-model (kill 전후 비교) | 둘 다 `migrated=true`, `state=READY_TO_EXECUTE` — 진짜 kill/restart 후에도 journal replay 일치 |
| production route 지속 동작 | `POST /api/mission-scheduler/tick?force=true` → 200, `ok=true` (process B가 정상 서비스 중) |
| ActivityQueue 자동 복구 (당시 실행 시점) | **아니오** — 이 report의 process-kill 실행은 자동 복구 연결 전 커밋에서 수행되어, 재기동만으로는 COMMITTED 상태 그대로(`auto_recovered_by_process_restart_alone=false`) |
| ActivityQueue 수동 복구 | 명시적으로 `.recover()` 호출하면 정상 동작(`recovered_after_explicit_recover_call=true`, action=`complete`) |

## 무엇을 실제로 확인했는가

1. **`agent_lab.crash_recovery.reconcile_crashed_merges()`는 이미 프로덕션에 존재하는 자동 메커니즘**이고(`app/server/main.py::_api_startup`에서 매 부팅마다 호출, `AGENT_LAB_CRASH_RECOVERY` 기본 on), 진짜 크래시 윈도우(merge는 git에 랜딩했지만 `run.json` status flip 전에 죽음)를 실제로 만들어 실제 kill+restart로 검증했다. 결과는 git ground truth와 정확히 일치했고, 무관한 실제 세션 115개는 스캔만 하고 전혀 건드리지 않았다(`rolled_back=0, quarantined=0, errors=0`).
2. **Mission journal replay는 진짜 프로세스 재시작에도 안전하다.** `MissionRepository.load()`가 매번 `journal.recover_tail()`을 호출하므로, 완전히 새로운 프로세스가 같은 파일을 열어도 `read-model`이 kill 직전과 동일한 상태를 반환했다.
3. **이 실행이 포착한 당시 상태:** `ActivityQueue.recover()`는 해당 process-kill 증거를 수집한 시점에는 자동 경로에 연결돼 있지 않았다. 따라서 재기동만으로 COMMITTED 상태가 그대로 남았고, 명시적 `.recover()` 호출은 정상 동작했다. 이후 [ActivityQueue 자동 복구 연결](./activity-queue-auto-recovery-2026-07-13.md)이 `_api_startup()`과 `scheduler_tick()`에 startup eager + throttled non-blocking safety-net으로 연결되었으며, runtime flag/profile 등록·테스트·live `/api/health/daemon` 관찰까지 완료했다. 이 문서의 부정 결과는 **historical pre-connection evidence**로 유지한다.

## 안전장치

- 시작 전 실제 `sessions/`를 스캔해 이미 살아있는 `checkpoint.phase=merging`이 있는 세션이 있으면 즉시 중단하도록 만들었다(우리가 만든 fixture와 우연히 겹쳐 실제 위기 상황을 잘못 reconcile하는 것을 방지). 이번 실행 전 hit 0건.
- 서버 프로세스는 격리된 `AGENT_LAB_CONFIG_DIR`·`AGENT_LAB_DAEMON_STATE`로 띄워 사용자의 실제 `~/.agent-lab/daemon_state.json`이나 run-lock을 건드리지 않았다.
- 포트는 사전에 빈 포트(8891)인지 확인 후 사용했다.
- 증거 수집용 세션 폴더(`dualwrite-crash-01-process-restart`, `dualwrite-crash-02-activity-queue`)는 실제 `sessions/`에서 제거했고, `git status --short sessions/`로 그 외 변경 없음을 재확인했다.

## 후속 판정

이 report 자체의 G3 kill/restart 결과는 여전히 유효하다. ActivityQueue 자동 복구 gap은 후속 구현·검증 문서에서 닫혔으므로, 현재 cutover 재심사의 남은 결정은 기술적 blocker가 아니라 **legacy writer retire와 Mission 단일 authority 승격에 대한 명시적 Human 승인**이다.
