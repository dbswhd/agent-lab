import { ThemeToggle } from "./ThemeToggle";

/** Reserved strip for native traffic lights (Tauri overlay title bar). */
export function TauriTitlebar() {
  return (
    <header className="tauri-titlebar" aria-hidden={false}>
      <div className="tauri-titlebar-center">
        <img
          className="app-brand-icon"
          src="/app-icon.png"
          alt=""
          width={16}
          height={16}
        />
        <span className="tauri-titlebar-title">Agent Lab</span>
      </div>
      <ThemeToggle />
    </header>
  );
}
