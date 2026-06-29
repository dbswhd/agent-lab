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

  const known = new Set(
    chatMsgs
      .filter((m) => m.role !== "you" && m.role !== "system")
      .map((m) => agentTurnKey(String(m.role), m.parallelRound)),
  );

  const additions = liveMsgs.flatMap((m) => {
    if (m.typing && !(m.body ?? "").trim() && !(m.turnItems?.length ?? 0)) {
      return [];
    }
    const key = agentTurnKey(String(m.role), m.parallelRound);
    if (known.has(key)) return [];
    const finalized =
      m.typing && (m.body ?? "").trim()
        ? { ...m, typing: false as const }
        : m;
    return [finalized];
  });

  return additions.length ? [...chatMsgs, ...additions] : chatMsgs;
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
  return mergeActivityMarkersFromLocal(base, local);
}
