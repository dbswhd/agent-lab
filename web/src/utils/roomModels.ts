import type { AgentOption } from "../api/client";

export function formatRoomModelLine(agents: AgentOption[]): string {
  return agents
    .map((agent) => (agent.model ? `${agent.label} ${agent.model}` : null))
    .filter(Boolean)
    .join(" · ");
}
