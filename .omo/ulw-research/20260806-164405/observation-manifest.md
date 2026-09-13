# Observation manifest

| observation_id | source | layer | group | independence | observer | observed_at | valid_at | artifact | anchor | contamination |
|---|---|---|---|---|---|---|---|---|---|---|
| O1 | .agent-lab/PROJECT.md | local SSOT | agent-lab | codebase | root | 2026-08-06 | 2026-07 | local | architecture one-liner | none |
| O2 | docs/NORTH-STAR.md | local roadmap | agent-lab | design doc | root | 2026-08-06 | 2026-07 | local | sections 0, 2.5 | aspirational rows separated from shipped |
| O3 | docs/EXTERNAL-REFS-TRACEABILITY.md | local traceability | agent-lab | shipped matrix | root | 2026-08-06 | 2026-08-06 | local | shipped and future sections | docs may lag code |
| O4 | https://modelcontextprotocol.io/specification/2026-07-28 | primary spec | MCP | standards body | root | 2026-08-06 | 2026-07-28 | web | stateless core, extensions | current |
| O5 | https://agentclientprotocol.com/updates | primary docs | ACP | standards project | root | 2026-08-06 | 2026-07 | web | v1/session lifecycle | v2 still evolving |
| O6 | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | primary engineering | eval | Anthropic | root | 2026-08-06 | 2026-01 | web | trajectory/outcome/harness | vendor perspective |
| O7 | https://github.com/anthropics/cwc-long-running-agents/tree/ad107a974bced5244f74dd283dbf2bfd3baee3a1 | pinned repo | long-run harness | Anthropic | root | 2026-08-06 | commit SHA | temp clone | default-fail/fresh evaluator | demo, not maintained |
| O8 | https://github.com/eth-medical-ai-lab/agent-gui/tree/94456371f251258ee8801292ca5c0583153af29e | pinned repo | operator UX | ETH | root | 2026-08-06 | commit SHA | temp clone | trajectory/steering UI | young project |
| O9 | https://github.com/strongdm/attractor/tree/fb57a55ed97372a27ac90102f436947e29f48426 | pinned repo | loop spec | StrongDM | root | 2026-08-06 | commit SHA | temp clone | programmable events/steer | NLSpec, no release |
| O10 | https://github.com/langchain-ai/open-swe/tree/52597446e63c621c61ca919ede81313c74b0f9b6 | pinned repo | async coding | LangChain | root | 2026-08-06 | commit SHA | temp clone | sandbox/middleware/triggers | prompt-driven validation |
| O11 | https://github.com/agentclientprotocol/agent-client-protocol/tree/e7846aa3e3755455050b03468d07e6124618da79 | pinned repo | protocol | ACP | root | 2026-08-06 | commit SHA | temp clone | schema/changelog | remote transport draft |
| O12 | https://github.com/a2ui-project/a2ui/tree/72fd6b3bd203602814d5cff9b6f85f157ab4e7fa | pinned repo | generative UI | A2UI | root | 2026-08-06 | commit SHA | temp clone | declarative catalog | v1 candidate |
| O13 | pyproject.toml | local dependency | agent-lab | code | root | 2026-08-06 | current | local | mcp>=1,<2 | no lockfile found |
| O14 | local .venv | installed runtime | agent-lab | environment | root | 2026-08-06 | current | command output | mcp 1.27.2 | local machine only |
| O15 | src/agent_lab/core/events.py + session/score.py | local code | agent-lab | code | root | 2026-08-06 | current | local | coarse runtime events, outcome KPIs | not a defect claim |
| O16 | https://a2a-protocol.org/latest/specification/ | primary spec | A2A | Linux Foundation project | root | 2026-08-06 | v1 | web | agent cards/tasks | current |
| O17 | https://docs.ag-ui.com/introduction | primary docs | AG-UI | protocol project | root | 2026-08-06 | current | web | event-based agent UI | overlaps A2UI transport |
| O18 | https://www.anthropic.com/engineering/how-we-contain-claude | primary engineering | safety | Anthropic | root | 2026-08-06 | 2026-06 | web | approval fatigue/containment | vendor telemetry |
| O19 | https://cursor.com/blog/agent-autonomy-auto-review | primary engineering | safety | Cursor | root | 2026-08-06 | 2026-06 | web | risk dial | product-specific |
| O20 | https://agentclientprotocol.com/rfds/streamable-http-websocket-transport | primary RFD | ACP | standards project | root | 2026-08-06 | draft 2026 | web | remote transport | draft |
