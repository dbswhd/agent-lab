type Props = {
  open: boolean;
  onToggle: () => void;
  /** titlebar uses panel icon; legacy chat-toolbar uses chevron */
  variant?: "chevron" | "panel";
  className?: string;
};

export function SidebarToggle({
  open,
  onToggle,
  variant = "chevron",
  className,
}: Props) {
  return (
    <button
      type="button"
      className={["sidebar-toggle", className].filter(Boolean).join(" ")}
      aria-expanded={open}
      aria-label={open ? "사이드바 접기" : "사이드바 펼치기"}
      title={`${open ? "사이드바 접기" : "사이드바 펼치기"} (⌃⌘S)`}
      onClick={onToggle}
    >
      {variant === "panel" ? (
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
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M9 3v18" />
        </svg>
      ) : (
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
          {open ? (
            <path
              fill="currentColor"
              d="M9.78 3.22a.75.75 0 0 1 0 1.06L6.06 8l3.72 3.72a.75.75 0 1 1-1.06 1.06l-4.25-4.25a.75.75 0 0 1 0-1.06l4.25-4.25a.75.75 0 0 1 1.06 0Z"
            />
          ) : (
            <path
              fill="currentColor"
              d="M6.22 3.22a.75.75 0 0 0 0 1.06L9.94 8l-3.72 3.72a.75.75 0 1 0 1.06 1.06l4.25-4.25a.75.75 0 0 0 0-1.06L7.28 3.22a.75.75 0 0 0-1.06 0Z"
            />
          )}
        </svg>
      )}
    </button>
  );
}
