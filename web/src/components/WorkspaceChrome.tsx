import type { ReactNode } from "react";
import type { RightPanelMode } from "../utils/workspaceTabs";
import type { Locale } from "../i18n/locale";
import { openCommandPalette } from "../utils/desktopShortcuts";
import { SidebarToggle } from "./SidebarToggle";
import { WorkbenchModeMenu } from "./WorkbenchModeMenu";

type Props = {
  readonly title: string;
  readonly meta?: string;
  readonly headerExtra?: ReactNode;
  readonly origin?: string;
  readonly sidebarOpen: boolean;
  readonly rightPanelOpen: boolean;
  readonly rightPanelMode: RightPanelMode;
  readonly locale: Locale;
  readonly onToggleSidebar: () => void;
  readonly onToggleRightPanel: () => void;
  readonly onSelectRightPanelMode: (mode: RightPanelMode) => void;
  readonly onOpenSettings?: () => void;
  readonly onWorkbenchMenuOpenChange?: (open: boolean) => void;
};

function isTauriApp(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function WorkspaceChrome({
  title,
  meta,
  headerExtra,
  origin = "agent-lab",
  sidebarOpen,
  rightPanelOpen,
  rightPanelMode,
  locale,
  onToggleSidebar,
  onToggleRightPanel,
  onSelectRightPanelMode,
  onOpenSettings: _onOpenSettings,
  onWorkbenchMenuOpenChange,
}: Props) {
  const tauri = isTauriApp();

  function startWindowDrag(event: React.MouseEvent<HTMLElement>) {
    if (!tauri || event.button !== 0) return;
    if (
      event.target instanceof HTMLElement &&
      event.target.closest("button, input, select, textarea, a")
    ) {
      return;
    }
    void import("@tauri-apps/api/window").then(({ getCurrentWindow }) =>
      getCurrentWindow().startDragging(),
    );
  }

  return (
    <header
      className={`workspace-chrome${tauri ? " workspace-chrome--tauri" : ""}`}
      data-tauri-drag-region={tauri ? "" : undefined}
      onMouseDown={startWindowDrag}
    >
      <div className="workspace-chrome__bar">
        <div
          className="workspace-chrome__drag"
          aria-hidden
          data-tauri-drag-region={tauri ? "" : undefined}
        />
        <div className="workspace-chrome__lead">
          <span className="workspace-chrome__gutter">
            <SidebarToggle
              open={sidebarOpen}
              onToggle={onToggleSidebar}
              variant="panel"
            />
          </span>
          <span className="workspace-chrome__lead-row">
            <span className="workspace-chrome__title-wrap">
              <button
                type="button"
                className="workspace-chrome__topic-btn"
                title={title}
                data-tauri-drag-region={tauri ? "" : undefined}
              >
                {title}
              </button>
            </span>
            <span className="workspace-chrome__pills">
              <span className="workspace-chrome__pill">{origin}</span>
              {headerExtra}
              {meta ? (
                <span className="workspace-chrome__pill workspace-chrome__pill--meta">
                  {meta}
                </span>
              ) : null}
            </span>
          </span>
        </div>
        <div className="workspace-chrome__actions">
          <button
            type="button"
            className="workspace-chrome__icon-btn"
            title="⌘K"
            aria-label="명령 팔레트"
            onClick={openCommandPalette}
          >
            <svg
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.7}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </button>
          <WorkbenchModeMenu
            active={rightPanelMode}
            open={rightPanelOpen}
            locale={locale}
            onSelect={onSelectRightPanelMode}
            onToggleOpen={onToggleRightPanel}
            onMenuOpenChange={onWorkbenchMenuOpenChange}
          />
        </div>
      </div>
    </header>
  );
}
