type Props = {
  open: boolean;
  onToggle: () => void;
};

export function SidebarToggle({ open, onToggle }: Props) {
  return (
    <button
      type="button"
      className="sidebar-toggle"
      aria-expanded={open}
      aria-label={open ? "사이드바 접기" : "사이드바 펼치기"}
      title={open ? "사이드바 접기" : "사이드바 펼치기"}
      onClick={onToggle}
    >
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
    </button>
  );
}
