import type { ReactNode } from "react";
import { AppBrandIcon } from "./AppBrandIcon";
import { ThemeToggle } from "./ThemeToggle";
import { isTauri } from "../theme";

type Props = {
  leading?: ReactNode;
};

/** Unified window title bar — brand centered, controls on edges. */
export function MacTitlebar({ leading }: Props) {
  const tauri = isTauri();
  return (
    <header
      className={`mac-titlebar${tauri ? " mac-titlebar--tauri" : ""}`}
      aria-hidden={false}
    >
      <div className="mac-titlebar-leading">{leading}</div>
      <div className="mac-titlebar-brand">
        <AppBrandIcon />
        <span className="mac-titlebar-title">Agent Lab</span>
      </div>
      <div className="mac-titlebar-trailing">
        <ThemeToggle />
      </div>
    </header>
  );
}
