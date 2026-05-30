import { useCallback, useEffect, useState } from "react";
import {
  archiveSession,
  deleteSession,
  fetchAgents,
  fetchBackends,
  fetchHealth,
  fetchSession,
  fetchSessions,
  renameSession,
  unarchiveSession,
  type AgentOption,
  type BackendOption,
  type SessionDetail,
  type SessionSummary,
} from "./api/client";
import { RoomChat } from "./components/RoomChat";
import { RunPanel } from "./components/RunPanel";
import { SessionList } from "./components/SessionList";
import { SessionViewer } from "./components/SessionViewer";
import { MacTitlebar } from "./components/MacTitlebar";
import { getSidebarOpen, setSidebarOpen } from "./utils/sidebarPrefs";
import { formatRoomModelLine } from "./utils/roomModels";
import { isTauriApp } from "./theme";

type Mode = "room" | "classic";
type ListTab = "active" | "archived";

export default function App() {
  const [mode, setMode] = useState<Mode>("room");
  const [listTab, setListTab] = useState<ListTab>("active");
  const [health, setHealth] = useState("");
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [backends, setBackends] = useState<BackendOption[]>([]);
  const [defaultBackend, setDefaultBackend] = useState("codex");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
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

  const reloadSessions = useCallback(async () => {
    const { sessions: list } = await fetchSessions(listTab === "archived");
    setSessions(list);
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

  useEffect(() => {
    (async () => {
      const [, a, b] = await Promise.all([
        fetchHealth(),
        fetchAgents(),
        fetchBackends(),
      ]);
      setAgents(a.agents);
      setHealth(formatRoomModelLine(a.agents) || "backend");
      setBackends(b.options);
      if (b.default) setDefaultBackend(b.default);
      await reloadSessions();
    })().catch((e) => {
      const msg = String(e);
      setHealth(
        msg.includes("Load failed") || msg.includes("Failed to fetch")
          ? "API(8765) 연결 실패 — 앱을 완전히 종료 후 make tauri-dev 로 재시작"
          : msg,
      );
    });
  }, [reloadSessions]);

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
              {listTab === "active" && (
                <div className="mode-switch mac-segmented" role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={mode === "room"}
                    className={mode === "room" ? "active" : ""}
                    onClick={() => setMode("room")}
                  >
                    3자 룸
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={mode === "classic"}
                    className={mode === "classic" ? "active" : ""}
                    onClick={() => setMode("classic")}
                  >
                    클래식 (레거시)
                  </button>
                </div>
              )}
            </div>
            <p className="chat-list-status">{health}</p>
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
          </aside>

          <section className="chat-pane">
            {mode === "room" ? (
              <RoomChat
                agents={agents}
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
              />
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
