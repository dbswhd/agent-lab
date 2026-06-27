import { sortAgentIds } from "./agentOrder";

export type ModelSlashScope = "session" | "default";

export function parseModelSlashArgs(args: string): {
  composition: string[];
  scope: ModelSlashScope | null;
} {
  const tokens = args.trim().split(/\s+/).filter(Boolean);
  let scope: ModelSlashScope | null = null;
  const last = tokens[tokens.length - 1];
  if (last === "session" || last === "default") {
    scope = last;
    tokens.pop();
  }
  const composition = tokens
    .join(" ")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean);
  return { composition, scope };
}

export function readSessionRoomModels(
  run: Record<string, unknown> | undefined,
): string[] | null {
  const raw = run?.room_models;
  if (!Array.isArray(raw)) return null;
  const ids = raw.map((id) => String(id).trim()).filter(Boolean);
  return ids.length > 0 ? sortAgentIds(ids) : null;
}
