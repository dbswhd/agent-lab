type ButtonProps = {
  visible: boolean;
  onClick: () => void;
};

/** Floating ↓ button shown when scrolled up (overlays.css). */
export function ScrollToBottomButton({ visible, onClick }: ButtonProps) {
  return (
    <button
      type="button"
      className={`scroll-to-bottom-btn${visible ? " is-visible" : ""}`}
      onClick={onClick}
      aria-label="맨 아래로"
      title="맨 아래로"
      aria-hidden={!visible}
      tabIndex={visible ? 0 : -1}
    >
      <svg
        className="scroll-to-bottom-btn__icon"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M8 3.5v9" />
        <path d="m4.5 9 3.5 3.5L11.5 9" />
      </svg>
    </button>
  );
}
