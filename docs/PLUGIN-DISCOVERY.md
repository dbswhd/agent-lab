# Plugin & command discovery (Phase A + B)

> **Status (2026-06-07):** Phase A discovery + **Phase B shipped** — `PluginPanel`, session allowlist API, execute/repair pass-through (`session_plugin_runtime.py`, `mcp_spec_export.py`). See [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) Track B.

## Summary

| Agent | List installed plugins/MCP | Pass config into Room turn | Agent Lab today |
|-------|---------------------------|----------------------------|-----------------|
| **Claude** | `claude mcp list`, `claude plugin list`; skills via `.claude/skills/*/SKILL.md` | `--mcp-config` allowlist overlay; discuss `build_plugin_allowlist_block` | Room + **execute/repair** MCP overlay |
| **Codex** | `codex plugin list`, `codex mcp list` | `-c mcp_servers.*` from `codex mcp get --json`; inbox MCP | Room + **execute/repair** transport export |
| **Cursor** | IDE-inherited (no list API) — `cursor-ide-mcp-hint` in UI | SDK `mcp_servers` for inbox; IDE MCP implicit | `PluginPanel` documents inheritance |

**Dual use (Phase B target):**

1. **Autonomous** — allowlisted MCP/plugins available during a turn (product decides when to call).
2. **Explicit** — Human `/slash` or Composer menu → Agent Lab routes to server action or agent invoke.

---

## Claude Code

### Discovery commands (verified locally)

```bash
claude mcp list          # MCP servers + health (HTTP/stdio)
claude mcp get <name>
claude plugin list       # marketplace plugins (may be empty)
claude plugin install <plugin@marketplace>
```

Skills (repo or workspace):

```bash
ls .claude/skills/*/SKILL.md   # frontmatter: name, description, tools
```

Legacy slash files: `.claude/commands/` (optional; same role as skills in older docs).

### Pass-through flags (`claude -p`)

Relevant for Phase B ([claude_cli.py](../src/agent_lab/claude_cli.py) does **not** use these today):

| Flag | Purpose |
|------|---------|
| `--mcp-config <json\|file>` | Load MCP servers for this invocation |
| `--plugin-dir` | Extra plugin directories |
| `--add-dir` | Already used via `resolve_claude_roots()` |
| `--disable-slash-commands` | Disables **all** skills — avoid in Room |
| `--bare` | Skips auto-discovery; explicit context only |

Skills resolve via **`/skill-name`** in the user prompt (Claude Code native). Agent Lab can map canonical slash → `/skill-name` in the prompt body.

### cwd / discovery pitfall

Room `cwd` = `discuss_primary_workspace()` (often quant-pipeline, not agent-lab). Skills in **agent-lab** `.claude/skills/` are invisible unless:

- `--add-dir` includes agent-lab repo, or
- workspace bootstrap copies/syncs skills into bound project.

### Phase B recommendation

- **`discover_claude()`** — parse `claude mcp list` stdout + scan `.claude/skills` under workspace roots.
- **Room invoke** — append `--mcp-config` from session allowlist; inject skill body on `/command` agent_invoke.
- Remove unconditional anti-MCP lines in [agent_permissions.py](../src/agent_lab/agent_permissions.py) when allowlist non-empty.

---

## Codex CLI

### Discovery commands

```bash
codex plugin list        # marketplaces + installed/enabled plugins
codex mcp list           # stdio + HTTP MCP servers + status
codex mcp get <name>
codex doctor             # install/config health
```

Example plugin rows (local machine): `browser@openai-bundled`, `documents@openai-primary-runtime`, etc.

### Pass-through

`codex exec` loads user config from `~/.codex/config.toml` and `CODEX_HOME`. Agent Lab does not pass `-c` overrides for MCP today ([codex_cli.py](../src/agent_lab/codex_cli.py)).

Room turns use read-only sandbox + command cap unless `CODEX_ROOM_WORKSPACE_WRITE=1`.

### Phase B recommendation

- **`discover_codex()`** — wrap `codex plugin list` + `codex mcp list` (parse tables; exit 0 required).
- **Session allowlist** — filter discovered ids; optional `-c mcp_servers...` if exec supports per-run overlay (spike in Phase B).
- **Explicit slash** — map to appended exec prompt or Codex-native slash if documented.

---

## Cursor (SDK bridge)

### Discovery

**No stable list API** in [cursor_agent.py](../src/agent_lab/agents/cursor_agent.py) / [cursor_bridge.py](../src/agent_lab/cursor_bridge.py).

Indirect signals:

- Activity callbacks may label tool keys containing `mcp` ([cursor_activity.py](../src/agent_lab/cursor_activity.py)).
- MCP/plugins come from **Cursor IDE** project/user config — same as interactive Cursor agent.

### Pass-through

```python
AgentOptions(api_key=..., model=..., local=LocalAgentOptions(cwd=cwd_str))
```

No MCP/plugin fields in current SDK usage.

### Phase B recommendation

- **Inventory:** read-only panel section “Cursor plugins/MCP are managed in Cursor IDE” + link to Cursor settings; optional future SDK field when available.
- **Autonomous:** rely on bridge inheritance; log MCP tool names in SSE for Human visibility.
- **`cursor.tools=false`:** should disable SDK tools in code (today prompt-only — fix in Phase B).

---

## Agent Lab built-in commands (Phase B seed)

Canonical slash commands (not product plugins):

| slash | kind | Action |
|-------|------|--------|
| `/goal-check` | server | `POST .../goal/check` |
| `/goal-set` | server | focus goal banner |
| `/stop` | client | cancel run |
| `/plan` | server | switch room mode plan |
| `/consensus` | server | consensus profile |

Merged with discovered agent commands in `GET /api/commands`.

---

## External tools (Phase C)

LazyCodex / git tools — not discoverable via Claude/Codex/Cursor CLIs. Register in `~/.agent-lab/tools.yaml` (planned); expose under **External** group in slash menu.

LazyCodex **patterns** (L1–L5) already shipped in Agent Lab code; **external runner** (`$ulw-loop`, boulder state) remains Phase C.

---

## Security

- Default CI/mock: empty discovery, plugins off.
- Session **allowlist** required before pass-through.
- Human gate for external tool subprocess (Phase C).

---

## Phase B dependencies on this doc

1. `src/agent_lab/plugin_discovery.py` — `discover_all(workspace) -> AgentPluginCatalog`
2. `GET /api/agents/plugins`, `GET /api/commands`
3. [PluginPanel](../web/src/components/) + [ChatComposer](../web/src/components/ChatComposer.tsx) slash menu
4. Tests: `tests/test_plugin_discovery.py` (mock CLI output fixtures)

---

## Spike checklist (Phase A done)

- [x] Claude `mcp list` / `plugin list` / skill paths documented
- [x] Codex `plugin list` / `mcp list` documented
- [x] Cursor gap documented (implicit IDE only)
- [x] Pass-through flags identified per agent
- [x] cwd/skill discovery pitfall recorded
- [x] Runnable spike: `python scripts/discover_agent_plugins.py` (JSON stdout)
- [ ] Live Room turn log sample with MCP activity (optional manual follow-up)
