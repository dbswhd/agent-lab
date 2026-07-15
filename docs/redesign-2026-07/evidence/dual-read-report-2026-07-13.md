# 대표 fixture dual-read parity report — 2026-07-13

> **판정:** `cutover_ready=false`
> **실행:** `python scripts/mission_dual_read.py`
> **범위:** [mission-baseline.json](../../tests/fixtures/mission-baseline.json)의 대표 5개 regression fixture

## 1. 결과

| 시나리오 | legacy observation | Mission journal | 상태 | 이유 |
| --- | --- | --- | --- | --- |
| plan reject → revisit | `plan_rejected` | 없음 | `unmigrated` | 새 event stream이 없음 |
| execute success → merge → Oracle pass | `plan_approved`, `execution_merged`, `oracle_passed` | 없음 | `unmigrated` | 새 event stream이 없음 |
| Oracle fail → repair | `execution_merged`, `oracle_failed`, `execution_merged`, `oracle_passed` | 없음 | `unmigrated` | 새 event stream이 없음 |
| Human Inbox pause/resume | `mission_paused` | 없음 | `unmigrated` | 새 event stream이 없음 |
| daemon/crash recovery | `step_completed` | 없음 | `unmigrated` | 새 event stream이 없음 |

## 2. Gate 판정

이번 결과는 drift가 아니라 **migration evidence 부재**다. journal이 없는 fixture를 parity pass로 간주하지 않았고, legacy scheduler·writer·execute path도 변경하지 않았다.

따라서 현재는 다음을 승인하지 않는다.

- legacy writer 제거
- production scheduler의 ActivityQueue enqueue 전환
- Mission journal을 유일한 write authority로 승격
- Step 7 문서·코드 retire

## 3. 다음 실행

1. 각 대표 시나리오를 `MissionApplication`/Mission repository 경로로 재생성한다.
2. legacy `run.json`과 새 journal을 같은 session identity로 보존한다.
3. `python scripts/mission_dual_read.py`를 다시 실행한다.
4. 5개 모두 `pass`, `unsupported_observations=0`, ordered event drift=0인지 확인한다.
5. 그 결과를 Checkpoint D Human cutover review에 제출한다.

**현재 결론:** parity report 경로는 작동하지만, 실제 dual-read data가 아직 없어 cutover gate는 닫혀 있다.
