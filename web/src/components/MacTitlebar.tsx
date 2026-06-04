import type { MouseEvent, ReactNode } from "react";
import { AppBrandIcon } from "./AppBrandIcon";
import { ThemeToggle } from "./ThemeToggle";
import { isTauri } from "../theme";
import { getCurrentWindow } from "@tauri-apps/api/window";

type Props = {
  leading?: ReactNode;
};

/** Unified window title bar — brand centered, controls on edges. */
export function MacTitlebar({ leading }: Props) {
  const tauri = isTauri();

  function startWindowDrag(event: MouseEvent<HTMLElement>) {
    if (!tauri || event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("button, input, select, textarea, a")) return;
    void getCurrentWindow().startDragging();
  }

  return (
    <header
      className={`mac-titlebar${tauri ? " mac-titlebar--tauri" : ""}`}
      aria-hidden={false}
      data-tauri-drag-region={tauri ? "" : undefined}
      onMouseDown={startWindowDrag}
    >
      <div className="mac-titlebar-leading">{leading}</div>
      <div
        className="mac-titlebar-brand"
        data-tauri-drag-region={tauri ? "" : undefined}
      >
        <AppBrandIcon />
        <span className="mac-titlebar-title">Agent Lab</span>
      </div>
      <div className="mac-titlebar-trailing">
        <ThemeToggle />
      </div>
    </header>
  );
}
