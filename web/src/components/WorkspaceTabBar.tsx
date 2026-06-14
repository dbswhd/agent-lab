import type { WorkspaceTab } from "../utils/workspaceTabs";
import type { Locale } from "../i18n/locale";
import { messages } from "../i18n/messages";

const TAB_META: {
  id: WorkspaceTab;
  icon: "transcript" | "work" | "run" | "artifacts" | "files" | "preview" | "terminal";
  shortcut: string;
}[] = [
  { id: "transcript", icon: "transcript", shortcut: "⌘1" },
  { id: "work", icon: "work", shortcut: "⌘2" },
  { id: "run", icon: "run", shortcut: "⌘3" },
  { id: "artifacts", icon: "artifacts", shortcut: "⌘4" },
  { id: "files", icon: "files", shortcut: "⌘5" },
  { id: "preview", icon: "preview", shortcut: "⌘6" },
  { id: "terminal", icon: "terminal", shortcut: "⌘7" },
];

type Props = {
  active: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  disabled?: boolean;
  isNew?: boolean;
  locale?: Locale;
  tabPinned?: boolean;
  running?: boolean;
  runningLabel?: string | null;
};

function TabIcon({ kind }: { kind: (typeof TAB_META)[number]["icon"] }) {
  const common = {
    viewBox: "0 0 24 24",
    width: 15,
    height: 15,
    fill: "none" as const,
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (kind) {
    case "transcript":
      return (
        <svg {...common}>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case "work":
      return (
        <svg {...common}>
          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
        </svg>
      );
    case "run":
      return (
        <svg {...common}>
          <polygon points="8,5 19,12 8,19" fill="currentColor" stroke="none" />
        </svg>
      );
    case "artifacts":
      return (
        <svg {...common}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6" />
        </svg>
      );
    case "files":
      return (
        <svg {...common}>
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2Z" />
        </svg>
      );
    case "preview":
      return (
        <svg {...common}>
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4" />
        </svg>
      );
    case "terminal":
      return (
        <svg {...common}>
          <polyline points="4 17 10 11 4 5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        </svg>
      );
  }
}

/** Workspace tab bar — prototype `.tabbar` with icons + shortcuts. */
export function WorkspaceTabBar({
  active,
  onChange,
  disabled,
  isNew,
  locale = "en",
  tabPinned,
  running,
  runningLabel,
}: Props) {
  const m = messages(locale);

  if (isNew) {
    return (
      <div className="tabbar">
        <span className="tabbar__static">{m.transcript}</span>
      </div>
    );
  }

  return (
    <div className="tabbar">
      <div className="tabbar__lead" role="tablist" aria-label="Workspace">
        {TAB_META.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active === tab.id}
            className={`tabbar__tab${active === tab.id ? " is-active" : ""}`}
            disabled={disabled}
            title={`${m[tab.id]} (${tab.shortcut})`}
            onClick={() => onChange(tab.id)}
          >
            <TabIcon kind={tab.icon} />
            {m[tab.id]}
            <span className="tab-shortcut">{tab.shortcut}</span>
          </button>
        ))}
      </div>
      <div className="tabbar__spacer" />
      <div className="tabbar__trailing">
        {tabPinned ? (
          <span className="badge">
            <PinIcon />
            {m.pinned}
          </span>
        ) : null}
        {running ? (
          <span className="badge badge--accent" title={runningLabel ?? undefined}>
            <span className="dot dot--live" aria-hidden />
            {runningLabel ?? m.running}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function PinIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="11"
      height="11"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M12 17v5M9 3h6l1 7 4 2-1 5H5L4 12l4-2 1-7Z" />
    </svg>
  );
}
