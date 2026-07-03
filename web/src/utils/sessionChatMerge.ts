import type { LiveMsg } from "../run/runSessionRegistry";
import { replayLiveLogToMessages } from "./liveRoomLog";
import { mergeActivityMarkersFromLocal } from "./transcriptActivity";

export function agentTurnKey(role: string, round?: number): string {
  return `${role}:r${round ?? 1}`;
}

/** Merge persisted chat with append-only live.jsonl from an in-flight turn. */
export function mergePersistedChatWithLiveLog(
  chatMsgs: LiveMsg[],
  liveLog: Array<Record<string, unknown>> | undefined,
  labelFor: (agentId: string) => string,
): LiveMsg[] {
  if (!liveLog?.length) return chatMsgs;
  const liveMsgs = replayLiveLogToMessages(liveLog, labelFor);
  if (!liveMsgs.length) return chatMsgs;

  const known = new Set<string>();
  for (const m of chatMsgs) {
    if (m.role === "you") continue;
    if (m.role !== "system") {
      known.add(agentTurnKey(String(m.role), m.parallelRound));
      continue;
    }
    if (m.sourceAgent) {
      known.add(agentTurnKey(String(m.sourceAgent), m.parallelRound));
    }
  }

  const additions = liveMsgs.flatMap((m) => {
    const key = agentTurnKey(String(m.role), m.parallelRound);
    if (known.has(key)) return [];
    const finalized =
      m.typing && (m.body ?? "").trim()
        ? { ...m, typing: false as const }
        : m;
    return [finalized];
  });

  const merged = additions.length ? [...chatMsgs, ...additions] : chatMsgs;
  return mergeTurnItemsIntoMessages(merged, liveMsgs);
}

/**
 * The turn-by-turn tool/thought activity trail only ever lives in the local,
 * live-streamed message (the server transcript persists final text only), so
 * picking the server side as the richer transcript would otherwise erase it
 * from view the moment a completed turn's session data next refreshes.
 */
export function mergeTurnItemsIntoMessages(
  base: LiveMsg[],
  source: LiveMsg[],
): LiveMsg[] {
  const sourceByKey = new Map<string, LiveMsg>();
  for (const m of source) {
    if (!(m.turnItems?.length ?? 0)) continue;
    if (m.role === "you") continue;
    if (m.role === "system" && !m.sourceAgent) continue;
    const key =
      m.role !== "system"
        ? agentTurnKey(String(m.role), m.parallelRound)
        : agentTurnKey(String(m.sourceAgent), m.parallelRound);
    sourceByKey.set(key, m);
  }
  if (!sourceByKey.size) return base;
  let changed = false;
  const next = base.map((m) => {
    if (m.turnItems?.length || m.role === "you") return m;
    if (m.role === "system" && !m.sourceAgent) return m;
    const key =
      m.role !== "system"
        ? agentTurnKey(String(m.role), m.parallelRound)
        : agentTurnKey(String(m.sourceAgent), m.parallelRound);
    const match = sourceByKey.get(key);
    if (!match) return m;
    changed = true;
    return { ...m, turnItems: match.turnItems };
  });
  return changed ? next : base;
}

function mergeTurnItemsFromLocal(base: LiveMsg[], local: LiveMsg[]): LiveMsg[] {
  return mergeTurnItemsIntoMessages(base, local);
}

/** Prefer the richer transcript when server and client counts match. */
export function preferRicherChatMessages(
  local: LiveMsg[],
  server: LiveMsg[],
): LiveMsg[] {
  let base: LiveMsg[];
  if (local.length > server.length) base = local;
  else if (server.length > local.length) base = server;
  else if (!local.length) base = server;
  else {
    const localChars = local.reduce((n, m) => n + (m.body?.length ?? 0), 0);
    const serverChars = server.reduce((n, m) => n + (m.body?.length ?? 0), 0);
    base = serverChars >= localChars ? server : local;
  }
  return mergeActivityMarkersFromLocal(
    mergeTurnItemsFromLocal(base, local),
    local,
  );
}
