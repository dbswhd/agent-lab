import { useCallback, useReducer, useSyncExternalStore } from "react";
import {
  getSessionRunSnapshot,
  subscribeSessionRun,
  updateSessionRun,
  type LiveMsg,
  type SessionRunSnapshot,
} from "../run/runSessionRegistry";

const EMPTY: SessionRunSnapshot = {
  sessionId: "",
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

export function useSessionRunState(sessionId: string | null) {
  const subscribe = useCallback(
    (onStoreChange: () => void) =>
      sessionId ? subscribeSessionRun(sessionId, onStoreChange) : () => {},
    [sessionId],
  );

  const getSnapshot = useCallback(
    () => (sessionId ? getSessionRunSnapshot(sessionId) : EMPTY),
    [sessionId],
  );

  const snap = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const [, bump] = useReducer((n: number) => n + 1, 0);

  const setRunning = useCallback(
    (running: boolean) => {
      if (!sessionId) return;
      updateSessionRun(sessionId, { running });
    },
    [sessionId],
  );

  const setRunBusy = useCallback(
    (runBusy: boolean) => {
      if (!sessionId) return;
      updateSessionRun(sessionId, { runBusy });
    },
    [sessionId],
  );

  const setSynthesizing = useCallback(
    (synthesizing: boolean) => {
      if (!sessionId) return;
      updateSessionRun(sessionId, { synthesizing });
    },
    [sessionId],
  );

  const setMessages = useCallback(
    (updater: LiveMsg[] | ((prev: LiveMsg[]) => LiveMsg[])) => {
      if (!sessionId) return;
      updateSessionRun(sessionId, (prev) => ({
        messages:
          typeof updater === "function" ? updater(prev.messages) : updater,
      }));
    },
    [sessionId],
  );

  const setTurnMessages = useCallback(
    (updater: LiveMsg[] | ((prev: LiveMsg[]) => LiveMsg[])) => {
      if (!sessionId) return;
      updateSessionRun(sessionId, (prev) => ({
        turnMessages:
          typeof updater === "function" ? updater(prev.turnMessages) : updater,
      }));
    },
    [sessionId],
  );

  const setTopologyDone = useCallback(
    (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => {
      if (!sessionId) return;
      updateSessionRun(sessionId, (prev) => ({
        topologyDone:
          typeof updater === "function" ? updater(prev.topologyDone) : updater,
      }));
    },
    [sessionId],
  );

  const setTopologyActive = useCallback(
    (active: SessionRunSnapshot["topologyActive"] | null) => {
      if (!sessionId) return;
      updateSessionRun(sessionId, { topologyActive: active });
    },
    [sessionId],
  );

  return {
    messages: snap.messages,
    turnMessages: snap.turnMessages,
    running: snap.running,
    runBusy: snap.runBusy,
    synthesizing: snap.synthesizing,
    localSseRun: snap.localSseRun,
    runStartedAt: snap.runStartedAt,
    topologyDone: snap.topologyDone,
    topologyActive: snap.topologyActive,
    backgroundRun: snap.backgroundRun,
    setRunning,
    setRunBusy,
    setSynthesizing,
    setMessages,
    setTurnMessages,
    setTopologyDone,
    setTopologyActive,
    bump,
  };
}
