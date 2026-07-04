import { useCallback, useEffect, useRef, useState } from "react";
import { useRunningSessionIds } from "./hooks/useRunningSessionIds";
import { useRunLockSync } from "./hooks/useRunLockSync";
import { useTauriFullscreen } from "./hooks/useTauriFullscreen";
import {
  archiveSession,
  deleteSession,
  fetchHealth,
  reconnectClaudeAuth,
  reconnectCursorBridge,
  reconnectKimiWorkBridge,
  fetchSession,
  fetchSessions,
  renameSession,
  unarchiveSession,
  type AgentOption,
  type AgentHealthRow,
  type SessionDetail,
  type SessionSummary,
} from "./api/client";
import { healthToAgentOptions } from "./utils/agentHealthOptions";
import { sortByAgentId } from "./utils/agentOrder";
import { RoomChat } from "./components/RoomChat";
import { SettingsPage } from "./components/SettingsPage";
import { getTurnStrategy } from "./utils/composeMode";
import { SessionRailStatusChip } from "./components/SessionRailStatusChip";
import { SessionList } from "./components/SessionList";
import { SessionRail } from "./components/SessionRail";
import {
  NewSessionDialog,
  type NewSessionParams,
} from "./components/NewSessionDialog";
import { FirstRunOnboarding } from "./components/FirstRunOnboarding";
import { MacNotificationProvider } from "./components/MacNotificationHost";
import { TweaksPanel } from "./components/TweaksPanel";
import { TweaksDemoOverlays } from "./components/TweaksDemoOverlays";
import { TweaksHotkeys } from "./components/TweaksHotkeys";
import { TitlebarSlotsProvider } from "./components/TitlebarSlotsContext";
import { getSidebarOpen, setSidebarOpen } from "./utils/sidebarPrefs";
import { formatRoomModelLine } from "./utils/roomModels";
import { isTauriApp } from "./theme";
import { ensureDesktopNotifyPermission } from "./utils/desktopNotify";
import {
  openCommandPalette,
  requestWorkspaceTabByIndex,
} from "./utils/desktopShortcuts";
import {
  getStoredWorkspaceId,
  getStoredWorkspacePath,
  setStoredWorkspaceId,
  setStoredWorkspacePath,
} from "./utils/sessionSetup";
import {
  clearLastSessionId,
  getLastSessionId,
  setLastSessionId,
} from "./utils/sessionSelectionPrefs";
import {
  getSessionRailWidth,
  setSessionRailWidth,
} from "./utils/sessionRailPrefs";
import {
  getFirstRunOnboardingDismissed,
  setFirstRunOnboardingDismissed as persistFirstRunOnboardingDismissed,
} from "./utils/onboardingPrefs";

type ListTab = "active" | "archived";
type ShellView = "workspace" | "settings";

const ONBOARDING_SAMPLE_TOPIC =
  "Agent Lab 온보딩 샘플: 이 레포의 구조를 5줄로 설명하고, 안전하게 실행 가능한 첫 plan action 하나를 제안해줘.";

export default function App() {
  const [listTab, setListTab] = useState<ListTab>("active");
  const [health, setHealth] = useState("");
  const [healthAgents, setHealthAgents] = useState<AgentHealthRow[]>([]);
  const [teamHealthAgents, setTeamHealthAgents] = useState<AgentHealthRow[]>(
    [],
  );
  const [apiOk, setApiOk] = useState(true);
  const [healthLoading, setHealthLoading] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [sessionsDir, setSessionsDir] = useState<string | null>(null);
  const [bridgeProbeFailed, setBridgeProbeFailed] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    getLastSessionId(),
  );
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [composerNew, setComposerNew] = useState(
    () => getLastSessionId() == null,
  );
  const [newSessionOpen, setNewSessionOpen] = useState(false);
  const [newSessionInitialTopic, setNewSessionInitialTopic] = useState<
    string | null
  >(null);
  const [firstRunOnboardingDismissed, setFirstRunOnboardingDismissedState] =
    useState(() => getFirstRunOnboardingDismissed());
  const [firstRunOnboardingOpen, setFirstRunOnboardingOpen] = useState(false);
  const [firstRunSetupActive, setFirstRunSetupActive] = useState(false);
  const [setupWorkspaceChosen, setSetupWorkspaceChosen] = useState(() =>
    Boolean(getStoredWorkspaceId("") || getStoredWorkspacePath()),
  );
  const [bootstrapAgentIds, setBootstrapAgentIds] = useState<string[] | null>(
    null,
  );
  const [bootstrapTopic, setBootstrapTopic] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpenState] = useState(getSidebarOpen);
  const [sessionRailWidth, setSessionRailWidthState] =
    useState(getSessionRailWidth);
  const [sessionQuery, setSessionQuery] = useState("");
  const [shellView, setShellView] = useState<ShellView>("workspace");

  const openSettings = useCallback((category?: string) => {
    if (category) {
      window.localStorage.setItem("agent-lab.settings-category", category);
    }
    setShellView("settings");
  }, []);

  const runningSessionIds = useRunningSessionIds();
  useRunLockSync(true);

  const toggleSidebar = useCallback(() => {
    setSidebarOpenState((current) => {
      const next = !current;
      setSidebarOpen(next);
      return next;
    });
  }, []);

  const commitSessionRailWidth = useCallback((width: number) => {
    setSessionRailWidthState(width);
    setSessionRailWidth(width);
  }, []);

  const apiOkRef = useRef(true);

  const reloadSessions = useCallback(async () => {
    try {
      const { sessions: list } = await fetchSessions(listTab === "archived");
      setSessions(list);
      setSessionsError(null);
    } catch (e) {
      const msg = String(e);
      setSessionsError(
        msg.includes("Failed to fetch") || msg.includes("Load failed")
          ? "세션 목록 불러오기 실패 — API(8765) 확인"
          : msg,
      );
    }
  }, [listTab]);

  const loadDetailRequestRef = useRef(0);
  const skipNextDetailLoadRef = useRef(false);
  /** Room SSE bound a session id before it appears in the sidebar list. */
  const roomBoundSessionRef = useRef<string | null>(null);

  const loadDetail = useCallback(async (id: string, keepPrevious = false) => {
    const req = ++loadDetailRequestRef.current;
    setLoadingDetail(true);
    setDetail((prev) => {
      if (keepPrevious && prev?.id === id) return prev;
      return null;
    });
    try {
      const next = await fetchSession(id);
      if (req !== loadDetailRequestRef.current) return;
      setDetail(next);
    } catch {
      if (req === loadDetailRequestRef.current) {
        setDetail(null);
      }
    } finally {
      if (req === loadDetailRequestRef.current) {
        setLoadingDetail(false);
      }
    }
  }, []);

  const reloadHealth = useCallback(
    async (probeBridge = false, probePreflight?: boolean): Promise<boolean> => {
      setHealthLoading(true);
      try {
        const sessionForHealth = composerNew ? null : selectedId;
        const preflight = probePreflight ?? probeBridge;
        const h = await fetchHealth(probeBridge, preflight, sessionForHealth);
        const ok = Boolean(h.ok && h.api?.ok !== false);
        setApiOk(ok);
        apiOkRef.current = ok;
        setSessionsDir(
          typeof h.sessions_dir === "string" ? h.sessions_dir : null,
        );
        const rows = sortByAgentId(h.agents_all ?? h.agents ?? []);
        setHealthAgents(rows);
        setTeamHealthAgents(h.agents ?? []);
        const cursor = rows.find((a) => a.id === "cursor");
        setBridgeProbeFailed(
          Boolean(
            probeBridge &&
            cursor &&
            cursor.configured &&
            (cursor.bridge === "error" || !cursor.ready),
          ),
        );
        const opts = healthToAgentOptions(rows);
        setAgents(opts);
        const teamOpts = healthToAgentOptions(sortByAgentId(h.agents ?? []));
        setHealth(
          formatRoomModelLine(teamOpts.length ? teamOpts : opts) || "backend",
        );
        return ok;
      } catch (e) {
        const msg = String(e);
        setApiOk(false);
        apiOkRef.current = false;
        setHealth(
          msg.includes("Load failed") || msg.includes("Failed to fetch")
            ? "API(8765) 연결 실패 — 자동 재연결 중…"
            : msg,
        );
        return false;
      } finally {
        setHealthLoading(false);
      }
    },
    [composerNew, selectedId],
  );

  const handleReconnectCursor = useCallback(async () => {
    setReconnecting(true);
    try {
      await reconnectCursorBridge();
      await reloadHealth(true);
    } catch (e) {
      setHealth(String(e));
    } finally {
      setReconnecting(false);
    }
  }, [reloadHealth]);

  const handleReconnectClaude = useCallback(async () => {
    setReconnecting(true);
    try {
      await reconnectClaudeAuth();
      await reloadHealth(true);
    } catch (e) {
      setHealth(String(e));
    } finally {
      setReconnecting(false);
    }
  }, [reloadHealth]);

  const handleReconnectKimiWork = useCallback(async () => {
    setReconnecting(true);
    try {
      const res = await reconnectKimiWorkBridge();
      await reloadHealth(true);
      if (res.hint) {
        setHealth(res.hint);
      } else if (res.loop_ready === false) {
        setHealth("Kimi Work Loop 검사 실패 — 잠시 후 다시 시도");
      }
    } catch (e) {
      setHealth(String(e));
    } finally {
      setReconnecting(false);
    }
  }, [reloadHealth]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        if (cancelled) return;
        const ok = await reloadHealth(false);
        if (ok) {
          await reloadSessions();
          void reloadHealth(true, false);
          return;
        }
        await new Promise((r) => window.setTimeout(r, 400));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadHealth, reloadSessions]);

  useEffect(() => {
    void reloadHealth(false);
  }, [selectedId, composerNew, reloadHealth]);

  useEffect(() => {
    void ensureDesktopNotifyPermission();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      if (cancelled) return;
      const wasOk = apiOkRef.current;
      const ok = await reloadHealth(false);
      if (ok && !wasOk) {
        await reloadSessions();
      }
      if (cancelled) return;
      timer = window.setTimeout(
        () => void tick(),
        apiOkRef.current ? 45_000 : 5_000,
      );
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [reloadHealth, reloadSessions]);

  useEffect(() => {
    reloadSessions().catch(() => {});
  }, [listTab, reloadSessions]);

  useEffect(() => {
    if (sessions.length === 0) return;
    if (selectedId && sessions.some((s) => s.id === selectedId)) {
      if (roomBoundSessionRef.current === selectedId) {
        roomBoundSessionRef.current = null;
      }
      return;
    }
    if (selectedId && !sessions.some((s) => s.id === selectedId)) {
      if (roomBoundSessionRef.current === selectedId) return;
      clearLastSessionId();
      setSelectedId(null);
      setComposerNew(true);
      setDetail(null);
    }
  }, [sessions, selectedId]);

  useEffect(() => {
    if (skipNextDetailLoadRef.current) {
      skipNextDetailLoadRef.current = false;
      return;
    }
    if (selectedId && !composerNew) loadDetail(selectedId, true);
    else if (composerNew) setDetail(null);
  }, [selectedId, composerNew, loadDetail]);

  const refreshSessionRun = useCallback(async (id: string) => {
    try {
      const next = await fetchSession(id);
      setDetail((prev) => (prev?.id === id ? next : prev));
    } catch {
      /* ignore transient API errors during reload */
    }
  }, []);

  function onRoomSessionChange(sessionId: string) {
    roomBoundSessionRef.current = sessionId;
    skipNextDetailLoadRef.current = true;
    setSelectedId(sessionId);
    setComposerNew(false);
    setLastSessionId(sessionId);
    setListTab("active");
    void reloadSessions();
    void loadDetail(sessionId, true);
  }

  const startNew = useCallback(() => {
    setFirstRunSetupActive(true);
    setNewSessionInitialTopic(null);
    setNewSessionOpen(true);
  }, []);

  const startOnboardingSample = useCallback(() => {
    setFirstRunSetupActive(true);
    setNewSessionInitialTopic(ONBOARDING_SAMPLE_TOPIC);
    setNewSessionOpen(true);
  }, []);

  const dismissFirstRunOnboarding = useCallback(() => {
    persistFirstRunOnboardingDismissed(true);
    setFirstRunOnboardingDismissedState(true);
    setFirstRunOnboardingOpen(false);
  }, []);

  const handleNewSessionCreate = useCallback(
    (params: NewSessionParams) => {
      setStoredWorkspaceId(params.workspaceId);
      setStoredWorkspacePath(params.workspacePath);
      setSetupWorkspaceChosen(true);
      setBootstrapAgentIds(null);
      setBootstrapTopic(params.topic ?? null);
      if (!firstRunOnboardingDismissed) {
        persistFirstRunOnboardingDismissed(true);
        setFirstRunOnboardingDismissedState(true);
      }
      setComposerNew(true);
      setSelectedId(null);
      setDetail(null);
      setListTab("active");
      clearLastSessionId();
      setFirstRunSetupActive(false);
      setFirstRunOnboardingOpen(false);
      setNewSessionInitialTopic(null);
      setNewSessionOpen(false);
      setShellView("workspace");
    },
    [firstRunOnboardingDismissed],
  );

  const clearBootstrapAgents = useCallback(() => {
    setBootstrapAgentIds(null);
    setBootstrapTopic(null);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!event.metaKey || event.altKey) return;
      const key = event.key.toLowerCase();

      if (key === "n") {
        event.preventDefault();
        startNew();
        return;
      }
      if (event.ctrlKey && key === "s") {
        event.preventDefault();
        toggleSidebar();
        return;
      }
      if (key === "k") {
        event.preventDefault();
        openCommandPalette();
        return;
      }
      if (!event.ctrlKey && ["1", "2", "3", "4", "5", "6", "7"].includes(key)) {
        event.preventDefault();
        requestWorkspaceTabByIndex(key);
      }
    }

    window.addEventListener("keydown", onKeyDown, { capture: true });
    return () =>
      window.removeEventListener("keydown", onKeyDown, { capture: true });
  }, [startNew, toggleSidebar]);

  function selectSession(id: string) {
    if (id === selectedId && !composerNew) return;
    skipNextDetailLoadRef.current = true;
    setSelectedId(id);
    setComposerNew(false);
    setLastSessionId(id);
    void loadDetail(id, false);
  }

  async function handleArchive(id: string) {
    await archiveSession(id);
    if (selectedId === id) {
      setSelectedId(null);
      setDetail(null);
      setComposerNew(true);
      clearLastSessionId();
    }
    await reloadSessions();
  }

  async function handleUnarchive(id: string) {
    await unarchiveSession(id);
    await reloadSessions();
    setListTab("active");
  }

  async function handleRename(id: string, topic: string) {
    if (!topic) return;
    await renameSession(id, topic);
    await reloadSessions();
    if (selectedId === id) await loadDetail(id);
  }

  async function handleDelete(id: string) {
    await deleteSession(id);
    if (selectedId === id) {
      setSelectedId(null);
      setDetail(null);
      setComposerNew(true);
      clearLastSessionId();
    }
    await reloadSessions();
  }

  const inTauri = isTauriApp();
  const fullscreen = useTauriFullscreen(inTauri);
  const roomSessionId = composerNew ? null : selectedId;
  const roomSessionDetail =
    roomSessionId && detail?.id === roomSessionId ? detail : null;
  const roomSessionLoading = Boolean(
    roomSessionId &&
    loadingDetail &&
    detail != null &&
    detail.id !== roomSessionId,
  );
  const showFirstRunOnboarding =
    shellView === "workspace" &&
    !newSessionOpen &&
    !firstRunSetupActive &&
    (firstRunOnboardingOpen ||
      (listTab === "active" &&
        sessions.length === 0 &&
        !sessionsError &&
        composerNew &&
        !selectedId &&
        !firstRunOnboardingDismissed));
  return (
    <div
      className={`app${inTauri ? " app--tauri" : ""}${
        fullscreen ? " app--fullscreen" : ""
      }`}
    >
      <MacNotificationProvider>
        <TitlebarSlotsProvider>
          <div
            className={`shell${sidebarOpen ? "" : " shell--rail-collapsed"}`}
            style={
              { "--rail-width": `${sessionRailWidth}px` } as React.CSSProperties
            }
          >
            <SessionRail
              open={sidebarOpen}
              width={sessionRailWidth}
              onWidthChange={setSessionRailWidthState}
              onWidthCommit={commitSessionRailWidth}
            >
              <div className="rail__header">
                <div className="rail__title-row">
                  <h1 className="rail__title">agent lab</h1>
                </div>
                <label className="rail__search">
                  <svg
                    viewBox="0 0 24 24"
                    width="15"
                    height="15"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={1.7}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <circle cx="11" cy="11" r="7" />
                    <path d="m21 21-4.3-4.3" />
                  </svg>
                  <input
                    type="search"
                    value={sessionQuery}
                    onChange={(event) => setSessionQuery(event.target.value)}
                    placeholder="세션 검색"
                    aria-label="세션 검색"
                  />
                </label>
                <div className="rail-scope-tabs" role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={listTab === "active"}
                    className={`rail-scope-tab${listTab === "active" ? " is-active" : ""}`}
                    onClick={() => setListTab("active")}
                  >
                    Sessions
                    {listTab === "active" && sessions.length > 0 ? (
                      <span className="rail-scope-tab__count">
                        {sessions.length}
                      </span>
                    ) : null}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={listTab === "archived"}
                    className={`rail-scope-tab${listTab === "archived" ? " is-active" : ""}`}
                    onClick={() => setListTab("archived")}
                  >
                    Archive
                    {listTab === "archived" && sessions.length > 0 ? (
                      <span className="rail-scope-tab__count rail-scope-tab__count--dim">
                        {sessions.length}
                      </span>
                    ) : null}
                  </button>
                </div>
              </div>
              <SessionRailStatusChip
                apiOk={apiOk}
                agents={teamHealthAgents}
                loading={healthLoading}
                reconnecting={reconnecting}
                probeBridgeFailed={bridgeProbeFailed}
                onRefresh={() => void reloadHealth(true)}
                onReconnectCursor={() => void handleReconnectCursor()}
                onReconnectClaude={() => void handleReconnectClaude()}
                onReconnectKimiWork={() => void handleReconnectKimiWork()}
                onOpenSettings={() => openSettings("agents")}
              />
              {!apiOk && health ? (
                <p className="chat-list-status chat-list-status--error">
                  {health}
                </p>
              ) : null}
              {sessionsError ? (
                <p className="chat-list-status chat-list-status--error">
                  {sessionsError}
                </p>
              ) : null}
              {apiOk &&
              sessions.length === 0 &&
              !sessionsError &&
              sessionsDir ? (
                <p className="chat-list-status" title={sessionsDir}>
                  세션 폴더 비어 있음 · {sessionsDir}
                </p>
              ) : null}
              <SessionList
                sessions={sessions}
                selectedId={!composerNew ? selectedId : null}
                runningSessionIds={runningSessionIds}
                archived={listTab === "archived"}
                query={sessionQuery}
                onSelect={selectSession}
                onArchive={listTab === "active" ? handleArchive : undefined}
                onUnarchive={
                  listTab === "archived" ? handleUnarchive : undefined
                }
                onRename={handleRename}
                onDelete={handleDelete}
              />
              {listTab === "active" ? (
                <div className="rail__footer">
                  <button
                    type="button"
                    className="btn btn--primary btn--block"
                    onClick={startNew}
                    title="새 Session (⌘N)"
                  >
                    + 새 Session
                    <span className="kbd" style={{ marginLeft: "auto" }}>
                      ⌘N
                    </span>
                  </button>
                  <button
                    type="button"
                    className={`icon-btn${shellView === "settings" ? " is-active" : ""}`}
                    title="Settings"
                    aria-label="Settings"
                    onClick={() => openSettings()}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      width="17"
                      height="17"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={1.7}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                    >
                      <circle cx="12" cy="12" r="3" />
                      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                    </svg>
                  </button>
                </div>
              ) : null}
            </SessionRail>

            <div className="workspace-canvas">
              <div className="workspace-tile">
                <section className="pane workspace-pane" aria-label="Workspace">
                  {shellView === "settings" ? (
                    <SettingsPage
                      sessionId={roomSessionId}
                      session={roomSessionDetail}
                      selectedAgents={agents
                        .filter((a) => a.ready)
                        .map((a) => a.id)}
                      turnProfile={getTurnStrategy()}
                      apiOk={apiOk}
                      healthAgents={healthAgents}
                      healthLoading={healthLoading}
                      reconnecting={reconnecting}
                      sessionsDir={sessionsDir}
                      probeBridgeFailed={bridgeProbeFailed}
                      onRefreshDiagnostics={() => void reloadHealth(true)}
                      onReconnectCursor={() => void handleReconnectCursor()}
                      onReconnectClaude={() => void handleReconnectClaude()}
                      onReconnectKimiWork={() => void handleReconnectKimiWork()}
                      onBack={() => setShellView("workspace")}
                    />
                  ) : showFirstRunOnboarding ? (
                    <FirstRunOnboarding
                      apiOk={apiOk}
                      healthText={health}
                      agents={healthAgents}
                      loading={healthLoading}
                      sessionsDir={sessionsDir}
                      hasWorkspace={setupWorkspaceChosen}
                      onRefresh={() => void reloadHealth(true)}
                      onOpenSettings={() => openSettings("agents")}
                      onReconnectCursor={() => void handleReconnectCursor()}
                      onReconnectClaude={() => void handleReconnectClaude()}
                      onChooseWorkspace={startNew}
                      onStartSample={startOnboardingSample}
                      onSkip={dismissFirstRunOnboarding}
                    />
                  ) : (
                    <RoomChat
                      agents={agents}
                      apiOk={apiOk}
                      healthAgents={healthAgents}
                      teamHealthAgents={teamHealthAgents}
                      sessionId={roomSessionId}
                      session={roomSessionDetail}
                      loading={roomSessionLoading}
                      onSessionChange={onRoomSessionChange}
                      onSessionMetaRefresh={refreshSessionRun}
                      sidebarOpen={sidebarOpen}
                      onToggleSidebar={toggleSidebar}
                      onOpenSettings={() => openSettings("agents")}
                      onRefreshHealth={() =>
                        reloadHealth(true).then(() => undefined)
                      }
                      bootstrapAgentIds={bootstrapAgentIds}
                      bootstrapTopic={bootstrapTopic}
                      onBootstrapAgentsApplied={clearBootstrapAgents}
                    />
                  )}
                </section>
              </div>
            </div>
          </div>
        </TitlebarSlotsProvider>
        <NewSessionDialog
          open={newSessionOpen}
          initialTopic={newSessionInitialTopic}
          onClose={() => {
            setFirstRunSetupActive(false);
            setNewSessionInitialTopic(null);
            setNewSessionOpen(false);
          }}
          onCreate={handleNewSessionCreate}
        />
        <TweaksPanel />
        <TweaksDemoOverlays />
        <TweaksHotkeys />
      </MacNotificationProvider>
    </div>
  );
}
