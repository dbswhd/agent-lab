/** Canonical agent display order (matches backend provider_picker_order). */
export const AGENT_PICKER_ORDER = [
  "cursor",
  "codex",
  "claude",
  "kimi_work",
  "kimi",
  "local",
] as const;

export function sortAgentIds(ids: string[]): string[] {
  const rank: Map<string, number> = new Map(
    AGENT_PICKER_ORDER.map((id, index) => [id, index]),
  );
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const raw of ids) {
    const id = raw.trim().toLowerCase();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    unique.push(id);
  }
  return unique.sort(
    (a, b) => (rank.get(a) ?? rank.size) - (rank.get(b) ?? rank.size),
  );
}

export function sortAgentPickerOptions<T extends { value: string }>(
  options: T[],
): T[] {
  const rank: Map<string, number> = new Map(
    AGENT_PICKER_ORDER.map((id, index) => [id, index]),
  );
  return [...options].sort(
    (a, b) =>
      (rank.get(a.value) ?? rank.size) - (rank.get(b.value) ?? rank.size),
  );
}

export const TURN_MODE_ORDER = ["quick", "team", "loop"] as const;

export function sortByAgentId<T extends { id: string }>(rows: T[]): T[] {
  const rank: Map<string, number> = new Map(
    AGENT_PICKER_ORDER.map((id, index) => [id, index]),
  );
  return [...rows].sort(
    (a, b) => (rank.get(a.id) ?? rank.size) - (rank.get(b.id) ?? rank.size),
  );
}
