import type { AgentHealthRow, AgentOption } from "../api/client";

export function healthToAgentOptions(agents: AgentHealthRow[]): AgentOption[] {
  return agents.map((a) => ({
    id: a.id,
    label: a.label,
    ready: a.ready,
    model: a.model,
  }));
}
