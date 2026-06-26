import type { AgentOption } from "../api/client";

/** Human-readable model name for composer chips and status lines. */
export function formatAgentModelName(
  model?: string | null,
  agentId?: string,
): string {
  const raw = model?.trim();
  if (!raw) {
    if (agentId === "kimi_work") return "Work";
    return "기본 모델";
  }
  if (raw.startsWith("kimi-work:")) {
    const name = raw.slice("kimi-work:".length).trim();
    return name || "Work";
  }
  return raw;
}

export function formatRoomModelLine(agents: AgentOption[]): string {
  return agents
    .map((agent) => {
      const model = formatAgentModelName(agent.model, agent.id);
      if (agent.id === "kimi_work") {
        return model === "Work" ? agent.label : `${agent.label} ${model}`;
      }
      return model === "기본 모델" ? agent.label : `${agent.label} ${model}`;
    })
    .join(" · ");
}
