import { useDismissOnPointerDownOutside } from "../hooks/useDismissOnPointerDownOutside";

type Props = {
  prompt: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
};

/** API key entry for /login api — composer-anchored popover. */
export function ComposerAuthSecretPopover({
  prompt,
  value,
  onChange,
  onSubmit,
  onCancel,
}: Props) {
  const popoverRef = useDismissOnPointerDownOutside(true, onCancel);

  return (
    <div
      ref={popoverRef}
      className="slash-command-menu composer-auth-secret-popover"
      role="dialog"
      aria-label={prompt}
      data-testid="composer-auth-secret-popover"
    >
      <div className="slash-command-menu__main">
        <header className="slash-command-menu__section-label">{prompt}</header>
        <div className="composer-auth-secret-popover__field">
          <input
            id="composer-auth-secret"
            type="password"
            autoComplete="off"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSubmit();
              }
            }}
            autoFocus
          />
        </div>
        <div className="composer-slash-choice__footer composer-auth-secret-popover__footer">
          <button
            type="button"
            className="composer-slash-choice__action composer-slash-choice__action--primary"
            disabled={!value.trim()}
            onClick={onSubmit}
          >
            저장
          </button>
          <button
            type="button"
            className="composer-slash-choice__cancel"
            onClick={onCancel}
          >
            취소 (Esc)
          </button>
        </div>
      </div>
    </div>
  );
}
