# MCP tool contract — agentic trading

두 MCP 서버의 **허용 read 도구**와 **금지 execute/full-json** 경계를 코드로 고정합니다.

## 서버 분리

| Server | Module | 역할 |
|--------|--------|------|
| `agent-lab-research` | `agent_lab.research_mcp_server` | playbook, batch, cards, critic, wisdom (장전·장중 read) |
| `quant-trading` | `quant_pipeline.quant_trading_mcp_server` | ingest, control plane, portfolio/freshness/kill switch |

## quant-trading (필수 read tools)

| Tool | 설명 |
|------|------|
| `get_backtest_card(ref)` | 캐시 카드 ~2KB (full JSON 금지) |
| `get_data_freshness()` | spec91 freshness, `blocking` / `trade_allowed` |
| `get_kill_switch_status()` | `EMERGENCY_STOP` 플래그 |
| `get_portfolio_snapshot()` | RiskEngine용 cash/equity/positions |
| `get_quote(symbol, market)` | mock-first compact quote |
| `list_eligible_strategies(limit)` | PASS 카드만 |
| `list_pending_proposals(limit)` | control plane pending + risk |

추가 (ingest/조회): `ingest_proposal_batch`, `ingest_trading_session`, `get_proposal`, `get_control_plane_snapshot`

## agent-lab-research (필수 read tools)

| Tool | 설명 |
|------|------|
| `get_playbook` / `get_pending_batch` | thin runtime 산출물 |
| `get_intraday_status` | playbook + batch + console pending 번들 |
| `get_backtest_card` / `get_strategy_verdict` | artifact card SSoT |
| `list_wireup_candidates` | PASS eligible 목록 |
| `get_data_freshness` / `get_portfolio_snapshot` | pipeline read |
| `get_kill_switch_status` | EMERGENCY_STOP (research 측 alias) |

장전 전용: `run_backtest_refresh(ref, dry_run=True)`, `review_proposal_thesis`, `wisdom_search`

## 전역 금지 (어떤 MCP에도 expose 금지)

- `execute_order`, `approve_proposal`, `arm_live`
- `read_notebook`, `read_full_backtest_json`, `read_full_json`, `read_ipynb`

Human console / Quant Control UI만 승인·실행.

## 검증

```bash
cd ~/Projects/agent-lab
PYTHONPATH="$HOME/Documents/New project/src" make verify-mcp-contract
```

구현: `src/agent_lab/mcp_tool_contract.py` + `tests/test_mcp_tool_contract.py`

## Cursor 등록

`docs/mcp-trading.example.json` — `PYTHONPATH`에 New project `src`, `QUANT_PIPELINE_ROOT`, `AGENTIC_TRADING_DB` 필수.

```json
"AGENT_LAB_FRESHNESS_PYTHON": "/Users/yoonjong/Desktop/pipeline/.venv/bin/python"
```

freshness subprocess는 pipeline venv(pandas) 사용.
