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
import { ThemeToggle } from "./components/ThemeToggle";
import { TauriTitlebar } from "./components/TauriTitlebar";
import { isTauri } from "./theme";

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

  const reloadSessions = useCallback(async () => {
    const { sessions: list } = await fetchSessions(listTab === "archived");
    setSessions(list);
  }, [listTab]);

  const loadDetail = useCallback(async (id: string) => {
    setLoadingDetail(true);
    try {
      setDetail(await fetchSession(id));
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      const [h, a, b] = await Promise.all([
        fetchHealth(),
        fetchAgents(),
        fetchBackends(),
      ]);
      setHealth(
        [h.provider, h.model].filter(Boolean).join(" · ") || "backend",
      );
      setAgents(a.agents);
      setBackends(b.options);
      if (b.default) setDefaultBackend(b.default);
      await reloadSessions();
    })().catch((e) => setHealth(String(e)));
  }, [reloadSessions]);

  useEffect(() => {
    reloadSessions().catch(() => {});
  }, [listTab, reloadSessions]);

  useEffect(() => {
    if (selectedId && !composerNew) loadDetail(selectedId);
    else if (composerNew) setDetail(null);
  }, [selectedId, composerNew, loadDetail]);

  async function onRoomSessionChange(sessionId: string) {
    setSelectedId(sessionId);
    setComposerNew(false);
    setListTab("active");
    await reloadSessions();
    await loadDetail(sessionId);
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

  const inTauri = isTauri();

  return (
    <div className="mac-app">
      <div className="mac-window">
        {inTauri && <TauriTitlebar />}

        {!inTauri && (
          <header className="mac-titlebar">
            <div className="traffic-lights" aria-hidden>
              <span className="close" />
              <span className="minimize" />
              <span className="zoom" />
            </div>
            <div className="mac-titlebar-center">
              <img
                className="app-brand-icon"
                src="/app-icon.png"
                alt=""
                width={16}
                height={16}
              />
              <span className="mac-titlebar-title">Agent Lab</span>
            </div>
            <ThemeToggle />
          </header>
        )}

        <div className="messenger">
          <aside className="chat-list-pane">
            <div className="chat-list-header">
              <div className="sidebar-title-row">
                <h1>{listTab === "archived" ? "보관함" : "대화"}</h1>
              </div>
              <button
                type="button"
                className="mac-btn-primary"
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
                    클래식
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
                loading={!composerNew && loadingDetail}
                onSessionChange={onRoomSessionChange}
              />
            ) : composerNew ? (
              <RunPanel
                backends={backends}
                defaultBackend={defaultBackend}
                onComplete={onRunComplete}
              />
            ) : (
              <SessionViewer session={detail} loading={loadingDetail} />
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
