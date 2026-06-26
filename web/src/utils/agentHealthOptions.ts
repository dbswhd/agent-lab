import type { AgentHealthRow, AgentOption } from "../api/client";
import { sortByAgentId } from "./agentOrder";

export function healthToAgentOptions(agents: AgentHealthRow[]): AgentOption[] {
  return sortByAgentId(
    agents.map((a) => ({
      id: a.id,
      label: a.label,
      ready: a.ready,
      model: a.model,
    })),
  );
}
