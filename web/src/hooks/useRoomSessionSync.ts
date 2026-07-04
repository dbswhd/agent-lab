import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import {
  fetchReadiness,
  fetchSessionTasks,
  runRoomSlash,
  type AgentHealthRow,
  type AgentOption,
  type ReadinessResponse,
  type RoomTasksPayload,
  type SessionDetail,
} from "../api/client";
import type { PendingFile } from "../components/ChatComposer";
import { useSessionRunState } from "./useSessionRunState";
import {
  PENDING_KEY,
  hydrateSessionMessages,
  getSessionRunSnapshot,
  isSessionRunActive,
  syncRunStateFromLiveLog,
} from "../run/runSessionRegistry";
import { preferRicherChatMessages } from "../utils/sessionChatMerge";
import { syncSessionActivityMarkers } from "../utils/transcriptActivity";
import {
  chatFingerprint,
  sessionToMessages,
} from "../utils/roomSessionMessages";
import { sortAgentIds } from "../utils/agentOrder";
import { writePendingRoomModels } from "../utils/modelSlash";

export type UseRoomSessionSyncOptions = {
  sessionId: string | null;
  session: SessionDetail | null;
  loading?: boolean;
  selected: string[];
  agents: AgentOption[];
  healthAgents: AgentHealthRow[];
  teamHealthAgents: AgentHealthRow[];
  bootstrapAgentIds?: string[] | null;
  bootstrapTopic?: string | null;
  onBootstrapAgentsApplied?: () => void;
  onSessionChange: (sessionId: string) => void | Promise<void>;
  onSessionMetaRefresh?: (sessionId: string) => void | Promise<void>;
  setSelected: Dispatch<SetStateAction<string[]>>;
  setText: Dispatch<SetStateAction<string>>;
  setPendingFiles: Dispatch<SetStateAction<PendingFile[]>>;
};

/** Session identity, chat/plan hydration, tasks/readiness, and meta refresh (F9 slice 4a). */
export function useRoomSessionSync({
  sessionId,
  session,
  loading,
  selected,
  agents,
  healthAgents,
  teamHealthAgents,
  bootstrapAgentIds,
  bootstrapTopic,
  onBootstrapAgentsApplied,
  onSessionChange,
  onSessionMetaRefresh,
  setSelected,
  setText,
  setPendingFiles,
}: UseRoomSessionSyncOptions) {
  const [liveRunSessionKey, setLiveRunSessionKey] = useState<string | null>(
    null,
  );
  const runSessionKey = sessionId ?? liveRunSessionKey ?? PENDING_KEY;
  const {
    messages,
    running,
    runBusy,
    synthesizing,
    localSseRun,
    runStartedAt,
    topologyActive,
    topologyDone,
    setSynthesizing,
  } = useSessionRunState(runSessionKey);
  const activeSessionIdRef = useRef<string | null>(sessionId);
  const navigatedToSessionRef = useRef(false);
  const syncedChatRef = useRef("");
  const prevSessionIdRef = useRef<string | null>(sessionId);
  const pendingSessionRoomModelsRef = useRef<string[] | null>(null);
  const agentsPickerInitRef = useRef(false);
  const refreshCommandsRef = useRef<(sid?: string | null) => void>(() => {});

  const [roomTasks, setRoomTasks] = useState<RoomTasksPayload | null>(null);
  const [planMd, setPlanMd] = useState("");
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);

  const isNew = !sessionId;
  const waitingForSession = Boolean(sessionId && !session && loading);
  const sessionReviewMode = Boolean(
    (session?.run?.last_turn as { review_mode?: boolean } | undefined)
      ?.review_mode,
  );

  useEffect(() => {
    activeSessionIdRef.current = sessionId;
    if (sessionId !== null) {
      setLiveRunSessionKey(null);
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) {
      setReadiness(null);
      return;
    }
    if (running || runBusy || synthesizing) {
      return;
    }
    let cancelled = false;
    void fetchReadiness(sessionId, true)
      .then((payload) => {
        if (!cancelled) setReadiness(payload);
      })
      .catch(() => {
        if (!cancelled) setReadiness(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, selected.join(","), running, runBusy, synthesizing]);

  const effectiveSessionId = useCallback((): string | null => {
    return sessionId ?? activeSessionIdRef.current;
  }, [sessionId]);

  const refreshTasks = useCallback(
    (overrideId?: string | null) => {
      const sid = overrideId ?? sessionId ?? activeSessionIdRef.current;
      if (!sid) {
        setRoomTasks(null);
        return;
      }
      void fetchSessionTasks(sid)
        .then(setRoomTasks)
        .catch(() => setRoomTasks(null));
    },
    [sessionId],
  );

  const refreshSessionMeta = useCallback(() => {
    const sid = effectiveSessionId();
    if (!sid) return;
    if (onSessionMetaRefresh) {
      void onSessionMetaRefresh(sid);
    } else {
      void onSessionChange(sid);
    }
    refreshTasks(sid);
    refreshCommandsRef.current(sid);
  }, [effectiveSessionId, onSessionMetaRefresh, onSessionChange, refreshTasks]);

  const persistPendingSessionRoomModels = useCallback(
    async (boundSessionId: string) => {
      const pending = pendingSessionRoomModelsRef.current;
      if (!pending?.length) return;
      pendingSessionRoomModelsRef.current = null;
      writePendingRoomModels(null);
      try {
        await runRoomSlash(
          `/model ${pending.join(",")} session`,
          boundSessionId,
        );
      } catch {
        pendingSessionRoomModelsRef.current = pending;
        writePendingRoomModels(pending);
      }
    },
    [],
  );

  useEffect(() => {
    refreshTasks();
  }, [
    refreshTasks,
    (session?.run?.artifacts as unknown[] | undefined)?.length,
    session?.run?.status,
    session?.chat?.length,
  ]);

  useEffect(() => {
    const rosterPool =
      teamHealthAgents.length > 0
        ? teamHealthAgents
        : healthAgents.length > 0
          ? healthAgents
          : agents;
    const ready = rosterPool.filter((a) => a.ready).map((a) => a.id);
    const known = new Set([
      ...rosterPool.map((a) => a.id),
      ...agents.map((a) => a.id),
    ]);
    if (ready.length === 0 && known.size === 0) return;
    setSelected((prev) => {
      const pending = pendingSessionRoomModelsRef.current;
      if (pending?.length) {
        const next = sortAgentIds(pending);
        return prev.join(",") === next.join(",") ? prev : next;
      }
      if (bootstrapAgentIds?.length) {
        const picked = sortAgentIds(bootstrapAgentIds);
        if (picked.length > 0) return picked;
      }
      if (!agentsPickerInitRef.current || prev.length === 0) {
        agentsPickerInitRef.current = true;
        if (ready.length > 0) return sortAgentIds(ready);
        return prev;
      }
      const kept = sortAgentIds(prev.filter((id) => known.has(id)));
      if (kept.length > 0) return kept;
      if (ready.length > 0) return sortAgentIds(ready);
      return prev;
    });
  }, [agents, bootstrapAgentIds, healthAgents, setSelected, teamHealthAgents]);

  useEffect(() => {
    if (!sessionId && bootstrapAgentIds?.length) {
      onBootstrapAgentsApplied?.();
    }
  }, [sessionId, bootstrapAgentIds, onBootstrapAgentsApplied]);

  useEffect(() => {
    if (sessionId || !bootstrapTopic?.trim()) return;
    setText((prev) => (prev.trim() ? prev : bootstrapTopic));
  }, [bootstrapTopic, sessionId, setText]);

  useEffect(() => {
    const prev = prevSessionIdRef.current;
    prevSessionIdRef.current = sessionId;

    if (prev === sessionId) return;

    if (sessionId === null) {
      setSynthesizing(false);
      return;
    }

    if (prev !== null && prev !== sessionId) {
      syncedChatRef.current = "";
      setPlanMd("");
    }
  }, [sessionId, setSynthesizing]);

  useEffect(() => {
    if (sessionId !== null) return;
    setSynthesizing(false);
    setText("");
    setPendingFiles([]);
  }, [sessionId, setPendingFiles, setSynthesizing, setText]);

  useEffect(() => {
    syncedChatRef.current = "";
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || !session) return;
    const local = getSessionRunSnapshot(sessionId);
    const runActive = isSessionRunActive(sessionId);
    if (runActive && local.messages.length > 0) return;

    const fp = chatFingerprint(session);
    if (fp !== syncedChatRef.current) {
      const serverMsgs = sessionToMessages(session, sessionReviewMode);
      const merged = preferRicherChatMessages(local.messages, serverMsgs);
      syncedChatRef.current = fp;
      hydrateSessionMessages(sessionId, merged);
      syncRunStateFromLiveLog(sessionId, session.live_log);
      syncSessionActivityMarkers(sessionId);
    }
    setPlanMd(session.plan_md || "");
  }, [session, sessionId, sessionReviewMode]);

  useEffect(() => {
    if (!sessionId) return;
    syncSessionActivityMarkers(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (sessionId !== null) return;
    syncedChatRef.current = "";
    setLiveRunSessionKey(null);
    navigatedToSessionRef.current = false;
    if (!isSessionRunActive(PENDING_KEY)) {
      hydrateSessionMessages(PENDING_KEY, []);
    }
    setPlanMd("");
  }, [sessionId]);

  return {
    runSessionKey,
    messages,
    running,
    runBusy,
    synthesizing,
    localSseRun,
    runStartedAt,
    topologyActive,
    topologyDone,
    setSynthesizing,
    liveRunSessionKey,
    setLiveRunSessionKey,
    activeSessionIdRef,
    navigatedToSessionRef,
    pendingSessionRoomModelsRef,
    agentsPickerInitRef,
    refreshCommandsRef,
    roomTasks,
    planMd,
    setPlanMd,
    readiness,
    setReadiness,
    isNew,
    waitingForSession,
    sessionReviewMode,
    refreshTasks,
    refreshSessionMeta,
    persistPendingSessionRoomModels,
    effectiveSessionId,
  };
}

export type RoomSessionSync = ReturnType<typeof useRoomSessionSync>;

/** Wire slash-command refresh into session meta reload (call after useRoomSlashCommands). */
export function bindRoomSessionRefreshCommands(
  ref: MutableRefObject<(sid?: string | null) => void>,
  refreshCommands: (sid?: string | null) => void,
) {
  ref.current = refreshCommands;
}
