import type { ChatMessage } from "../utils/transcript";
import { inferRunStateFromLiveLog } from "../utils/liveRoomLog";
import { mergeTurnItemsIntoMessages } from "../utils/sessionChatMerge";

export type LiveMsg = ChatMessage & { typing?: boolean };

export type BackgroundRunInfo = {
  runKind: string;
  label: string;
};

export type SessionRunSnapshot = {
  sessionId: string;
  messages: LiveMsg[];
  turnMessages: LiveMsg[];
  running: boolean;
  runBusy: boolean;
  synthesizing: boolean;
  topologyDone: Set<string>;
  topologyActive: { agent: string; round: number } | null;
  /** Server-held run lock while local SSE is idle (mission/execute/retry/orphan). */
  backgroundRun: BackgroundRunInfo | null;
  /** Local Room SSE turn — survives transient gaps before the run lock is held. */
  localSseRun: boolean;
  /** Wall-clock start of the current turn (for Worked-for duration across remounts). */
  runStartedAt: number | null;
};

const PENDING_KEY = "__pending__";

const registry = new Map<string, SessionRunSnapshot>();
const sessionListeners = new Map<string, Set<() => void>>();
const globalListeners = new Set<() => void>();

function emptySnapshot(sessionId: string): SessionRunSnapshot {
  return {
    sessionId,
    messages: [],
    turnMessages: [],
    running: false,
    runBusy: false,
    synthesizing: false,
    topologyDone: new Set(),
    topologyActive: null,
    backgroundRun: null,
    localSseRun: false,
    runStartedAt: null,
  };
}

function notifySession(sessionId: string) {
  sessionListeners.get(sessionId)?.forEach((fn) => fn());
  globalListeners.forEach((fn) => fn());
}

export function getSessionRunSnapshot(sessionId: string): SessionRunSnapshot {
  let snap = registry.get(sessionId);
  if (!snap) {
    snap = emptySnapshot(sessionId);
    registry.set(sessionId, snap);
  }
  return snap;
}

export function subscribeSessionRun(
  sessionId: string | null,
  listener: () => void,
): () => void {
  if (!sessionId) return () => {};
  let set = sessionListeners.get(sessionId);
  if (!set) {
    set = new Set();
    sessionListeners.set(sessionId, set);
  }
  set.add(listener);
  return () => {
    set!.delete(listener);
    if (set!.size === 0) sessionListeners.delete(sessionId);
  };
}

export function subscribeAllSessionRuns(listener: () => void): () => void {
  globalListeners.add(listener);
  return () => globalListeners.delete(listener);
}

export function getRunningSessionIds(): string[] {
  return [...registry.entries()]
    .filter(([, s]) => s.running || s.runBusy)
    .map(([id]) => id)
    .filter((id) => id !== PENDING_KEY);
}

export function isSessionRunActive(sessionId: string): boolean {
  const snap = registry.get(sessionId);
  return Boolean(
    snap?.running || snap?.runBusy || snap?.backgroundRun || snap?.localSseRun,
  );
}

export function clearAllBackgroundRuns(): void {
  for (const [id, snap] of registry.entries()) {
    if (snap.backgroundRun) {
      registry.set(id, { ...snap, backgroundRun: null });
      notifySession(id);
    }
  }
}

export function syncSessionFromServerLock(
  lock: {
    locked: boolean;
    session_id?: string | null;
    run_kind?: string | null;
    label?: string | null;
  } | null,
): void {
  if (!lock?.locked) {
    clearAllBackgroundRuns();
    for (const [id] of registry.entries()) {
      clearOrphanedRunState(id);
    }
    return;
  }
  const sid = lock.session_id?.trim();
  if (!sid) return;
  const snap = getSessionRunSnapshot(sid);
  if (snap.running || snap.runBusy || snap.synthesizing) {
    if (snap.backgroundRun) {
      updateSessionRun(sid, { backgroundRun: null });
    }
    return;
  }
  const next: BackgroundRunInfo = {
    runKind: String(lock.run_kind ?? "room"),
    label: String(lock.label ?? "Running"),
  };
  const prev = snap.backgroundRun;
  if (
    prev?.runKind === next.runKind &&
    prev?.label === next.label &&
    !snap.running &&
    !snap.runBusy
  ) {
    return;
  }
  updateSessionRun(sid, {
    backgroundRun: next,
    running: true,
    runBusy: true,
  });
}

/** Optimistic UI before run-lock poll catches up (execute / retry). */
export function markBackgroundRun(
  sessionId: string,
  info: BackgroundRunInfo,
): void {
  updateSessionRun(sessionId, {
    running: true,
    runBusy: true,
    backgroundRun: info,
  });
}

/** Clear client background run; optional kind avoids clobbering another path. */
export function clearBackgroundRun(
  sessionId: string,
  runKind?: string,
): void {
  updateSessionRun(sessionId, (snap) => {
    if (runKind && snap.backgroundRun?.runKind !== runKind) {
      return {};
    }
    if (!snap.backgroundRun && snap.messages.some((m) => m.typing)) {
      return {};
    }
    return {
      running: false,
      runBusy: false,
      backgroundRun: null,
    };
  });
}

export function updateSessionRun(
  sessionId: string,
  patch:
    | Partial<SessionRunSnapshot>
    | ((snap: SessionRunSnapshot) => Partial<SessionRunSnapshot>),
): SessionRunSnapshot {
  const current = getSessionRunSnapshot(sessionId);
  const delta = typeof patch === "function" ? patch(current) : patch;
  const next: SessionRunSnapshot = {
    ...current,
    ...delta,
    sessionId,
    topologyDone: delta.topologyDone ?? current.topologyDone,
  };
  registry.set(sessionId, next);
  notifySession(sessionId);
  return next;
}

export function migratePendingSessionRun(realSessionId: string): void {
  const pending = registry.get(PENDING_KEY);
  if (!pending) return;
  const existing = registry.get(realSessionId);
  if (existing && (existing.messages.length > 0 || existing.running)) {
    registry.delete(PENDING_KEY);
    notifySession(PENDING_KEY);
    return;
  }
  registry.set(realSessionId, { ...pending, sessionId: realSessionId });
  registry.delete(PENDING_KEY);
  const pendingListeners = sessionListeners.get(PENDING_KEY);
  if (pendingListeners) {
    sessionListeners.delete(PENDING_KEY);
    let realSet = sessionListeners.get(realSessionId);
    if (!realSet) {
      realSet = new Set();
      sessionListeners.set(realSessionId, realSet);
    }
    pendingListeners.forEach((fn) => realSet!.add(fn));
  }
  notifySession(PENDING_KEY);
  notifySession(realSessionId);
}

export function resolveRunSessionKey(
  sessionId: string | null,
  activeSessionId: string | null,
): string {
  return activeSessionId ?? sessionId ?? PENDING_KEY;
}

export function patchSessionMessages(
  sessionKey: string,
  updater: (messages: LiveMsg[]) => LiveMsg[],
  options?: { alsoTurn?: boolean },
): void {
  updateSessionRun(sessionKey, (snap) => {
    const messages = updater(snap.messages);
    const turnMessages = options?.alsoTurn
      ? updater(snap.turnMessages)
      : snap.turnMessages;
    return { messages, turnMessages };
  });
}

export function appendSessionMessages(
  sessionKey: string,
  items: LiveMsg[],
  options?: { alsoTurn?: boolean },
): void {
  patchSessionMessages(sessionKey, (m) => [...m, ...items], options);
}

export function resetTurnRun(sessionKey: string, userMsg: LiveMsg): void {
  const startedAt = Date.now();
  updateSessionRun(sessionKey, (snap) => ({
    messages: [...snap.messages, userMsg],
    turnMessages: [userMsg],
    topologyDone: new Set(),
    topologyActive: null,
    running: true,
    runBusy: true,
    backgroundRun: null,
    localSseRun: true,
    runStartedAt: startedAt,
  }));
}

/** Restore running UI after refresh when live.jsonl still has open agent turns. */
export function syncRunStateFromLiveLog(
  sessionId: string,
  liveLog: Array<Record<string, unknown>> | undefined,
): void {
  if (!liveLog?.length) return;
  const snap = getSessionRunSnapshot(sessionId);
  if (snap.localSseRun && snap.running) return;
  const { inFlight, runStartedAt } = inferRunStateFromLiveLog(liveLog);
  if (!inFlight) return;
  updateSessionRun(sessionId, {
    running: true,
    runBusy: true,
    localSseRun: true,
    runStartedAt: runStartedAt ?? snap.runStartedAt ?? Date.now(),
  });
}

export function findAgentTurnMessage(
  msgs: LiveMsg[],
  agentId: string,
  round: number,
): LiveMsg | undefined {
  const tid = `typing-${agentId}-r${round}`;
  return (
    msgs.find((m) => m.id === tid) ??
    msgs.find(
      (m) =>
        m.role === agentId &&
        (m.parallelRound ?? 1) === round &&
        (m.typing || m.id.startsWith("typing-") || m.id.startsWith("cancel-")),
    )
  );
}

function finalizeTypingAsCancelled(msgs: LiveMsg[]): LiveMsg[] {
  return msgs.flatMap((m) => {
    if (!m.typing) return [m];
    const partial = (m.body ?? "").trim();
    const hasTurnItems = (m.turnItems?.length ?? 0) > 0;
    if (!partial && !hasTurnItems) return [];
    return [
      {
        ...m,
        typing: false,
        body: partial ? `${partial}\n\n_(취소됨)_` : "_(취소됨)_",
      },
    ];
  });
}

/** Drop or finalize typing shells when the server run is no longer active. */
export function stripStaleTypingMessages(msgs: LiveMsg[]): LiveMsg[] {
  return msgs.flatMap((m) => {
    if (!m.typing) return [m];
    const partial = (m.body ?? "").trim();
    const hasTurnItems = (m.turnItems?.length ?? 0) > 0;
    if (!partial && !hasTurnItems) return [];
    return [{ ...m, typing: false }];
  });
}

function clearOrphanedRunState(sessionId: string): void {
  updateSessionRun(sessionId, (snap) => {
    if (!snap.running && !snap.runBusy && !snap.backgroundRun) return {};
    if (snap.localSseRun) return {};
    return {
      messages: stripStaleTypingMessages(snap.messages),
      turnMessages: stripStaleTypingMessages(snap.turnMessages),
      running: false,
      runBusy: false,
      synthesizing: false,
      topologyActive: null,
      backgroundRun: null,
    };
  });
}

/** User stop: keep streamed partials, drop empty typing shells. */
export function finalizeCancelledTyping(sessionKey: string): void {
  updateSessionRun(sessionKey, (snap) => ({
    messages: finalizeTypingAsCancelled(snap.messages),
    turnMessages: finalizeTypingAsCancelled(snap.turnMessages),
    running: false,
    runBusy: false,
    synthesizing: false,
    topologyActive: null,
    backgroundRun: null,
    localSseRun: false,
    runStartedAt: null,
  }));
}

export function finishSessionRun(
  sessionKey: string,
  realSessionId?: string,
): void {
  const key =
    realSessionId && realSessionId !== sessionKey ? realSessionId : sessionKey;
  if (realSessionId && realSessionId !== sessionKey) {
    migratePendingSessionRun(realSessionId);
  }
  updateSessionRun(key, (snap) => ({
    messages: snap.messages.filter((x) => !x.typing),
    turnMessages: snap.turnMessages.filter((x) => !x.typing),
    running: false,
    runBusy: false,
    synthesizing: false,
    topologyActive: null,
    backgroundRun: null,
    localSseRun: false,
    runStartedAt: null,
  }));
}

export function hydrateSessionMessages(
  sessionId: string,
  messages: LiveMsg[],
): void {
  const snap = getSessionRunSnapshot(sessionId);
  if (isSessionRunActive(sessionId) && snap.messages.length > 0) return;
  const runActive = isSessionRunActive(sessionId);
  const stripped = runActive ? messages : stripStaleTypingMessages(messages);
  const finalized = runActive
    ? messages
    : mergeTurnItemsIntoMessages(stripped, snap.messages);
  updateSessionRun(sessionId, {
    messages: finalized,
    turnMessages: runActive ? snap.turnMessages : [],
  });
}

export { PENDING_KEY };
