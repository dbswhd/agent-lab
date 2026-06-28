# Research package refactor (shipped)

Moved `research_*.py` → `src/agent_lab/research/`.

| Old | New |
|-----|-----|
| `research_artifact_card.py` | `research/artifact_card.py` |
| `research_mcp_read.py` | `research/mcp_read.py` |
| `research_mcp_server.py` | `research/mcp_server.py` |

MCP module path: `python -m agent_lab.research.mcp_server`

Pipeline read helpers (`pipeline_research_read.py`, `pipeline_market_read.py`) stay at root — separate wave.

```bash
make audit-research-imports
make typecheck-research-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md) · [MCP-TOOL-CONTRACT.md](MCP-TOOL-CONTRACT.md).
