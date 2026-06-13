# Trading Mission — offline lane (주간 wire-up)

주 1회 Agent-lab 세션 없이도 **deterministic lane**으로 카드·WireUpDecision·runtime playbook을 갱신합니다.  
풀 Room은 선택(별도 UI 세션 `trading-offline` 템플릿).

## 한 줄 실행

```bash
cd ~/Projects/agent-lab
QUANT_PIPELINE_ROOT=~/Desktop/pipeline \
  make offline-lane
```

또는:

```bash
.venv/bin/python scripts/run_trading_mission_offline.py --force
```

## 산출물

| 경로 | 내용 |
|------|------|
| `sessions/.../artifacts/wireup_decision.json` | WireUpDecision/v1 |
| `sessions/.../artifacts/playbook.md` | 주간 active_refs + 「오늘 장중 행동」 |
| `pipeline/data/agentic/wireup_decision.json` | runtime ingest (MCP thin agent) |
| `pipeline/data/agentic/playbook.md` | 동일 playbook |

**proposal_batch ingest 없음** — 주간은 전략 선별만.

## WireUpDecision 필드

- `active_refs` — PASS + eligible, 상위 N (default 8)
- `watch_refs` — 다음 티어 후보
- `blocked_refs` — FAIL / ineligible
- `card_sync` — `build-research-cards` 리포트

## 환경 변수

| 변수 | 기본 | 용도 |
|------|------|------|
| `AGENT_LAB_OFFLINE_ACTIVE_CAP` | 8 | active_refs 상한 |
| `AGENT_LAB_OFFLINE_WATCH_CAP` | 12 | watch_refs 상한 |
| `AGENT_LAB_WISDOM_INDEX` | off | 1이면 `wisdom/wireup-*.md` + index |

## 주간 스케줄 (선택)

```cron
# 일요일 10:00 KST
0 10 * * 0 cd ~/Projects/agent-lab && QUANT_PIPELINE_ROOT=~/Desktop/pipeline .venv/bin/python scripts/run_trading_mission_offline.py
```

## 검증

```bash
.venv/bin/python -m pytest tests/test_trading_mission_offline_lane.py -q
```

## Room 세션 (선택)

UI에서 template **Trading · 주간 offline** (`trading-offline`)으로 세션 생성 후 전략 리뷰.  
Lane 스크립트는 Room 없이도 wireup artifact를 채웁니다.
