import type { RightPanelMode } from "../utils/workspaceTabs";
import type { Locale } from "../i18n/locale";
import { workbenchModeLabel } from "../utils/workbenchModeLabel";

const MODES: readonly RightPanelMode[] = [
  "preview",
  "diff",
  "terminal",
  "files",
  "background",
  "overview",
] as const;

type Props = {
  readonly active: RightPanelMode;
  readonly open: boolean;
  readonly locale: Locale;
  readonly onSelect: (mode: RightPanelMode) => void;
};

function modeIcon(mode: RightPanelMode) {
  switch (mode) {
    case "preview":
      return <path d="m8 5 10 7-10 7Z" />;
    case "diff":
      return (
        <>
          <path d="M8 5h10" />
          <path d="M8 12h10" />
          <path d="M8 19h10" />
          <path d="M4 12h.01" />
        </>
      );
    case "terminal":
      return (
        <>
          <path d="m4 7 5 5-5 5" />
          <path d="M12 19h8" />
        </>
      );
    case "files":
      return (
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
      );
    case "background":
      return (
        <>
          <path d="M12 3v3" />
          <path d="M12 18v3" />
          <path d="M3 12h3" />
          <path d="M18 12h3" />
          <path d="m5.6 5.6 2.1 2.1" />
          <path d="m16.3 16.3 2.1 2.1" />
        </>
      );
    case "overview":
      return <path d="M4 5h16v14H4Z" />;
  }
}

/** Persistent segmented tab bar for switching the workbench panel's mode —
 *  replaces the former dropdown menu so every mode is visible and reachable
 *  in one click (Apricot Glass, web/DESIGN.md). */
export function WorkbenchModeTabs({ active, open, locale, onSelect }: Props) {
  return (
    <div
      className="workbench-mode-tabs"
      role="tablist"
      aria-label="Workbench panel"
    >
      {MODES.map((mode) => {
        const label = workbenchModeLabel(mode, locale);
        const isActive = open && active === mode;
        return (
          <button
            key={mode}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-label={label}
            title={label}
            className={`workbench-mode-tabs__item${isActive ? " is-active" : ""}`}
            onClick={() => onSelect(mode)}
          >
            <svg
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              {modeIcon(mode)}
            </svg>
          </button>
        );
      })}
    </div>
  );
}
