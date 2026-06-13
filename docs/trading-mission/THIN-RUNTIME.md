# Trading Mission — thin intraday runtime

장중 **풀 Room 없이** playbook · pending batch · control plane queue만 읽고 Human approve를 돕는 루프.

## Session template

- **ID:** `trading-thin`
- **Workspace:** `quant-pipeline`
- **금지:** Room discuss, `run_backtest_refresh(dry_run=False)`, live execute

Agent-lab UI preset: `session_setup_options().trading_thin_preset`

## CLI status (no MCP)

```bash
export AGENT_LAB_SESSION_FOLDER=~/Projects/agent-lab/sessions/<today-premarket-session>
export AGENTIC_TRADING_DB=~/Documents/New\ project/data/agentic_trading/control_plane.sqlite3

cd ~/Projects/agent-lab
.venv/bin/python -m agent_lab.trading_mission.thin_runtime \
  --session "$AGENT_LAB_SESSION_FOLDER" \
  --db "$AGENTIC_TRADING_DB"
```

`AGENT_LAB_SESSION_FOLDER` 미설정 시 **최신** `artifacts/proposal_batch.json` 세션을 자동 선택.

## Cursor MCP 등록

`~/.cursor/mcp.json` (경로는 환경에 맞게 수정):

```json
{
  "mcpServers": {
    "agent-lab-research": {
      "command": "/Users/yoonjong/Projects/agent-lab/.venv/bin/python",
      "args": ["-m", "agent_lab.research_mcp_server"],
      "env": {
        "QUANT_PIPELINE_ROOT": "/Users/yoonjong/Desktop/pipeline",
        "AGENTIC_TRADING_DB": "/Users/yoonjong/Documents/New project/data/agentic_trading/control_plane.sqlite3",
        "AGENT_LAB_SESSION_FOLDER": "/Users/yoonjong/Projects/agent-lab/sessions/<your-premarket-session>"
      }
    },
    "quant-trading": {
      "command": "/Users/yoonjong/Projects/agent-lab/.venv/bin/python",
      "args": ["-m", "quant_pipeline.quant_trading_mcp_server"],
      "env": {
        "PYTHONPATH": "/Users/yoonjong/Documents/New project/src",
        "QUANT_PIPELINE_ROOT": "/Users/yoonjong/Desktop/pipeline",
        "AGENTIC_TRADING_DB": "/Users/yoonjong/Documents/New project/data/agentic_trading/control_plane.sqlite3"
      }
    }
  }
}
```

예시 파일: `docs/mcp-trading.example.json`

등록 후 Cursor 재시작 → MCP 도구 목록에 `get_intraday_status`, `get_playbook`, `list_pending_proposals` 등 표시.

## Thin agent 워크플로 (장중)

1. `get_intraday_status()` — mission_id, playbook preview, batch, console pending
2. `get_playbook()` / `get_pending_batch()` — 상세 읽기
3. `list_pending_proposals()` (quant-trading) — risk_status 포함
4. `get_data_freshness()` / `get_kill_switch_status()` — trade_allowed 게이트 확인
5. Human: control plane console에서 approve → paper execute
6. 필요 시 `review_proposal_thesis()` — thesis/ref 검증만 (새 Room 없음)

## 환경 변수

| 변수 | 용도 |
|------|------|
| `AGENT_LAB_SESSION_FOLDER` | 장전 Mission 세션 (없으면 최신 자동) |
| `AGENTIC_TRADING_DB` | control plane SQLite |
| `QUANT_PIPELINE_ROOT` | pipeline read tools |
| `AGENTIC_APPLY_PROPOSAL_CRITIC` | ingest 시 critic cap (장전) |

## Console

```bash
PYTHONPATH=src python -m quant_pipeline.agentic_trading.server \
  "$AGENTIC_TRADING_DB" 8877
```

`:8765` 점유 시 alternate port 사용.
