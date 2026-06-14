type Props = {
  open: boolean;
  onToggle: () => void;
  badgeCount?: number;
};

/** Right context sidebar toggle — prototype titlebar icon-btn. */
export function ContextSidebarToggle({
  open,
  onToggle,
  badgeCount = 0,
}: Props) {
  return (
    <button
      type="button"
      className={`icon-btn${open ? " is-active" : ""}`}
      aria-expanded={open}
      aria-label={open ? "컨텍스트 접기" : "컨텍스트 펼치기"}
      title={open ? "컨텍스트" : "컨텍스트 (⌃⌘I)"}
      onClick={onToggle}
    >
      {badgeCount > 0 ? (
        <span className="context-sidebar-toggle__badge" aria-hidden>
          {badgeCount > 9 ? "9+" : badgeCount}
        </span>
      ) : null}
      <svg
        viewBox="0 0 24 24"
        width="17"
        height="17"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.7}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M9 4v16" />
      </svg>
    </button>
  );
}
