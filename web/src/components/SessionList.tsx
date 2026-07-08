import { useMemo, useRef, useState } from "react";
import type { SessionSummary } from "../api/client";
import {
  SESSION_GROUP_UNGROUPED_LABEL,
  createSessionGroup,
  getSessionGroup,
  groupLabelToAssignment,
  groupSessionsForDrag,
  groupSessionsForList,
  isSessionPinned,
  listSessionGroups,
  moveSessionToGroup,
  toggleSessionPinned,
} from "../utils/sessionGroupPrefs";
import { SessionContextMenu, type MenuAction } from "./SessionContextMenu";
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

/** Compact relative/absolute timestamp — disambiguates rows that share a topic
 * (e.g. repeated dogfood runs), since the list otherwise renders title-only. */
function formatSessionTimestamp(iso?: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffMin = Math.floor((Date.now() - date.getTime()) / 60000);
  if (diffMin < 1) return "방금";
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}일 전`;
  return date.toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" });
}

/**
 * Session rail list — title-only rows, optional group headers, context menu.
 */
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
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(
    null,
  );
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [newGroupOpen, setNewGroupOpen] = useState(false);
  const [newGroupValue, setNewGroupValue] = useState("");
  const [pendingGroupSessionId, setPendingGroupSessionId] = useState<
    string | null
  >(null);
  const [groupRevision, setGroupRevision] = useState(0);
  const [dragSessionId, setDragSessionId] = useState<string | null>(null);
  const [dropTargetKey, setDropTargetKey] = useState<string | null>(null);
  const suppressClickRef = useRef(false);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const dragEnabled = !archived && !normalizedQuery;
  const visibleSessions = useMemo(() => {
    if (!normalizedQuery) return sessions;
    return sessions.filter((session) =>
      [session.topic, session.id]
        .filter(Boolean)
        .some((value) =>
          String(value).toLocaleLowerCase().includes(normalizedQuery),
        ),
    );
  }, [normalizedQuery, sessions]);

  const groupedSessions = useMemo(() => {
    void groupRevision;
    if (dragSessionId) return groupSessionsForDrag(visibleSessions);
    return groupSessionsForList(visibleSessions);
  }, [dragSessionId, groupRevision, visibleSessions]);

  const sessionGroups = useMemo(() => {
    void groupRevision;
    return listSessionGroups();
  }, [groupRevision]);

  function bumpGroups() {
    setGroupRevision((value) => value + 1);
  }

  function finishDrag() {
    setDragSessionId(null);
    setDropTargetKey(null);
  }

  function handleDropOnGroup(groupKey: string) {
    if (!dragSessionId) return;
    const current = getSessionGroup(dragSessionId);
    const next = groupLabelToAssignment(groupKey);
    if (current !== next) {
      moveSessionToGroup(dragSessionId, next);
      bumpGroups();
    }
    suppressClickRef.current = true;
    finishDrag();
  }

  if (visibleSessions.length === 0) {
    return (
      <p className="session-list-empty">
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
    if (action === "pin" || action === "unpin") {
      toggleSessionPinned(id);
      bumpGroups();
      return;
    }
    if (action === "archive" && onArchive) onArchive(id);
    if (action === "unarchive" && onUnarchive) onUnarchive(id);
    if (action === "rename") {
      const s = sessions.find((x) => x.id === id);
      setRenameId(id);
      setRenameValue(s?.topic || id);
    }
    if (action === "delete") setDeleteId(id);
    if (typeof action === "object" && action.type === "move-to-group") {
      moveSessionToGroup(id, action.group);
      bumpGroups();
    }
    if (typeof action === "object" && action.type === "new-group") {
      setPendingGroupSessionId(id);
      setNewGroupValue("");
      setNewGroupOpen(true);
    }
  }

  return (
    <>
      <div className="session-list scroll-y">
        {groupedSessions.map((group) => {
          const isDropTarget =
            dragSessionId !== null && dropTargetKey === group.key;
          return (
            <section
              key={group.key}
              className={[
                "session-list__group",
                isDropTarget ? "session-list__group--drop-target" : "",
                dragSessionId && group.sessions.length === 0
                  ? "session-list__group--drop-empty"
                  : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onDragOver={(event) => {
                if (!dragSessionId) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                setDropTargetKey(group.key);
              }}
              onDragLeave={(event) => {
                if (
                  event.currentTarget.contains(
                    event.relatedTarget as Node | null,
                  )
                ) {
                  return;
                }
                setDropTargetKey((current) =>
                  current === group.key ? null : current,
                );
              }}
              onDrop={(event) => {
                event.preventDefault();
                handleDropOnGroup(group.key);
              }}
            >
              <h2 className="session-list__group-label">{group.label}</h2>
              {group.sessions.length === 0 && dragSessionId ? (
                <div className="session-list__drop-slot" aria-hidden>
                  여기로 이동
                </div>
              ) : null}
              {group.sessions.map((s) => {
                const running = runningSessionIds.includes(s.id);
                const pinned = isSessionPinned(s.id);
                const dragging = dragSessionId === s.id;
                return (
                  <button
                    key={s.id}
                    type="button"
                    draggable={dragEnabled}
                    className={[
                      "session-item",
                      selectedId === s.id ? "is-active" : "",
                      running ? "session-item--running" : "",
                      pinned ? "session-item--pinned" : "",
                      dragging ? "session-item--dragging" : "",
                      dragEnabled ? "session-item--draggable" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    aria-current={selectedId === s.id ? "true" : undefined}
                    onClick={() => {
                      if (suppressClickRef.current) {
                        suppressClickRef.current = false;
                        return;
                      }
                      onSelect(s.id);
                    }}
                    onDragStart={(event) => {
                      if (!dragEnabled) return;
                      suppressClickRef.current = false;
                      setDragSessionId(s.id);
                      setDropTargetKey(
                        getSessionGroup(s.id) ?? SESSION_GROUP_UNGROUPED_LABEL,
                      );
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", s.id);
                    }}
                    onDragEnd={() => {
                      suppressClickRef.current = true;
                      finishDrag();
                    }}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setMenu({ id: s.id, x: e.clientX, y: e.clientY });
                    }}
                  >
                    <span className="session-item__topic">
                      {s.topic || s.id}
                    </span>
                    {s.created_at ? (
                      <span className="session-item__meta">
                        {formatSessionTimestamp(s.created_at)}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </section>
          );
        })}
      </div>

      {menu ? (
        <SessionContextMenu
          x={menu.x}
          y={menu.y}
          archived={archived}
          pinned={isSessionPinned(menu.id)}
          groups={sessionGroups}
          currentGroup={getSessionGroup(menu.id)}
          onAction={(action) => handleMenuAction(menu.id, action)}
          onClose={() => setMenu(null)}
        />
      ) : null}

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
          className="field"
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
        open={newGroupOpen}
        title="새 그룹"
        onClose={() => {
          setNewGroupOpen(false);
          setPendingGroupSessionId(null);
        }}
        buttons={[
          {
            label: "취소",
            variant: "cancel",
            onClick: () => {
              setNewGroupOpen(false);
              setPendingGroupSessionId(null);
            },
          },
          {
            label: "만들기",
            variant: "default",
            onClick: () => {
              const created = createSessionGroup(newGroupValue);
              if (created && pendingGroupSessionId) {
                moveSessionToGroup(pendingGroupSessionId, created);
                bumpGroups();
              }
              setNewGroupOpen(false);
              setPendingGroupSessionId(null);
            },
          },
        ]}
      >
        <input
          className="field"
          value={newGroupValue}
          onChange={(e) => setNewGroupValue(e.target.value)}
          placeholder="그룹 이름"
          autoFocus
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            const created = createSessionGroup(newGroupValue);
            if (created && pendingGroupSessionId) {
              moveSessionToGroup(pendingGroupSessionId, created);
              bumpGroups();
            }
            setNewGroupOpen(false);
            setPendingGroupSessionId(null);
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
