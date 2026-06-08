import type { ChatMessage } from "../utils/transcript";

export type LiveMsg = ChatMessage & { typing?: boolean };

export type SessionRunSnapshot = {
  sessionId: string;
  messages: LiveMsg[];
  turnMessages: LiveMsg[];
  running: boolean;
  runBusy: boolean;
  synthesizing: boolean;
  topologyDone: Set<string>;
  topologyActive: { agent: string; round: number } | null;
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
  return Boolean(snap?.running || snap?.runBusy);
}

export function updateSessionRun(
  sessionId: string,
  patch: Partial<SessionRunSnapshot> | ((snap: SessionRunSnapshot) => Partial<SessionRunSnapshot>),
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
  patchSessionMessages(
    sessionKey,
    (m) => [...m, ...items],
    options,
  );
}

export function resetTurnRun(sessionKey: string, userMsg: LiveMsg): void {
  updateSessionRun(sessionKey, (snap) => ({
    messages: [...snap.messages, userMsg],
    turnMessages: [userMsg],
    topologyDone: new Set(),
    topologyActive: null,
    running: true,
    runBusy: true,
  }));
}

export function finishSessionRun(
  sessionKey: string,
  realSessionId?: string,
): void {
  const key = realSessionId && realSessionId !== sessionKey ? realSessionId : sessionKey;
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
  }));
}

export function hydrateSessionMessages(
  sessionId: string,
  messages: LiveMsg[],
): void {
  if (isSessionRunActive(sessionId)) return;
  updateSessionRun(sessionId, {
    messages,
    turnMessages: [],
  });
}

export { PENDING_KEY };
