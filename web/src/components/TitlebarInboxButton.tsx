type Props = {
  pendingCount?: number;
  onClick: () => void;
  disabled?: boolean;
};

export function TitlebarInboxButton({
  pendingCount = 0,
  onClick,
  disabled,
}: Props) {
  const badge = pendingCount > 0 ? pendingCount : undefined;

  return (
    <button
      type="button"
      className="titlebar-inbox-btn icon-btn"
      title="Human Inbox"
      aria-label={
        badge ? `Human Inbox, ${badge} pending` : "Human Inbox"
      }
      disabled={disabled}
      onClick={onClick}
    >
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
        <path d="M22 12h-6l-2 3H10l-2-3H2" />
        <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
      </svg>
      {badge ? (
        <span className="titlebar-inbox-btn__badge" aria-hidden>
          {badge > 99 ? "99+" : badge}
        </span>
      ) : null}
    </button>
  );
}
