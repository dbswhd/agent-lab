# MCP tool contract — agentic trading

두 MCP 서버의 **허용 read 도구**, **단일 write 도구**, **금지 execute/full-json** 경계를 코드로 고정합니다.
거래 control-plane v1 의미론의 canonical source는 quant-agentic-trading
`docs/agentic-trading-v1-spec.md`입니다.

## 서버 분리

| Server | Module | 역할 |
|--------|--------|------|
| `agent-lab-research` | `agent_lab.research.mcp_server` | playbook, batch, cards, critic, wisdom (장전·장중 read) |
| `quant-trading` | `quant_pipeline.agentic_trading.mcp_server` | control plane read + **create_trade_proposal** write |

배치 ingest(`proposal_batch.json` → SQLite)는 **MCP가 아닌 CLI/internal** 경로입니다.

```bash
PYTHONPATH=src python -m quant_pipeline.agentic_trading.ingest_cli ...
```

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

추가 read: `get_proposal`, `get_control_plane_snapshot`

**유일한 write tool:** `create_trade_proposal` — `backtest_ref` + cached ResearchArtifactCard 필수

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
- `ingest_proposal_batch`, `ingest_trading_session` (quant MCP write surface에 포함 금지)

v1 live 실행은 Human console / Quant Control UI 승인만 허용합니다. paper/mock
자동 실행은 quant-agentic-trading v1 spec의 `paper_auto_eligible()` 조건을
통과한 경우에만 허용됩니다.

## 검증

```bash
cd ~/Projects/agent-lab
PYTHONPATH="$HOME/Projects/quant-agentic-trading/src" make verify-mcp-contract
```

구현: `src/agent_lab/mcp_tool_contract.py` + `tests/test_mcp_tool_contract.py`

## Cursor 등록

`docs/mcp-trading.example.json` — `PYTHONPATH`에 quant-agentic-trading `src`, `QUANT_PIPELINE_ROOT`, `AGENTIC_TRADING_DB` 필수.

```json
"AGENT_LAB_FRESHNESS_PYTHON": "/Users/yoonjong/Desktop/pipeline/.venv/bin/python"
```

freshness subprocess는 pipeline venv(pandas) 사용.
