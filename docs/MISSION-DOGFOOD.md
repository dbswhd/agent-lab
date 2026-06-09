# Mission Loop — live dogfood checklist (Week 2)

Mock 스모크(`sessions/_regression/mission_loop_*`)는 FSM 스냅샷만 검증합니다. 실 사용 품질은 **한 건의 live/mock 미션**을 끝까지 돌린 뒤 아래를 점검하세요.

## 준비

```bash
make dev
# Mission Loop 활성 (세션 또는 env)
export AGENT_LAB_MISSION_LOOP=1
```

## 실행 (1 mission)

1. Transcript에서 목표·제약을 discuss로 합의
2. Work → plan gate 통과 → autonomous 구간 허용(필요 시)
3. execute → verify → merge까지 1 action 이상
4. ⌘. 또는 circuit breaker로 **pause** 한 번 재현 (선택)
5. Resume로 `runtime.boulder.resume_phase` (또는 `last_partial`) 복귀 확인 — mock: `make mission-dogfood-run`이 `last_failure`/`boulder` lifecycle 검증

## Mock dogfood (CI-safe, no API)

```bash
make mission-dogfood-run
```

Creates `sessions/dogfood-<utc>/`, runs plan gate → pause/resume → verify PASS → `MISSION_DONE`, then prints KPI report.

## KPI (`make score-session` / dogfood report)

```bash
LATEST=$(ls -t sessions | grep -v '^_' | grep -v '^dogfood' | head -1)
make score-session SESSION=sessions/$LATEST
python scripts/mission_dogfood_report.py sessions/$LATEST
```

회귀 golden: `make mission-dogfood-report`

| 항목 | 기대 |
|------|------|
| `mission_loop.repair_events` | verify FAIL 시만 증가; cap 미만 |
| `mission_loop.notepad_chars` | `learnings.md` 등에 회고·검증 기록 > 200 chars |
| `mission_circuit_breaker` | 정상 완료 시 0 |
| `mission_completed` | `MISSION_DONE` 시 100% |

## Notepad 품질 (수동)

- [ ] `verification.md` — 마지막 verify verdict·명령 요약
- [ ] `learnings.md` — 실패 원인·다음 시도와 **중복 없음**
- [ ] `decisions.md` — Human gate·BLOCK 해소 기록 (해당 시)

## 회귀

```bash
make smoke          # 23 baselines incl. mission_loop_*
make test -k mission_loop
```

SSOT: [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) · Oracle: [LIVE-ORACLE.md](./LIVE-ORACLE.md)
