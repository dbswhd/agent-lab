import { useState } from "react";
import type { SessionSummary } from "../api/client";
import {
  SessionContextMenu,
  type MenuAction,
} from "./SessionContextMenu";
import { MacAlert } from "./MacAlert";

type Props = {
  sessions: SessionSummary[];
  selectedId: string | null;
  runningSessionIds?: string[];
  archived?: boolean;
  query?: string;
  onSelect: (id: string) => void;
  onArchive?: (id: string) => void;
  onUnarchive?: (id: string) => void;
  onRename?: (id: string, topic: string) => void;
  onDelete?: (id: string) => void;
};

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
      });
    }
    return d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

function sessionSubtitle(s: SessionSummary): string {
  if (s.workflow === "room.parallel") {
    return "Cursor · Codex · Claude";
  }
  return s.model || "Planner · Critic · Scribe";
}

export function SessionList({
  sessions,
  selectedId,
  runningSessionIds = [],
  archived = false,
  query = "",
  onSelect,
  onArchive,
  onUnarchive,
  onRename,
  onDelete,
}: Props) {
  const [menu, setMenu] = useState<{
    id: string;
    x: number;
    y: number;
  } | null>(null);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleSessions = normalizedQuery
    ? sessions.filter((session) =>
        [
          session.topic,
          session.id,
          session.model,
          session.workflow,
          sessionSubtitle(session),
        ]
          .filter(Boolean)
          .some((value) =>
            String(value).toLocaleLowerCase().includes(normalizedQuery),
          ),
      )
    : sessions;

  if (visibleSessions.length === 0) {
    return (
      <p className="chat-list-empty">
        {normalizedQuery
          ? "검색 결과가 없습니다"
          : archived
            ? "보관된 대화가 없습니다"
            : "대화 없음 · 새 대화를 시작하세요"}
      </p>
    );
  }

  function handleMenuAction(id: string, action: MenuAction) {
    setMenu(null);
    if (action === "archive" && onArchive) onArchive(id);
    if (action === "unarchive" && onUnarchive) onUnarchive(id);
    if (action === "rename") {
      const s = sessions.find((x) => x.id === id);
      setRenameId(id);
      setRenameValue(s?.topic || id);
    }
    if (action === "delete") setDeleteId(id);
  }

  return (
    <>
      <div className="session-list-scroll">
        <ul className="session-list">
          {visibleSessions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className={`session-row${selectedId === s.id ? " selected" : ""}${runningSessionIds.includes(s.id) ? " session-row--running" : ""}`}
                aria-current={selectedId === s.id ? "true" : undefined}
                onClick={() => onSelect(s.id)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setMenu({ id: s.id, x: e.clientX, y: e.clientY });
                }}
              >
                <span className="session-preview">
                  <span className="session-preview-title">
                    {runningSessionIds.includes(s.id) ? (
                      <span
                        className="session-row__run-dot"
                        aria-label="실행 중"
                        title="에이전트 턴 실행 중"
                      />
                    ) : null}
                    {s.topic || s.id}
                  </span>
                  <span className="session-preview-sub">{sessionSubtitle(s)}</span>
                </span>
                <span className="session-time">{formatTime(s.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {menu && (
        <SessionContextMenu
          x={menu.x}
          y={menu.y}
          archived={archived}
          onAction={(a) => handleMenuAction(menu.id, a)}
          onClose={() => setMenu(null)}
        />
      )}

      <MacAlert
        open={renameId !== null}
        title="이름 변경"
        onClose={() => setRenameId(null)}
        buttons={[
          {
            label: "취소",
            variant: "cancel",
            onClick: () => setRenameId(null),
          },
          {
            label: "저장",
            variant: "default",
            onClick: () => {
              if (renameId && onRename) onRename(renameId, renameValue.trim());
              setRenameId(null);
            },
          },
        ]}
      >
        <input
          className="mac-alert-input mac-textfield"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter" && renameId && onRename) {
              onRename(renameId, renameValue.trim());
              setRenameId(null);
            }
          }}
        />
      </MacAlert>

      <MacAlert
        open={deleteId !== null}
        title="대화를 삭제할까요?"
        message="이 작업은 되돌릴 수 없습니다. 세션 폴더가 영구 삭제됩니다."
        onClose={() => setDeleteId(null)}
        buttons={[
          {
            label: "취소",
            variant: "cancel",
            onClick: () => setDeleteId(null),
          },
          {
            label: "삭제",
            variant: "destructive",
            onClick: () => {
              if (deleteId && onDelete) onDelete(deleteId);
              setDeleteId(null);
            },
          },
        ]}
      />
    </>
  );
}
