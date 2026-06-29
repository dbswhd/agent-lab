import { useEffect, useRef, useState } from "react";
import type { RightPanelMode } from "../utils/workspaceTabs";
import type { Locale } from "../i18n/locale";
import { workbenchModeLabel } from "../utils/workbenchModeLabel";

type MenuItem = {
  readonly mode: RightPanelMode;
  readonly shortcut?: string;
};

const PRIMARY_ITEMS: readonly MenuItem[] = [
  { mode: "preview", shortcut: "⇧⌘P" },
  { mode: "diff", shortcut: "⇧⌘D" },
  { mode: "terminal", shortcut: "^`" },
  { mode: "files", shortcut: "⇧⌘F" },
  { mode: "background" },
] as const;

const SECONDARY_ITEMS: readonly MenuItem[] = [{ mode: "overview" }] as const;

type Props = {
  readonly active: RightPanelMode;
  readonly open: boolean;
  readonly locale: Locale;
  readonly badgeCount?: number;
  readonly onSelect: (mode: RightPanelMode) => void;
  readonly onToggleOpen: () => void;
  readonly onMenuOpenChange?: (open: boolean) => void;
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

export function WorkbenchModeMenu({
  active,
  open,
  locale,
  badgeCount = 0,
  onSelect,
  onMenuOpenChange,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onMenuOpenChange?.(menuOpen);
  }, [menuOpen, onMenuOpenChange]);

  useEffect(() => {
    if (!menuOpen) return;
    function onPointerDown(event: PointerEvent) {
      if (
        event.target instanceof Node &&
        rootRef.current?.contains(event.target)
      ) {
        return;
      }
      setMenuOpen(false);
    }
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [menuOpen]);

  function pick(mode: RightPanelMode) {
    onSelect(mode);
    setMenuOpen(false);
  }

  return (
    <div className="workbench-mode-menu" ref={rootRef}>
      <button
        type="button"
        className={`workbench-mode-menu__trigger${menuOpen ? " is-open" : ""}`}
        aria-label="Workbench panel"
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((current) => !current)}
      >
        <svg
          viewBox="0 0 24 24"
          width="17"
          height="17"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M4 5h16v14H4Z" />
          <path d="M14 5v14" />
        </svg>
        <span className="workbench-mode-menu__caret">⌄</span>
        {badgeCount > 0 ? (
          <span className="context-sidebar-toggle__badge" aria-hidden>
            {badgeCount}
          </span>
        ) : null}
      </button>
      {menuOpen ? (
        <div className="workbench-mode-menu__popover" role="menu">
          {[...PRIMARY_ITEMS, ...SECONDARY_ITEMS].map((item, index) => (
            <button
              key={item.mode}
              type="button"
              className={[
                "workbench-mode-menu__item",
                open && active === item.mode ? "is-active" : "",
                index === PRIMARY_ITEMS.length ? "has-separator" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              role="menuitem"
              onClick={() => pick(item.mode)}
            >
              <svg
                viewBox="0 0 24 24"
                width="17"
                height="17"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.8}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                {modeIcon(item.mode)}
              </svg>
              <span>{workbenchModeLabel(item.mode, locale)}</span>
              {item.shortcut ? <kbd>{item.shortcut}</kbd> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
