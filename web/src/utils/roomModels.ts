import type { AgentOption } from "../api/client";

/** Display order: Claude → Codex → Cursor */
export const ROOM_MODEL_AGENT_ORDER = ["claude", "codex", "cursor"] as const;

export function formatRoomModelLine(agents: AgentOption[]): string {
  const byId = new Map(agents.map((a) => [a.id, a]));
  return ROOM_MODEL_AGENT_ORDER.map((id) => {
    const agent = byId.get(id);
    if (!agent?.model) return null;
    return `${agent.label} ${agent.model}`;
  })
    .filter(Boolean)
    .join(" · ");
}
