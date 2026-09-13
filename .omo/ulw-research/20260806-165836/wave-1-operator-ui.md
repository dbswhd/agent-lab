# Wave 1 — operator UI

- `microsoft/Magentic-UI@d3c9d13…`: best decision model with approve/deny/alternative and user/auto/policy provenance.
- `assistant-ui@e70da91…`: best composable Room visual primitives and `requires-action` mapping; not an authorization backend.
- CopilotKit/AG-UI provides headless interrupt wiring; Chainlit supplies minimal ask/edit cards; Open WebUI supplies artifact/security lessons.
- No UI candidate should become the authoritative gate; Agent Lab Human Inbox remains SSOT.
- Sources: [Magentic approval model](https://github.com/microsoft/Magentic-UI/blob/d3c9d13c39288257286a66daabf7c5b5fb72ee69/src/magentic_ui/approval.py#L1-L46), [assistant-ui A2A state mapping](https://github.com/assistant-ui/assistant-ui/blob/e70da91866a5ac880472fbcf23039909270f7623/packages/react-a2a/src/conversions.ts#L60-L97), [CopilotKit HITL](https://docs.copilotkit.ai/agent-spec/human-in-the-loop/useInterrupt).

## EXPAND
- LEAD: Cloudflare durable tool approval — WHY: runtime rather than display semantics — ANGLE: source and failure recovery.
- LEAD: nested approval issue — WHY: Room subagent correctness — ANGLE: OpenAI Agents JS issue #680.

