import type { ReactNode } from "react";
import { ThemeToggle } from "./ThemeToggle";

type Props = {
  leading?: ReactNode;
  title?: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
  viewBadge?: string;
  /** When false, theme toggle is omitted (pass in trailing yourself). */
  showThemeToggle?: boolean;
};

export function MacTitlebar({
  leading,
  title,
  meta,
  trailing,
  viewBadge,
  showThemeToggle = true,
}: Props) {
  const tauri =
    typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

  function startWindowDrag(event: React.MouseEvent<HTMLElement>) {
    if (!tauri || event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("button, input, select, textarea, a")) return;
    void import("@tauri-apps/api/window").then(({ getCurrentWindow }) =>
      getCurrentWindow().startDragging(),
    );
  }

  return (
    <header
      className={`titlebar${tauri ? " titlebar--tauri" : ""}`}
      data-tauri-drag-region={tauri ? "" : undefined}
      onMouseDown={startWindowDrag}
    >
      {leading}
      {viewBadge ? (
        <span className="titlebar__view-badge">{viewBadge}</span>
      ) : null}
      <div
        className="titlebar__brand"
        data-tauri-drag-region={tauri ? "" : undefined}
      >
        {title ? (
          <span className="titlebar__topic">{title}</span>
        ) : (
          <span className="titlebar__title">Agent Lab</span>
        )}
      </div>
      <div className="titlebar__spacer" />
      {meta ? <span className="titlebar__meta">{meta}</span> : null}
      <div className="titlebar__actions">
        {trailing}
        {showThemeToggle ? <ThemeToggle /> : null}
      </div>
    </header>
  );
}
