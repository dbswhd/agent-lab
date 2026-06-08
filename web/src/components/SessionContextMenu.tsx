import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export type MenuAction = "archive" | "unarchive" | "rename" | "delete";

type Props = {
  x: number;
  y: number;
  archived: boolean;
  onAction: (action: MenuAction) => void;
  onClose: () => void;
};

/** SessionContextMenu — canonical right-click menu for session list rows.
 *
 *  Uses .ctx-menu / .ctx-menu__item / .ctx-menu__sep classes (overlays.css).
 *  Drop-in for old .mac-context-menu (macos26.css).
 *  Position clamped to viewport; rendered into document.body via portal.
 */
export function SessionContextMenu({ x, y, archived, onAction, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  /* Close on outside click or Escape */
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  /* Clamp to viewport */
  const MENU_W = 188;
  const MENU_H = 116;
  const cx = Math.min(x, window.innerWidth  - MENU_W - 8);
  const cy = Math.min(y, window.innerHeight - MENU_H - 8);

  return createPortal(
    <div
      ref={ref}
      className="ctx-menu"
      style={{ left: cx, top: cy }}
      role="menu"
    >
      {!archived && (
        <button
          type="button"
          className="ctx-menu__item"
          role="menuitem"
          onClick={() => { onAction("rename"); onClose(); }}
        >
          이름 변경…
        </button>
      )}

      {archived ? (
        <button
          type="button"
          className="ctx-menu__item"
          role="menuitem"
          onClick={() => { onAction("unarchive"); onClose(); }}
        >
          복원
        </button>
      ) : (
        <button
          type="button"
          className="ctx-menu__item"
          role="menuitem"
          onClick={() => { onAction("archive"); onClose(); }}
        >
          보관
        </button>
      )}

      <div className="ctx-menu__sep" role="separator" />

      <button
        type="button"
        className="ctx-menu__item ctx-menu__item--danger"
        role="menuitem"
        onClick={() => { onAction("delete"); onClose(); }}
      >
        삭제…
      </button>
    </div>,
    document.body,
  );
}
