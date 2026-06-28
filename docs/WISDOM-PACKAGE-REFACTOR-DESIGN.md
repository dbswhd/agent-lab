# Wisdom package refactor (shipped)

Moved `wisdom_*.py` → `src/agent_lab/wisdom/`.

| Old | New |
|-----|-----|
| `wisdom_index.py` | `wisdom/index.py` |
| `wisdom_store.py` | `wisdom/store.py` |
| `wisdom_mcp.py` | `wisdom/mcp.py` |
| `wisdom_mcp_server.py` | `wisdom/mcp_server.py` |

MCP module path: `python -m agent_lab.wisdom.mcp_server`

```bash
make audit-wisdom-imports
make typecheck-wisdom-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
