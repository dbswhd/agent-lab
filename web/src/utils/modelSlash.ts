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

const PENDING_ROOM_MODELS_KEY = "agent-lab:pending-room-models";

function pendingModelsStore(): Storage | null {
  try {
    return typeof sessionStorage !== "undefined" ? sessionStorage : null;
  } catch {
    return null;
  }
}

/** Pre-session "이번 세션만" composition — survives refresh until first bind. */
export function readPendingRoomModels(): string[] | null {
  const store = pendingModelsStore();
  if (!store) return null;
  try {
    const raw = store.getItem(PENDING_ROOM_MODELS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return null;
    const ids = parsed.map((id) => String(id).trim()).filter(Boolean);
    return ids.length > 0 ? sortAgentIds(ids) : null;
  } catch {
    return null;
  }
}

export function writePendingRoomModels(composition: string[] | null): void {
  const store = pendingModelsStore();
  if (!store) return;
  if (!composition?.length) {
    store.removeItem(PENDING_ROOM_MODELS_KEY);
    return;
  }
  store.setItem(
    PENDING_ROOM_MODELS_KEY,
    JSON.stringify(sortAgentIds(composition)),
  );
}
