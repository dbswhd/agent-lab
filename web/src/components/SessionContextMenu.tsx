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

export function SessionContextMenu({
  x,
  y,
  archived,
  onAction,
  onClose,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  return createPortal(
    <div
      ref={ref}
      className="mac-context-menu"
      style={{ left: x, top: y }}
      role="menu"
    >
      {!archived && (
        <button type="button" role="menuitem" onClick={() => onAction("rename")}>
          이름 변경…
        </button>
      )}
      {archived ? (
        <button type="button" role="menuitem" onClick={() => onAction("unarchive")}>
          복원
        </button>
      ) : (
        <button type="button" role="menuitem" onClick={() => onAction("archive")}>
          보관
        </button>
      )}
      <button
        type="button"
        role="menuitem"
        className="destructive"
        onClick={() => onAction("delete")}
      >
        삭제…
      </button>
    </div>,
    document.body,
  );
}
