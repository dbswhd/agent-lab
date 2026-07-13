# Journal-backed dual-read migration simulation — 2026-07-13

> **판정:** `cutover_ready=true` in isolated temporary copy only
> **범위:** regression fixture를 임시 디렉터리로 복사한 뒤 Mission journal/ActivityQueue를 seed하고 parity evaluator를 실행

## 실행

```bash
python scripts/seed_mission_dual_read.py --target /tmp/agent-lab-dual-read/seeded
python scripts/mission_dual_read.py --root /tmp/agent-lab-dual-read/seeded
```

## 결과

| 시나리오 | 새 근거 | 관측 event/evidence | 상태 |
| --- | --- | --- | --- |
| plan reject → revisit | Mission journal | `PlanRejected` | `pass` |
| execute success → merge → Oracle pass | Mission journal | `PlanApproved`, `MergeCommitted`, `OraclePassed` | `pass` |
| Oracle fail → repair | Mission journal | `MergeCommitted`, `OracleFailed`, `MergeCommitted`, `OraclePassed` | `pass` |
| Human Inbox pause/resume | Mission journal | `BlockOpened` | `pass` |
| daemon/crash recovery | completed ActivityQueue | `recovery-step-1` | `pass` |

## 해석과 제한

- 이 결과는 **temporary migration simulation**이다. `sessions/_regression/**` 원본은 변경하지 않았다.
- 실제 production session의 dual-read 결과는 [2026-07-13 report](./dual-read-report-2026-07-13.md)처럼 아직 `unmigrated`다.
- crash recovery는 Mission event가 아니라 ActivityQueue completion evidence로 표현했다. 이를 Mission journal event로 억지로 승격하지 않는다.
- 따라서 이 시뮬레이션만으로 legacy writer 제거, production scheduler enqueue, cutover 승인을 하지 않는다.

## 다음 gate

실제 supervisor dogfood session 하나를 새 application/queue 경로로 실행하고, 동일 evaluator에서 `pass`를 얻은 뒤 Human review를 요청한다.
