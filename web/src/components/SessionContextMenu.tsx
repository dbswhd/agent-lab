import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type MenuAction =
  | "pin"
  | "unpin"
  | "rename"
  | "archive"
  | "unarchive"
  | "fork"
  | "delete"
  | { type: "move-to-group"; group: string | null }
  | { type: "new-group" };

type Props = {
  x: number;
  y: number;
  archived: boolean;
  pinned: boolean;
  groups: string[];
  currentGroup: string | null;
  onAction: (action: MenuAction) => void;
  onClose: () => void;
};

/** Session rail context menu — Claude-style with group flyout. */
export function SessionContextMenu({
  x,
  y,
  archived,
  pinned,
  groups,
  currentGroup,
  onAction,
  onClose,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [groupOpen, setGroupOpen] = useState(false);
  const groupCloseTimerRef = useRef<number | null>(null);

  const openGroupMenu = () => {
    if (groupCloseTimerRef.current !== null) {
      window.clearTimeout(groupCloseTimerRef.current);
      groupCloseTimerRef.current = null;
    }
    setGroupOpen(true);
  };

  const scheduleCloseGroupMenu = () => {
    if (groupCloseTimerRef.current !== null) {
      window.clearTimeout(groupCloseTimerRef.current);
    }
    groupCloseTimerRef.current = window.setTimeout(() => {
      setGroupOpen(false);
      groupCloseTimerRef.current = null;
    }, 200);
  };

  useEffect(() => {
    return () => {
      if (groupCloseTimerRef.current !== null) {
        window.clearTimeout(groupCloseTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    function onDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const MENU_W = 220;
  const MENU_H = 280;
  const cx = Math.min(x, window.innerWidth - MENU_W - 8);
  const cy = Math.min(y, window.innerHeight - MENU_H - 8);

  function run(action: MenuAction) {
    onAction(action);
    onClose();
  }

  return createPortal(
    <div
      ref={ref}
      className="ctx-menu ctx-menu--session"
      style={{ left: cx, top: cy }}
      role="menu"
    >
      {!archived ? (
        <>
          <div className="ctx-menu__section">
            <button
              type="button"
              className="ctx-menu__item"
              role="menuitem"
              onClick={() => run(pinned ? "unpin" : "pin")}
            >
              <span>{pinned ? "고정 해제" : "고정"}</span>
              <kbd className="ctx-menu__kbd">P</kbd>
            </button>

            <button
              type="button"
              className="ctx-menu__item"
              role="menuitem"
              onClick={() => run("rename")}
            >
              <span>이름 변경</span>
              <kbd className="ctx-menu__kbd">R</kbd>
            </button>

            <button
              type="button"
              className="ctx-menu__item"
              role="menuitem"
              onClick={() => run("fork")}
              data-testid="session-menu-fork"
            >
              <span>포크</span>
              <kbd className="ctx-menu__kbd">F</kbd>
            </button>
          </div>

          <div className="ctx-menu__group-block">
            <div
              className="ctx-menu__sep ctx-menu__sep--section"
              role="separator"
            />

            <div
              className={`ctx-menu__submenu-host${groupOpen ? " is-open" : ""}`}
              onMouseEnter={openGroupMenu}
              onMouseLeave={scheduleCloseGroupMenu}
            >
              <button
                type="button"
                className="ctx-menu__item ctx-menu__item--submenu"
                role="menuitem"
                aria-haspopup="menu"
                aria-expanded={groupOpen}
                onClick={() => {
                  if (groupOpen) {
                    if (groupCloseTimerRef.current !== null) {
                      window.clearTimeout(groupCloseTimerRef.current);
                      groupCloseTimerRef.current = null;
                    }
                    setGroupOpen(false);
                    return;
                  }
                  openGroupMenu();
                }}
              >
                <span>그룹으로 이동</span>
                <span className="ctx-menu__chev" aria-hidden>
                  ›
                </span>
              </button>

              <div className="ctx-menu__flyout-bridge">
                <div
                  className="ctx-menu ctx-menu--session ctx-menu--flyout"
                  role="menu"
                >
                  {groups.map((group, index) => (
                    <button
                      key={group}
                      type="button"
                      className={`ctx-menu__item${currentGroup === group ? " is-active" : ""}`}
                      role="menuitem"
                      onClick={() => run({ type: "move-to-group", group })}
                    >
                      <span>{group}</span>
                      <kbd className="ctx-menu__kbd">{index + 1}</kbd>
                    </button>
                  ))}
                  {groups.length > 0 ? (
                    <div
                      className="ctx-menu__sep ctx-menu__sep--thin"
                      role="separator"
                    />
                  ) : null}
                  {currentGroup ? (
                    <button
                      type="button"
                      className="ctx-menu__item"
                      role="menuitem"
                      onClick={() =>
                        run({ type: "move-to-group", group: null })
                      }
                    >
                      <span>그룹 없음</span>
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="ctx-menu__item"
                    role="menuitem"
                    onClick={() => run({ type: "new-group" })}
                  >
                    <span>새 그룹…</span>
                    <kbd className="ctx-menu__kbd">{groups.length + 1}</kbd>
                  </button>
                </div>
              </div>
            </div>

            <div
              className="ctx-menu__sep ctx-menu__sep--thin"
              role="separator"
            />
          </div>
        </>
      ) : null}

      <div className="ctx-menu__section">
        {archived ? (
          <button
            type="button"
            className="ctx-menu__item"
            role="menuitem"
            onClick={() => run("unarchive")}
          >
            <span>복원</span>
          </button>
        ) : (
          <button
            type="button"
            className="ctx-menu__item"
            role="menuitem"
            onClick={() => run("archive")}
          >
            <span>보관</span>
            <kbd className="ctx-menu__kbd">A</kbd>
          </button>
        )}

        <button
          type="button"
          className="ctx-menu__item ctx-menu__item--danger"
          role="menuitem"
          onClick={() => run("delete")}
        >
          <span>삭제</span>
          <kbd className="ctx-menu__kbd">D</kbd>
        </button>
      </div>
    </div>,
    document.body,
  );
}
