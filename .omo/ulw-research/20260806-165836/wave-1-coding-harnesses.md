# Wave 1 — coding harnesses

- `SWE-agent@3ea751c…`: strongest trajectory/retry/reviewer pattern; benchmark-specific `.traj` and environment coupling must not become product state.
- `Aider@5dc9490…`: commit-before/after, read-only files, lint/test hooks; edits host repo directly and auto-test defaults false.
- `aaif-goose/goose@dafdbb7…`: per-tool permission categories and event hooks; permission is not isolation.
- `OpenHands@5663869…`: sandbox/event/condenser architecture is strong, but large dependency surface.
- Continue is better as IDE/MCP/context reference than a single harness loop.
- Sources: [SWE-agent run/retry](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/agent/agents.py#L357-L404), [Aider coder controls](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py#L277-L320), [Goose agent permissions](https://github.com/aaif-goose/goose/blob/dafdbb7364cb8f145a71e2fd4e080136e225ad14/crates/goose/src/agents/agent.rs#L31-L44), [OpenHands condenser](https://docs.openhands.dev/sdk/arch/condenser).

## EXPAND
- LEAD: Cline shared session runtime — WHY: typed event and approval contract — ANGLE: source deep-dive.
- LEAD: Pydantic AI Harness — WHY: new composable hook layer — ANGLE: maturity and lifecycle implementation.

