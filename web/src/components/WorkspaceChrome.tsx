import type { RightPanelMode } from "../utils/workspaceTabs";
import type { Locale } from "../i18n/locale";
import { openCommandPalette } from "../utils/desktopShortcuts";
import { SidebarToggle } from "./SidebarToggle";
import { TitlebarInboxButton } from "./TitlebarInboxButton";
import { WorkbenchModeMenu } from "./WorkbenchModeMenu";

type Props = {
  readonly title: string;
  readonly meta?: string;
  readonly sidebarOpen: boolean;
  readonly rightPanelOpen: boolean;
  readonly rightPanelMode: RightPanelMode;
  readonly locale: Locale;
  readonly inboxPendingCount: number;
  readonly panelBadgeCount: number;
  readonly running: boolean;
  readonly onToggleSidebar: () => void;
  readonly onToggleRightPanel: () => void;
  readonly onSelectRightPanelMode: (mode: RightPanelMode) => void;
  readonly onOpenInbox: () => void;
  readonly onOpenSettings?: () => void;
  readonly onStop: () => void;
};

function isTauriApp(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function WorkspaceChrome({
  title,
  meta,
  sidebarOpen,
  rightPanelOpen,
  rightPanelMode,
  locale,
  inboxPendingCount,
  panelBadgeCount,
  running,
  onToggleSidebar,
  onToggleRightPanel,
  onSelectRightPanelMode,
  onOpenInbox,
  onOpenSettings,
  onStop,
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
      <div className="workspace-chrome__leading">
        <SidebarToggle
          open={sidebarOpen}
          onToggle={onToggleSidebar}
          variant="panel"
          className="icon-btn"
        />
        <div className="workspace-chrome__title" data-tauri-drag-region={tauri ? "" : undefined}>
          <span className="workspace-chrome__topic" title={title}>
            {title}
          </span>
          {meta ? <span className="workspace-chrome__meta">{meta}</span> : null}
        </div>
      </div>
      <div className="workspace-chrome__spacer" data-tauri-drag-region={tauri ? "" : undefined} />
      <div className="workspace-chrome__actions">
        {running ? (
          <button
            type="button"
            className="workspace-chrome__run-badge"
            onClick={onStop}
            title="Stop run (⌘.)"
          >
            running
          </button>
        ) : null}
        {inboxPendingCount > 0 ? (
          <TitlebarInboxButton
            pendingCount={inboxPendingCount}
            onClick={onOpenInbox}
          />
        ) : null}
        <button
          type="button"
          className="icon-btn"
          title="⌘K"
          aria-label="명령 팔레트"
          onClick={openCommandPalette}
        >
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </button>
        <WorkbenchModeMenu
          active={rightPanelMode}
          open={rightPanelOpen}
          locale={locale}
          badgeCount={panelBadgeCount}
          onSelect={onSelectRightPanelMode}
          onToggleOpen={onToggleRightPanel}
        />
      </div>
    </header>
  );
}
