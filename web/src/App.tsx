import { useCallback, useEffect, useRef, useState } from "react";
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
import {
  AgentHealthPanel,
  healthToAgentOptions,
} from "./components/AgentHealthPanel";
import { ApiDiagnosticsBar } from "./components/ApiDiagnosticsBar";
import { RoomChat } from "./components/RoomChat";
import { RunPanel } from "./components/RunPanel";
import { SessionList } from "./components/SessionList";
import { SessionViewer } from "./components/SessionViewer";
import { MacTitlebar } from "./components/MacTitlebar";
import { MacNotificationProvider } from "./components/MacNotificationHost";
import { getSidebarOpen, setSidebarOpen } from "./utils/sidebarPrefs";
import { formatRoomModelLine } from "./utils/roomModels";
import { isTauriApp } from "./theme";
import { ensureDesktopNotifyPermission } from "./utils/desktopNotify";

type Mode = "room" | "classic";
type ListTab = "active" | "archived";

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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [composerNew, setComposerNew] = useState(true);
  const [sidebarOpen, setSidebarOpenState] = useState(getSidebarOpen);

  function toggleSidebar() {
    const next = !sidebarOpen;
    setSidebarOpenState(next);
    setSidebarOpen(next);
  }

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
          ? "대화 목록 불러오기 실패 — API(8765) 확인"
          : msg,
      );
    }
  }, [listTab]);

  const loadDetail = useCallback(async (id: string, keepPrevious = false) => {
    setLoadingDetail(true);
    if (!keepPrevious) {
      setDetail(null);
    }
    try {
      setDetail(await fetchSession(id));
    } finally {
      setLoadingDetail(false);
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
    if (selectedId && !composerNew) loadDetail(selectedId);
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
    setSelectedId(sessionId);
    setComposerNew(false);
    setListTab("active");
    await reloadSessions();
    await loadDetail(sessionId, true);
  }

  async function onRunComplete(sessionId: string) {
    await onRoomSessionChange(sessionId);
  }

  function startNew() {
    setComposerNew(true);
    setSelectedId(null);
    setDetail(null);
    setListTab("active");
  }

  function selectSession(id: string) {
    setSelectedId(id);
    setComposerNew(false);
  }

  async function handleArchive(id: string) {
    await archiveSession(id);
    if (selectedId === id) {
      setSelectedId(null);
      setDetail(null);
      setComposerNew(true);
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
    }
    await reloadSessions();
  }

  const inTauri = isTauriApp();

  return (
    <div className="mac-app">
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
          className={`messenger${sidebarOpen ? "" : " messenger--sidebar-collapsed"}`}
        >
          <aside className="chat-list-pane" aria-hidden={!sidebarOpen}>
            <div className="chat-list-header">
              <div className="sidebar-title-row">
                <h1>{listTab === "archived" ? "보관함" : "대화"}</h1>
              </div>
              <button
                type="button"
                className="mac-btn-primary mac-sidebar-btn"
                onClick={startNew}
              >
                새 대화
              </button>
              <div className="list-tabs mac-segmented" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={listTab === "active"}
                  className={listTab === "active" ? "active" : ""}
                  onClick={() => setListTab("active")}
                >
                  대화
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={listTab === "archived"}
                  className={listTab === "archived" ? "active" : ""}
                  onClick={() => setListTab("archived")}
                >
                  보관함
                </button>
              </div>
            </div>
            <AgentHealthPanel
              apiOk={apiOk}
              agents={healthAgents}
              loading={healthLoading}
              reconnecting={reconnecting}
              showBridgeSetupGuide={bridgeProbeFailed}
              onRefresh={() => void reloadHealth(true)}
              onReconnectCursor={() => void handleReconnectCursor()}
            />
            <ApiDiagnosticsBar
              apiOk={apiOk}
              sessionsDir={sessionsDir}
              probeBridgeFailed={bridgeProbeFailed}
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
              archived={listTab === "archived"}
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
                      : "3자 룸으로 돌아가기"
                  }
                >
                  {mode === "room"
                    ? "클래식 (레거시)…"
                    : "← 3자 룸으로 돌아가기"}
                </button>
              </div>
            ) : null}
          </aside>

          <section
            className={[
              "chat-pane",
              mode === "classic" ? "chat-pane--classic" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {mode === "room" ? (
              <RoomChat
                agents={agents}
                healthAgents={healthAgents}
                sessionId={composerNew ? null : selectedId}
                session={composerNew ? null : detail}
                loading={!composerNew && loadingDetail && detail == null}
                onSessionChange={onRoomSessionChange}
                onSessionMetaRefresh={refreshSessionRun}
                sidebarOpen={sidebarOpen}
                onToggleSidebar={toggleSidebar}
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
