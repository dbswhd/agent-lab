type Props = {
  syncMode: boolean;
  onChange: (syncMode: boolean) => void;
  disabled?: boolean;
  label?: string;
  title?: string;
};

/** sync = pause discuss on pending inbox; soft = surface only. */
export function ComposerInboxModeToggle({
  syncMode,
  onChange,
  disabled,
  label = "Inbox sync",
  title,
}: Props) {
  return (
    <label className="switch" title={title}>
      <input
        type="checkbox"
        checked={syncMode}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch__track" aria-hidden />
      {label}
    </label>
  );
}
