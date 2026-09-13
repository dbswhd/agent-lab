# Wave 1 — IDE/terminal adapters

- `cline/cline@81cce3d…`: shared typed session events, explicit approvals, lazy resume/hydration, provider registry. Best event-spine/client adapter reference.
- `sst/opencode@f6c5afe…`: event bus + versioned message schema + timeline hydration; distinguish from older Go `opencode-ai/opencode`.
- Goose has strong streaming buffer and recorded provider scenarios; Continue has useful MCP lifecycle and transform pipelines but a process-global manager is unsuitable for multi-room state.
- Sources: [Cline session events](https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/session-events.ts), [Cline approvals](https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/interactive/approvals.ts), [OpenCode bus](https://github.com/sst/opencode/blob/f6c5afe5a960a252177c1c7ddc280706fd85b7b0/packages/opencode/src/bus/bus-event.ts), [Goose stream buffer](https://github.com/block/goose/blob/dafdbb7364cb8f145a71e2fd4e080136e225ad14/crates/goose-cli/src/session/streaming_buffer.rs), [Continue MCP](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/context/mcp/MCPConnection.ts).

## EXPAND
- LEAD: Cline event/approval tests — WHY: verify replay and non-TTY fail-closed — ANGLE: clone.
- LEAD: OpenCode parent/child session lineage — WHY: subagent visibility — ANGLE: schema/tests.

