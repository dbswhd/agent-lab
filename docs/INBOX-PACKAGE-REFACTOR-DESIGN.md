# Inbox package refactor (shipped)

Moved `inbox_*.py` → `src/agent_lab/inbox/` (Human gate harvest + MCP).

| Old | New |
|-----|-----|
| `inbox_harvest.py` | `inbox/harvest.py` |
| `inbox_facilitator.py` | `inbox/facilitator.py` |
| `inbox_mcp_policy.py` | `inbox/mcp_policy.py` |
| `inbox_mcp_server.py` | `inbox/mcp_server.py` |

MCP module path: `python -m agent_lab.inbox.mcp_server`

Cursor bridge wiring stays at `cursor_inbox_mcp.py` (adapter layer).

```bash
make audit-inbox-imports
make typecheck-inbox-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md) · [MCP-FIRST-INBOX.md](MCP-FIRST-INBOX.md).
