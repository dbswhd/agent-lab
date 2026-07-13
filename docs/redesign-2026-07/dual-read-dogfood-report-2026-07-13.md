# Supervisor dogfood dual-read report — 2026-07-13

> **판정:** mock-only supervisor dogfood + shadow projection `pass`
> **범위:** 기존 `scripts/mission_dogfood_run.py`를 임시 sessions root에서 실행한 뒤 Mission journal을 shadow projection하고 parity evaluator를 재실행

## 실행 결과

| 항목 | 결과 |
| --- | --- |
| legacy dogfood | `dogfood_ok=true` |
| Mission journal | `journal_present=true` |
| dual-read | `pass` |
| observed core events | `MergeCommitted`, `OraclePassed` |
| missing/unexpected | 없음 |

실행 명령:

```bash
BASE=$(mktemp -d)
python scripts/mission_dogfood_dual_read.py \
  --sessions "$BASE" \
  --session-id supervisor-dual-read
```

## 해석

- 기존 dogfood runner의 legacy run은 통과했다.
- 그 결과를 바탕으로 새 Mission event journal을 shadow projection하고 ordered parity를 확인했다.
- 실제 production writer와 daemon/scheduler는 변경하지 않았다.
- 이 경로는 mock-only다. 실제 provider를 사용하는 live supervisor dogfood의 근거로 대체하지 않는다.

## 다음 gate

실제 supervisor dogfood session에서 동일한 read model/event evidence를 수집하고, Human이 dual-write 기간과 cutover 범위를 승인한 뒤에만 production enqueue를 검토한다.
