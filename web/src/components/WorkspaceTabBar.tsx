import type { WorkspaceTab } from "../utils/workspaceTabs";
import type { Locale } from "../i18n/locale";
import { messages } from "../i18n/messages";

const TAB_META: {
  id: WorkspaceTab;
  icon: "transcript" | "work" | "run" | "artifacts" | "files";
  shortcut: string;
}[] = [
  { id: "transcript", icon: "transcript", shortcut: "⌘1" },
  { id: "work", icon: "work", shortcut: "⌘2" },
  { id: "run", icon: "run", shortcut: "⌘3" },
  { id: "artifacts", icon: "artifacts", shortcut: "⌘4" },
  { id: "files", icon: "files", shortcut: "⌘5" },
];

type Props = {
  active: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  disabled?: boolean;
  isNew?: boolean;
  locale?: Locale;
  tabPinned?: boolean;
  running?: boolean;
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
          <span className="badge badge--accent">
            <span className="dot dot--live" aria-hidden />
            {m.running}
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
