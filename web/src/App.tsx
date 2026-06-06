import { useCallback, useEffect, useRef, useState } from "react";
import { useRunningSessionIds } from "./hooks/useRunningSessionIds";
import {
  archiveSession,
  deleteSession,
  fetchBackends,
  fetchHealth,
  reconnectCursorBridge,
  fetchSession,
  fetchSessions,
  renameSession,
  unarchiveSession,
  type AgentOption,
  type AgentHealthRow,
  type BackendOption,
  type SessionDetail,
  type SessionSummary,
} from "./api/client";
import { healthToAgentOptions } from "./components/AgentHealthPanel";
import { RoomChat } from "./components/RoomChat";
import { SettingsPage } from "./components/SettingsPage";
import { getTurnStrategy } from "./utils/composeMode";
import { getEfficiencyMode } from "./utils/efficiencyPrefs";
import { SessionRailStatusChip } from "./components/SessionRailStatusChip";
import { RunPanel } from "./components/RunPanel";
import { SessionList } from "./components/SessionList";
import { SessionRail } from "./components/SessionRail";
import { SessionViewer } from "./components/SessionViewer";
import { MacTitlebar } from "./components/MacTitlebar";
import { MacNotificationProvider } from "./components/MacNotificationHost";
import { getSidebarOpen, setSidebarOpen } from "./utils/sidebarPrefs";
import { formatRoomModelLine } from "./utils/roomModels";
import { isTauriApp } from "./theme";
import { ensureDesktopNotifyPermission } from "./utils/desktopNotify";
import {
  openCommandPalette,
  requestWorkspaceTabByIndex,
} from "./utils/desktopShortcuts";
import {
  clearLastSessionId,
  getLastSessionId,
  setLastSessionId,
} from "./utils/sessionSelectionPrefs";
import {
  getSessionRailWidth,
  setSessionRailWidth,
} from "./utils/sessionRailPrefs";

type Mode = "room" | "classic";
type ListTab = "active" | "archived";
type ShellView = "workspace" | "settings";

export default function App() {
  const [mode, setMode] = useState<Mode>("room");
  const [listTab, setListTab] = useState<ListTab>("active");
  const [health, setHealth] = useState("");
  const [healthAgents, setHealthAgents] = useState<AgentHealthRow[]>([]);
  const [apiOk, setApiOk] = useState(true);
  const [healthLoading, setHealthLoading] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [backends, setBackends] = useState<BackendOption[]>([]);
  const [defaultBackend, setDefaultBackend] = useState("codex");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [sessionsDir, setSessionsDir] = useState<string | null>(null);
  const [bridgeProbeFailed, setBridgeProbeFailed] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    getLastSessionId(),
  );
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [composerNew, setComposerNew] = useState(() => getLastSessionId() == null);
  const [sidebarOpen, setSidebarOpenState] = useState(getSidebarOpen);
  const [sessionRailWidth, setSessionRailWidthState] = useState(getSessionRailWidth);
  const [sessionQuery, setSessionQuery] = useState("");
  const [shellView, setShellView] = useState<ShellView>("workspace");

  const runningSessionIds = useRunningSessionIds();

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

  const reloadHealth = useCallback(async (probeBridge = false): Promise<boolean> => {
    setHealthLoading(true);
    try {
      const h = await fetchHealth(probeBridge, probeBridge);
      const ok = Boolean(h.ok && h.api?.ok !== false);
      setApiOk(ok);
      apiOkRef.current = ok;
      setSessionsDir(typeof h.sessions_dir === "string" ? h.sessions_dir : null);
      const rows = h.agents ?? [];
      setHealthAgents(rows);
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
      setHealth(formatRoomModelLine(opts) || "backend");
      return ok;
    } catch (e) {
      const msg = String(e);
      setApiOk(false);
      apiOkRef.current = false;
      setHealth(
        msg.includes("Load failed") || msg.includes("Failed to fetch")
          ? "API(8765) 연결 실패 — make dev / tauri-dev 재시작"
          : msg,
      );
      return false;
    } finally {
      setHealthLoading(false);
    }
  }, []);

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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        if (cancelled) return;
        const ok = await reloadHealth(true);
        if (ok) {
          const b = await fetchBackends().catch(() => ({
            options: [],
            default: null,
          }));
          setBackends(b.options);
          if (b.default) setDefaultBackend(b.default);
          await reloadSessions();
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
    void ensureDesktopNotifyPermission();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      void (async () => {
        const wasOk = apiOkRef.current;
        const ok = await reloadHealth(false);
        if (ok && !wasOk) {
          await reloadSessions();
        }
      })();
    }, 45_000);
    return () => window.clearInterval(id);
  }, [reloadHealth, reloadSessions]);

  useEffect(() => {
    reloadSessions().catch(() => {});
  }, [listTab, reloadSessions]);

  useEffect(() => {
    if (sessions.length === 0) return;
    if (selectedId && !sessions.some((s) => s.id === selectedId)) {
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

  async function onRoomSessionChange(sessionId: string) {
    skipNextDetailLoadRef.current = true;
    setSelectedId(sessionId);
    setComposerNew(false);
    setLastSessionId(sessionId);
    setListTab("active");
    await reloadSessions();
    await loadDetail(sessionId, true);
  }

  async function onRunComplete(sessionId: string) {
    await onRoomSessionChange(sessionId);
  }

  const startNew = useCallback(() => {
    setComposerNew(true);
    setSelectedId(null);
    setDetail(null);
    setListTab("active");
    clearLastSessionId();
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
      if (!event.ctrlKey && ["1", "2", "3", "4", "5"].includes(key)) {
        event.preventDefault();
        requestWorkspaceTabByIndex(key);
      }
    }

    window.addEventListener("keydown", onKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", onKeyDown, { capture: true });
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
  const roomSessionId = composerNew ? null : selectedId;
  const roomSessionDetail =
    roomSessionId && detail?.id === roomSessionId ? detail : null;
  const roomSessionLoading = Boolean(
    roomSessionId &&
      (loadingDetail || (detail != null && detail.id !== roomSessionId)),
  );

  return (
    <div className="mac-app mac-app--developer-console">
      <MacNotificationProvider>
      <div className="mac-window">
        <MacTitlebar
          leading={
            !inTauri ? (
              <div className="traffic-lights" aria-hidden>
                <span className="close" />
                <span className="minimize" />
                <span className="zoom" />
              </div>
            ) : undefined
          }
        />

        <div
          className={`workspace-shell${sidebarOpen ? "" : " workspace-shell--rail-collapsed"}`}
        >
          <SessionRail
            open={sidebarOpen}
            width={sessionRailWidth}
            onWidthChange={setSessionRailWidthState}
            onWidthCommit={commitSessionRailWidth}
          >
            <div className="chat-list-header">
              <div className="sidebar-title-row">
                <h1>{listTab === "archived" ? "Archive" : "Sessions"}</h1>
              </div>
              <button
                type="button"
                className="mac-btn-primary mac-sidebar-btn"
                onClick={startNew}
                title="새 Session (⌘N)"
              >
                새 Session
              </button>
              <label className="session-search">
                <span className="session-search__icon" aria-hidden>
                  ⌕
                </span>
                <input
                  type="search"
                  value={sessionQuery}
                  onChange={(event) => setSessionQuery(event.target.value)}
                  placeholder="세션 검색"
                  aria-label="세션 검색"
                />
              </label>
              <div className="list-tabs mac-segmented" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={listTab === "active"}
                  className={listTab === "active" ? "active" : ""}
                  onClick={() => setListTab("active")}
                >
                  Sessions
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={listTab === "archived"}
                  className={listTab === "archived" ? "active" : ""}
                  onClick={() => setListTab("archived")}
                >
                  Archive
                </button>
              </div>
            </div>
            <SessionRailStatusChip
              apiOk={apiOk}
              agents={healthAgents}
              loading={healthLoading}
              reconnecting={reconnecting}
              sessionsDir={sessionsDir}
              probeBridgeFailed={bridgeProbeFailed}
              onRefresh={() => void reloadHealth(true)}
              onReconnectCursor={() => void handleReconnectCursor()}
            />
            {!apiOk && health ? (
              <p className="chat-list-status chat-list-status--error">{health}</p>
            ) : null}
            {sessionsError ? (
              <p className="chat-list-status chat-list-status--error">{sessionsError}</p>
            ) : null}
            {apiOk && sessions.length === 0 && !sessionsError && sessionsDir ? (
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
              onUnarchive={listTab === "archived" ? handleUnarchive : undefined}
              onRename={handleRename}
              onDelete={handleDelete}
            />
            {listTab === "active" ? (
              <div className="sidebar-footer">
                <button
                  type="button"
                  className="mac-btn-secondary sidebar-settings-btn"
                  onClick={() => setShellView("settings")}
                >
                  Settings…
                </button>
                <button
                  type="button"
                  className={[
                    "mac-btn-secondary",
                    "sidebar-mode-btn",
                    mode === "classic" ? "is-active" : "",
                  ].join(" ")}
                  onClick={() =>
                    setMode((m) => (m === "room" ? "classic" : "room"))
                  }
                  title={
                    mode === "room"
                      ? "Planner · Critic · Scribe 순차 모드"
                      : "Session 모드로 돌아가기"
                  }
                >
                  {mode === "room"
                    ? "클래식 (레거시)…"
                    : "← Session으로 돌아가기"}
                </button>
              </div>
            ) : null}
          </SessionRail>

          <section
            className={[
              "workspace-pane",
              mode === "classic" ? "workspace-pane--classic chat-pane--classic" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-label="Workspace"
          >
            {shellView === "settings" ? (
              <SettingsPage
                sessionId={roomSessionId}
                session={roomSessionDetail}
                selectedAgents={agents.filter((a) => a.ready).map((a) => a.id)}
                turnProfile={getTurnStrategy()}
                efficiencyOn={getEfficiencyMode()}
                apiOk={apiOk}
                healthAgents={healthAgents}
                healthLoading={healthLoading}
                reconnecting={reconnecting}
                sessionsDir={sessionsDir}
                probeBridgeFailed={bridgeProbeFailed}
                onRefreshDiagnostics={() => void reloadHealth(true)}
                onReconnectCursor={() => void handleReconnectCursor()}
                onBack={() => setShellView("workspace")}
                onOpenLegacy={() => {
                  setMode("classic");
                  setShellView("workspace");
                }}
              />
            ) : mode === "room" ? (
              <RoomChat
                agents={agents}
                healthAgents={healthAgents}
                sessionId={roomSessionId}
                session={roomSessionDetail}
                loading={roomSessionLoading}
                onSessionChange={onRoomSessionChange}
                onSessionMetaRefresh={refreshSessionRun}
                sidebarOpen={sidebarOpen}
                onToggleSidebar={toggleSidebar}
                onOpenSettings={() => setShellView("settings")}
              />
            ) : composerNew ? (
              <RunPanel
                backends={backends}
                defaultBackend={defaultBackend}
                onComplete={onRunComplete}
                sidebarOpen={sidebarOpen}
                onToggleSidebar={toggleSidebar}
              />
            ) : (
              <SessionViewer
                session={detail}
                loading={loadingDetail}
                sidebarOpen={sidebarOpen}
                onToggleSidebar={toggleSidebar}
                agents={agents}
                onSessionRefresh={() => {
                  if (selectedId) void loadDetail(selectedId, true);
                }}
              />
            )}
          </section>
        </div>
      </div>
      </MacNotificationProvider>
    </div>
  );
}
