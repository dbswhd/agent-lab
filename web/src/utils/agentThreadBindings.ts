const STORAGE_KEY = "agent-lab-agent-thread-bindings";

export type AgentThreadBindings = Record<string, "new" | string>;

export function getStoredAgentThreadBindings(): AgentThreadBindings | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    const out: AgentThreadBindings = {};
    for (const [key, val] of Object.entries(parsed)) {
      if (typeof val !== "string") continue;
      out[key] = val.trim() === "new" ? "new" : val.trim();
    }
    return Object.keys(out).length ? out : null;
  } catch {
    return null;
  }
}

export function setStoredAgentThreadBindings(
  bindings: AgentThreadBindings | null,
): void {
  if (!bindings || Object.keys(bindings).length === 0) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(bindings));
}

export function clearStoredAgentThreadBindings(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function bindingsFromAgentChoices(
  agents: Array<{ id: string; thread: "new" | string }>,
): AgentThreadBindings {
  const out: AgentThreadBindings = {};
  for (const row of agents) {
    out[row.id] = row.thread === "new" ? "new" : row.thread;
  }
  return out;
}
